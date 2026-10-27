"""Camada Service: regras do streaming de áudio, sem nada de HTTP."""
import mimetypes
from dataclasses import dataclass

from app.integrations.storage import ObjectStorage
from app.modules.audio.ranges import ByteRange, parse_range
from app.modules.audio.signing import AudioUrlSigner


@dataclass(frozen=True)
class AudioChunk:
    data: bytes
    size: int  # tamanho do arquivo inteiro, para o Content-Range
    content_type: str
    byte_range: ByteRange | None  # None quando o arquivo vai inteiro (status 200)


class AudioService:
    def __init__(self, storage: ObjectStorage, signer: AudioUrlSigner) -> None:
        self.storage = storage
        self.signer = signer

    def sign(self, key: str) -> dict[str, str]:
        """Parâmetros da URL assinada. Levanta `StorageObjectNotFound` se o áudio não existir."""
        self.storage.size(key)  # não faz sentido assinar uma URL que vai dar 404
        return self.signer.sign(key)

    def stream(self, key: str, expires: int, signature: str, range_header: str | None) -> AudioChunk:
        """Confere a assinatura e lê o trecho pedido.

        Levanta `AudioSignatureError` (URL inválida), `StorageObjectNotFound` (áudio inexistente)
        ou `RangeNotSatisfiable` (faixa fora do arquivo).
        """
        # A assinatura vem antes de tudo: sem ela, ninguém descobre nem se a chave existe
        self.signer.verify(key, expires, signature)

        size = self.storage.size(key)
        byte_range = parse_range(range_header, size)
        if byte_range is None:
            data = self.storage.get(key)
        else:
            data = self.storage.get_range(key, byte_range.start, byte_range.end)

        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        return AudioChunk(data=data, size=size, content_type=content_type, byte_range=byte_range)
