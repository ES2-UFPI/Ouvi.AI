"""Contrato do armazenamento de objetos (Adapter).

O resto do sistema só conhece `ObjectStorage` e as exceções deste módulo. Nenhum SDK de
fornecedor (boto3, por exemplo) pode ser importado fora de `app/integrations/storage`.
"""
from abc import ABC, abstractmethod


class StorageError(Exception):
    """Falha genérica do armazenamento (serviço fora do ar, credencial errada...)."""


class StorageObjectNotFound(StorageError):
    """A chave pedida não existe no bucket."""


class InvalidByteRange(StorageError):
    """Faixa de bytes impossível para o objeto (ex.: começa depois do fim do arquivo)."""


class ObjectStorage(ABC):
    """Armazenamento de objetos compatível com S3: chaves (ex.: "audio/12.mp3") apontam para bytes."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Grava (ou sobrescreve) o objeto."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Lê o objeto inteiro."""

    @abstractmethod
    def get_range(self, key: str, start: int, end: int) -> bytes:
        """Lê os bytes de `start` até `end`, INCLUSIVE, como no header HTTP `Range: bytes=start-end`.

        Um `end` além do fim do arquivo é cortado no último byte, como o HTTP faz.
        Levanta `InvalidByteRange` se `start` for negativo, maior que `end` ou não couber no arquivo.
        """

    @abstractmethod
    def size(self, key: str) -> int:
        """Tamanho do objeto em bytes."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Apaga o objeto. Apagar uma chave que não existe não é erro (igual ao S3)."""

    @abstractmethod
    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """URL temporária que dá acesso de leitura ao objeto sem credenciais (ex.: para o `<audio>`)."""

    def ensure_bucket(self) -> None:
        """Cria o bucket se ele não existir. Só faz sentido em desenvolvimento."""


def check_range(start: int, end: int) -> None:
    """Validação da faixa que não depende do tamanho do objeto, compartilhada pelas implementações."""
    if start < 0 or end < start:
        raise InvalidByteRange(f"Faixa inválida: bytes={start}-{end}")
