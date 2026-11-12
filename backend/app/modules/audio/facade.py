"""AudioGenerationFacade: junta as etapas da geração de áudio de uma história atrás de um único `generate()`.

Para cada frase, em ordem: compõe o SSML com as regras do filtro (AudioComposer), sintetiza (TTSProvider),
grava o arquivo (ObjectStorage) e registra o resultado (AudioAssetRepository). O Router não conhece nenhuma
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

_CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg"}


def audio_storage_key(story_id: int, rules_hash: str, voice_id: str, segment_id: int, audio_format: str) -> str:
    """Chave do arquivo no armazenamento. Depende das regras e da voz, como o próprio AudioAsset."""
    return f"stories/{story_id}/audio/{rules_hash}/{voice_id}/{segment_id}.{audio_format}"


@dataclass
class GenerationResult:
    """Resumo de uma chamada a `generate()`: ids das frases (segment_id) em cada situação."""

    generated: list[int] = field(default_factory=list)  # sintetizadas agora
    skipped: list[int] = field(default_factory=list)  # já prontas, ou em geração por outro worker
    failed: list[int] = field(default_factory=list)  # falharam nesta chamada


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

        # A seleção das trocas é feita sobre a HISTÓRIA INTEIRA (densidade), igual à prévia do texto
        selected = self.composer.select_swaps(segments, rules["segment_types"], rules["density"])

        # Cria antes todos os registros (`pending`): o status já mostra o total desde o começo
        assets = [
            self.assets.get_or_create(
                story_id=story_id, segment_id=segment.id, rules_hash=rules_hash, voice_id=self.voice_id
            )
            for segment in segments
        ]

        result = GenerationResult()
        for segment, asset in zip(segments, assets):
            outcome = self._process(segment, asset, selected, rules["base_language"])
            getattr(result, outcome).append(segment.id)
        return result

    def _process(self, segment: Segment, asset: AudioAsset, selected: set[int], base_language: str) -> str:
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
            synthesis = self._synthesize(ssml)
            key = audio_storage_key(asset.story_id, asset.rules_hash, asset.voice_id, segment.id, synthesis.format)
            content_type = _CONTENT_TYPES.get(synthesis.format, "application/octet-stream")
            self.storage.put(key, synthesis.data, content_type=content_type)
        except (TTSError, StorageError, ValueError) as exc:
            # ValueError: anotação desatualizada em relação ao texto (o composer recusa montar o SSML)
            logger.warning("Falha ao gerar o áudio da frase %s: %s", segment.id, exc)
            self.assets.mark_failed(asset, str(exc) or type(exc).__name__)
            return "failed"

        self.assets.mark_ready(
            asset, storage_key=key, audio_format=synthesis.format, duration_ms=synthesis.duration_ms
        )
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
