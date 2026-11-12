"""AudioGenerationFacade: junta as etapas da geração de áudio de uma história atrás de um único `generate()`.

Para cada frase, em ordem: compõe o SSML com as regras do filtro (AudioComposer), sintetiza (TTSProvider),
grava o arquivo (ObjectStorage) e registra o resultado (AudioAssetRepository). Antes do TTS, consulta o cache
global de áudio (AudioCache, US08): se o mesmo conteúdo já foi sintetizado, para qualquer filtro ou usuário, o
arquivo é reaproveitado e o TTS não é chamado. O Router não conhece nenhuma
dessas etapas. Uma falha em uma frase não derruba as outras: só aquela frase termina `failed`.

A Facade só lê as frases pelo `StoryService` (nunca pelo repositório de outro módulo) e recebe a sessão do
banco já pronta. Em segundo plano, quem chama é `run_generation`, que abre uma sessão PRÓPRIA: a sessão da
requisição já foi fechada quando a tarefa começa.
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.storage import ObjectStorage, StorageError
from app.integrations.tts import TTSError, TTSProvider
from app.modules.audio.cache.service import AudioCache
from app.modules.audio.composer import AudioComposer
from app.modules.audio.models import STATUS_READY, AudioAsset
from app.modules.audio.repository import AudioAssetRepository, InvalidTransition, compute_rules_hash
from app.modules.stories.models import Segment
from app.modules.stories.service import StoryService

logger = logging.getLogger(__name__)

# Tentativas de síntese por frase quando o erro do TTS é recuperável (tempo esgotado, 429, 5xx)
MAX_ATTEMPTS = 3
# Espera antes da 2ª tentativa; dobra a cada nova tentativa (1 s, 2 s...)
RETRY_BASE_DELAY_SECONDS = 1.0
# Uma frase em `generating` sem mudança há mais que isto está presa (a API reiniciou no meio da geração)
STALE_AFTER = timedelta(minutes=2)

# Usados na chave de cache quando o provedor não informa os seus (veja `provider_name` e `audio_format`)
DEFAULT_PROVIDER = "desconhecido"
DEFAULT_AUDIO_FORMAT = "wav"


@dataclass
class GenerationResult:
    """Resumo de uma chamada a `generate()`: ids das frases (segment_id) em cada situação."""

    generated: list[int] = field(default_factory=list)  # sintetizadas agora
    skipped: list[int] = field(default_factory=list)  # já prontas, ou em geração por outro worker
    failed: list[int] = field(default_factory=list)  # falharam nesta chamada
    cached: list[int] = field(default_factory=list)  # prontas agora, reaproveitando o cache (sem TTS)
    chars_saved: int = 0  # caracteres que deixaram de ir ao TTS graças ao cache


class AudioGenerationFacade:
    def __init__(
        self,
        stories: StoryService,
        assets: AudioAssetRepository,
        tts: TTSProvider,
        storage: ObjectStorage,
        *,
        voice_id: str,
        composer: AudioComposer | None = None,
        cache: AudioCache | None = None,
        provider: str | None = None,
        audio_format: str | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        retry_base_delay: float = RETRY_BASE_DELAY_SECONDS,
        stale_after: timedelta = STALE_AFTER,
        sleep: Callable[[float], None] = time.sleep,  # injetável: os testes não esperam de verdade
    ) -> None:
        self.stories = stories
        self.assets = assets
        self.tts = tts
        self.storage = storage
        self.voice_id = voice_id
        self.composer = composer or AudioComposer()
        self.cache = cache or AudioCache(assets.db, storage)
        # Fornecedor e formato entram na chave de cache: trocar qualquer um gera áudio novo
        self.provider = provider or getattr(tts, "provider_name", DEFAULT_PROVIDER)
        self.audio_format = audio_format or getattr(tts, "audio_format", DEFAULT_AUDIO_FORMAT)
        self.max_attempts = max_attempts
        self.retry_base_delay = retry_base_delay
        self.stale_after = stale_after
        self.sleep = sleep

    def generate(self, story_id: int, rules: dict[str, Any], user_id: int | None = None) -> GenerationResult:
        """Gera o áudio de todas as frases da história com as regras do filtro.

        `rules` são as regras do filtro (`ListeningFilter.rules`), já conferidas pelo chamador: a posse do
        filtro é verificada no Router/Service, antes de chegar aqui. `user_id` só serve para o log.

        Idempotente: frases já `ready` (para as mesmas regras e voz) não chamam o TTS de novo; frases
        `failed` são tentadas outra vez. As frases são processadas em ordem e cada uma é confirmada no
        banco assim que termina, então a primeira fica pronta antes das demais e o player já pode começar.
        Levanta `LookupError` se a história não existir.
        """
        _, segments = self.stories.get_segments(story_id)
        rules_hash = compute_rules_hash(rules)
        logger.info(
            "Gerando áudio da história %s (regras %s, usuário %s): %d frases",
            story_id, rules_hash[:8], user_id, len(segments),
        )

        # Recupera frases presas em `generating` (o worker morreu no meio, ex.: reinício da API)
        recovered = self.assets.reset_stale(older_than=self.stale_after)
        if recovered:
            logger.warning("%d frase(s) presa(s) em generating voltaram para a fila", recovered)

        # A seleção das trocas é feita sobre a HISTÓRIA INTEIRA (densidade e curva), igual à prévia do texto
        selected = self.composer.select_swaps(
            segments, rules["segment_types"], rules["density"], rules.get("word_level"), rules.get("progression")
        )

        # Cria antes todos os registros (`pending`): o status já mostra o total desde o começo
        assets = [
            self.assets.get_or_create(
                story_id=story_id, segment_id=segment.id, rules_hash=rules_hash, voice_id=self.voice_id
            )
            for segment in segments
        ]

        result = GenerationResult()
        for segment, asset in zip(segments, assets):
            outcome = self._process(segment, asset, selected, rules["base_language"], result)
            getattr(result, outcome).append(segment.id)
        logger.info(
            "Cache de áudio da história %s: %d acerto(s), %d erro(s), %d caracteres economizados",
            story_id, len(result.cached), len(result.generated), result.chars_saved,
        )
        return result

    def _process(
        self, segment: Segment, asset: AudioAsset, selected: set[int], base_language: str, result: GenerationResult
    ) -> str:
        """Gera uma frase. Devolve o nome da lista do GenerationResult em que ela entra."""
        if asset.status == STATUS_READY:
            return "skipped"
        try:
            self.assets.start_generation(asset)
        except InvalidTransition:
            # Outro worker já está gerando esta frase (ou acabou de terminar): não repete o trabalho
            return "skipped"

        try:
            ssml = self.composer.compose(segment, selected, base_language).ssml
            # O cache é consultado depois de compor: a chave depende do SSML final, não do filtro
            cached = self.cache.fetch_or_create(
                ssml,
                voice_id=self.voice_id,
                provider=self.provider,
                audio_format=self.audio_format,
                synthesize=lambda: self._synthesize(ssml),
            )
        except (TTSError, StorageError, ValueError) as exc:
            # ValueError: anotação desatualizada em relação ao texto (o composer recusa montar o SSML)
            logger.warning("Falha ao gerar o áudio da frase %s: %s", segment.id, exc)
            self.assets.mark_failed(asset, str(exc) or type(exc).__name__)
            return "failed"

        blob = cached.blob
        self.assets.mark_ready(
            asset,
            storage_key=blob.storage_key,
            audio_format=blob.format,
            duration_ms=blob.duration_ms,
            blob_id=blob.id,
        )
        if cached.hit:
            result.chars_saved += blob.char_count
            logger.info(
                "Cache de áudio: acerto na frase %s (blob %s, %d caracteres economizados)",
                segment.id, blob.id, blob.char_count,
            )
            return "cached"
        logger.info("Cache de áudio: erro na frase %s (blob %s sintetizado)", segment.id, blob.id)
        return "generated"

    def _synthesize(self, ssml: str):
        """Chama o TTS, tentando de novo (com espera crescente) só os erros recuperáveis."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.tts.synthesize(ssml, self.voice_id)
            except TTSError as exc:
                if not exc.retryable or attempt == self.max_attempts:
                    raise
                self.sleep(self.retry_base_delay * 2 ** (attempt - 1))
        raise AssertionError("inalcançável")  # pragma: no cover


def build_facade(db: Session, tts: TTSProvider, storage: ObjectStorage, voice_id: str, **kwargs: Any) -> AudioGenerationFacade:
    """Monta a Facade sobre uma sessão."""
    return AudioGenerationFacade(
        StoryService.from_session(db), AudioAssetRepository(db), tts, storage, voice_id=voice_id, **kwargs
    )


def run_generation(
    session_factory: Callable[[], Session],
    tts: TTSProvider,
    storage: ObjectStorage,
    *,
    voice_id: str,
    story_id: int,
    rules: dict[str, Any],
    user_id: int | None = None,
    **kwargs: Any,
) -> GenerationResult | None:
    """Ponto de entrada da tarefa em segundo plano: abre uma sessão PRÓPRIA, gera e fecha a sessão.

    Nunca recebe a sessão da requisição (que o FastAPI fecha ao responder). Erros inesperados vão para o
    log em vez de subir: não há mais ninguém esperando a resposta.
    """
    db = session_factory()
    try:
        return build_facade(db, tts, storage, voice_id, **kwargs).generate(story_id, rules, user_id)
    except Exception:
        logger.exception("Falha inesperada na geração do áudio da história %s", story_id)
        return None
    finally:
        db.close()
