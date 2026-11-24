"""Armazenamento de objetos dentro do próprio PostgreSQL.

Serve para hospedar o protótipo num serviço gratuito sem contratar um S3 à parte (ex.: Render): os áudios
ficam numa tabela `storage_objects`, com a chave como identificador. Os áudios do Ouvi.AI são pequenos (dezenas
de KB por frase), então caber no banco não é problema. Em produção de verdade, prefira o `s3`.
"""
from collections.abc import Callable
from urllib.parse import quote

from sqlalchemy import Column, LargeBinary, String, Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.integrations.storage.base import (
    InvalidByteRange,
    ObjectStorage,
    StorageError,
    StorageObjectNotFound,
    check_range,
)

storage_objects = Table(
    "storage_objects",
    Base.metadata,
    Column("key", String(500), primary_key=True),
    Column("data", LargeBinary, nullable=False),
    Column("content_type", String(100), nullable=False),
)


class DatabaseStorage(ObjectStorage):
    """Guarda cada objeto numa linha do Postgres. Cada operação abre e fecha a própria sessão."""

    def __init__(self, session_factory: Callable[[], Session], bucket: str = "database") -> None:
        self._session_factory = session_factory
        self.bucket = bucket

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        stmt = insert(storage_objects).values(key=key, data=bytes(data), content_type=content_type)
        stmt = stmt.on_conflict_do_update(
            index_elements=[storage_objects.c.key],
            set_={"data": stmt.excluded.data, "content_type": stmt.excluded.content_type},
        )
        self._run(lambda db: db.execute(stmt), commit=True)

    def get(self, key: str) -> bytes:
        return self._scalar(key, select(storage_objects.c.data).where(storage_objects.c.key == key))

    def get_range(self, key: str, start: int, end: int) -> bytes:
        check_range(start, end)
        size = self.size(key)
        if start >= size:
            raise InvalidByteRange(f"Faixa inválida: bytes={start}-{end} (tamanho {size})")
        length = min(end, size - 1) - start + 1
        # substring do Postgres começa em 1; lê só o trecho pedido, sem trazer o arquivo inteiro
        column = func.substring(storage_objects.c.data, start + 1, length)
        return bytes(self._scalar(key, select(column).where(storage_objects.c.key == key)))

    def size(self, key: str) -> int:
        column = func.length(storage_objects.c.data)
        return self._scalar(key, select(column).where(storage_objects.c.key == key))

    def delete(self, key: str) -> None:
        self._run(lambda db: db.execute(delete(storage_objects).where(storage_objects.c.key == key)), commit=True)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        # Não há servidor de arquivos por trás: o player usa a rota assinada da API (`GET /audio/stream`)
        return f"database://{self.bucket}/{quote(key)}?expires_in={expires_in}"

    # ---------- auxiliares ----------

    def _scalar(self, key: str, stmt):
        value = self._run(lambda db: db.execute(stmt).scalar_one_or_none())
        if value is None:
            raise StorageObjectNotFound(key)
        return bytes(value) if isinstance(value, memoryview) else value

    def _run(self, action, commit: bool = False):
        try:
            with self._session_factory() as db:
                result = action(db)
                if commit:
                    db.commit()
                return result
        except SQLAlchemyError as exc:
            raise StorageError(f"Falha no armazenamento do banco: {exc}") from exc
