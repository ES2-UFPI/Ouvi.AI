"""Armazenamento em memória, para os testes rodarem sem MinIO."""
from urllib.parse import quote

from app.integrations.storage.base import (
    InvalidByteRange,
    ObjectStorage,
    StorageObjectNotFound,
    check_range,
)


class InMemoryStorage(ObjectStorage):
    """Guarda os objetos num dicionário. Tudo se perde quando o processo termina."""

    def __init__(self, bucket: str = "memory") -> None:
        self.bucket = bucket
        self._objects: dict[str, tuple[bytes, str]] = {}  # chave -> (bytes, content_type)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._objects[key] = (bytes(data), content_type)

    def get(self, key: str) -> bytes:
        return self._read(key)

    def get_range(self, key: str, start: int, end: int) -> bytes:
        check_range(start, end)
        data = self._read(key)
        if start >= len(data):
            raise InvalidByteRange(f"Faixa inválida: bytes={start}-{end} (tamanho {len(data)})")
        return data[start : end + 1]  # o fim do HTTP é inclusivo; o do fatiamento, não

    def size(self, key: str) -> int:
        return len(self._read(key))

    def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        # Igual ao S3, não confere se a chave existe. Não há servidor por trás: a URL só
        # identifica o objeto, para os testes conferirem
        return f"memory://{self.bucket}/{quote(key)}?expires_in={expires_in}"

    def _read(self, key: str) -> bytes:
        try:
            return self._objects[key][0]
        except KeyError:
            raise StorageObjectNotFound(key) from None
