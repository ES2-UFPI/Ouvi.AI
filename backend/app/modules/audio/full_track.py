"""Áudio único da história: junta o áudio de cada frase num arquivo só, com a linha do tempo de cada frase.

O player toca esse arquivo inteiro, com uma barra de progresso para a história toda: dá para voltar a
qualquer palavra, em vez de ficar preso à frase que está tocando. As frases continuam sendo geradas (e
guardadas no cache de áudio) uma a uma; este módulo só COSTURA o que já está pronto.

O arquivo não é guardado no banco: a chave no armazenamento é o hash das chaves das frases que o compõem.
Se uma frase for gerada de novo (áudio diferente), a chave muda e o arquivo é montado outra vez.
"""
import hashlib
import io
import wave
from collections.abc import Sequence
from dataclasses import dataclass

from app.integrations.storage import ObjectStorage, StorageObjectNotFound
from app.modules.audio.models import AudioAsset

FULL_PREFIX = "full"


class UnsupportedAudioFormat(Exception):
    """Os áudios das frases não podem ser juntados (formatos diferentes ou desconhecidos)."""


@dataclass(frozen=True)
class TrackSegment:
    """Onde a frase fica no áudio único."""

    segment_id: int
    position: int
    start_ms: int
    duration_ms: int


@dataclass(frozen=True)
class FullTrack:
    storage_key: str
    format: str
    duration_ms: int
    segments: list[TrackSegment]


def join_audio(parts: Sequence[bytes], audio_format: str) -> bytes:
    """Junta os arquivos, na ordem. MP3 de taxa constante (o do Azure) é só colar os quadros um depois do
    outro; WAV precisa de um cabeçalho novo com o tamanho total."""
    if audio_format == "mp3":
        return b"".join(parts)
    if audio_format == "wav":
        return _join_wav(parts)
    raise UnsupportedAudioFormat(f"formato não suportado para juntar: {audio_format!r}")


def _join_wav(parts: Sequence[bytes]) -> bytes:
    params = None
    frames: list[bytes] = []
    for data in parts:
        with wave.open(io.BytesIO(data)) as reader:
            current = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
            if params is not None and current != params:
                raise UnsupportedAudioFormat("os arquivos WAV têm parâmetros diferentes")
            params = current
            frames.append(reader.readframes(reader.getnframes()))
    if params is None:
        raise UnsupportedAudioFormat("nenhum arquivo para juntar")
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(params[0])
        writer.setsampwidth(params[1])
        writer.setframerate(params[2])
        writer.writeframes(b"".join(frames))
    return out.getvalue()


def track_key(assets: Sequence[AudioAsset], audio_format: str) -> str:
    digest = hashlib.sha256("|".join(a.storage_key for a in assets).encode()).hexdigest()
    return f"{FULL_PREFIX}/{digest}.{audio_format}"


class FullTrackBuilder:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage

    def build(self, assets: Sequence[AudioAsset], positions: dict[int, int]) -> FullTrack:
        """`assets` são os áudios PRONTOS, em ordem de posição; `positions` dá a posição de cada frase.

        Reaproveita o arquivo se ele já foi montado. Levanta `UnsupportedAudioFormat` se os formatos
        diferem e `StorageError` se o armazenamento falhar.
        """
        formats = {a.format for a in assets}
        if len(formats) != 1:
            raise UnsupportedAudioFormat(f"formatos diferentes: {sorted(f or '?' for f in formats)}")
        audio_format = formats.pop() or ""
        key = track_key(assets, audio_format)

        try:
            self.storage.size(key)
        except StorageObjectNotFound:
            parts = [self.storage.get(a.storage_key) for a in assets]
            content_type = "audio/mpeg" if audio_format == "mp3" else "audio/wav"
            self.storage.put(key, join_audio(parts, audio_format), content_type)

        segments: list[TrackSegment] = []
        start = 0
        for asset in assets:
            duration = asset.duration_ms or 0
            segments.append(TrackSegment(asset.segment_id, positions[asset.segment_id], start, duration))
            start += duration
        return FullTrack(storage_key=key, format=audio_format, duration_ms=start, segments=segments)
