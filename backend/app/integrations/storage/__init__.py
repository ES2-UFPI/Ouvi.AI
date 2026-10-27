"""Armazenamento de objetos compatível com S3 (MinIO em dev, Cloudflare R2 em produção).

Use sempre a interface `ObjectStorage`, recebida pela dependência `get_storage`. O boto3 só é
importado em `s3.py`, e só quando a implementação S3 é escolhida.
"""
from app.integrations.storage.base import (
    InvalidByteRange,
    ObjectStorage,
    StorageError,
    StorageObjectNotFound,
)
from app.integrations.storage.factory import create_storage, get_storage
from app.integrations.storage.memory import InMemoryStorage

__all__ = [
    "InMemoryStorage",
    "InvalidByteRange",
    "ObjectStorage",
    "StorageError",
    "StorageObjectNotFound",
    "create_storage",
    "get_storage",
]
