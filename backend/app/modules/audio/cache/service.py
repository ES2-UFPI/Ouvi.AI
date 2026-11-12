"""AudioCache: consulta o cache antes do TTS e registra o resultado depois dele.

Fluxo de uma frase (`fetch_or_create`), todo dentro de UMA transação que segura o lock da chave:
1. calcula a chave pelo conteúdo e trava a chave (lock consultivo do Postgres);
2. blob encontrado e arquivo presente no armazenamento: acerto, o TTS não é chamado;
3. senão: sintetiza, grava o arquivo e só DEPOIS registra (ou corrige) o blob. Uma falha no meio deixa no
   máximo um arquivo órfão, nunca um registro apontando para um arquivo que não existe.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.integrations.storage import ObjectStorage, StorageObjectNotFound
from app.integrations.tts import SynthesisResult
from app.modules.audio.cache.key import build_cache_key, normalize_ssml
from app.modules.audio.cache.repository import AudioBlobRepository
from app.modules.audio.models import AudioBlob

logger = logging.getLogger(__name__)

CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg"}


def cache_storage_key(cache_key: str, audio_format: str) -> str:
    """Chave do arquivo no armazenamento: depende só do conteúdo, como o próprio blob."""
    return f"cache/{cache_key[:2]}/{cache_key}.{audio_format}"


@dataclass(frozen=True)
class CacheResult:
    blob: AudioBlob
    hit: bool  # True: reaproveitado, sem chamar o TTS


class AudioCache:
    def __init__(self, db: Session, storage: ObjectStorage, blobs: AudioBlobRepository | None = None) -> None:
        self.db = db
        self.storage = storage
        self.blobs = blobs or AudioBlobRepository(db)

    def fetch_or_create(
        self,
        ssml: str,
        *,
        voice_id: str,
        provider: str,
        audio_format: str,
        synthesize: Callable[[], SynthesisResult],
    ) -> CacheResult:
        """Devolve o blob do conteúdo, chamando `synthesize` só se ele ainda não existir (ou se o arquivo
        sumiu do armazenamento). Confirma a transação no fim; em qualquer erro desfaz e repassa o erro."""
        cache_key = build_cache_key(ssml, voice_id, provider, audio_format)
        try:
            # Até o commit (ou rollback), outro pedido da mesma chave espera aqui
            self.blobs.lock(cache_key)
            blob = self.blobs.get_by_key(cache_key)
            if blob is not None and self._file_exists(blob.storage_key):
                self.blobs.register_hit(blob)
                self.db.commit()
                return CacheResult(blob, hit=True)

            if blob is not None:
                logger.warning(
                    "Cache de áudio: o arquivo do blob %s sumiu do armazenamento (%s); gerando de novo",
                    blob.id, blob.storage_key,
                )
            synthesis = synthesize()
            storage_key = cache_storage_key(cache_key, synthesis.format)
            content_type = CONTENT_TYPES.get(synthesis.format, "application/octet-stream")
            self.storage.put(storage_key, synthesis.data, content_type=content_type)

            if blob is None:
                blob = self.blobs.create_if_absent(
                    cache_key=cache_key,
                    storage_key=storage_key,
                    audio_format=synthesis.format,
                    duration_ms=synthesis.duration_ms,
                    size_bytes=len(synthesis.data),
                    char_count=len(normalize_ssml(ssml)),
                )
            else:
                self.blobs.replace_file(
                    blob,
                    storage_key=storage_key,
                    audio_format=synthesis.format,
                    duration_ms=synthesis.duration_ms,
                    size_bytes=len(synthesis.data),
                )
            self.db.commit()
        except BaseException:
            self.db.rollback()  # solta o lock da chave
            raise
        return CacheResult(blob, hit=False)

    def _file_exists(self, storage_key: str) -> bool:
        try:
            self.storage.size(storage_key)
        except StorageObjectNotFound:
            return False
        return True
