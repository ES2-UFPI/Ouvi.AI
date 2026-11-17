"""Cache global de áudio (US08): o mesmo conteúdo enviado ao TTS é sintetizado uma única vez.

Comandos (veja o README): `python -m app.modules.audio.cache stats` e `python -m app.modules.audio.cache purge`.
"""
from app.modules.audio.cache.key import CACHE_KEY_VERSION, build_cache_key, normalize_ssml
from app.modules.audio.cache.repository import AudioBlobRepository

__all__ = ["CACHE_KEY_VERSION", "AudioBlobRepository", "build_cache_key", "normalize_ssml"]
