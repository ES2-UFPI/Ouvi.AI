"""Fábrica do armazenamento: a implementação é escolhida pelas Settings, sem mudar código."""
from collections.abc import Callable
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.storage.base import ObjectStorage
from app.integrations.storage.memory import InMemoryStorage


def _build_s3(settings: Settings) -> ObjectStorage:
    # Import tardio: quem usa só a memória (testes) não precisa carregar o boto3
    from app.integrations.storage.s3 import S3Storage

    return S3Storage(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
        public_endpoint=settings.storage_public_endpoint,
    )


def _build_memory(settings: Settings) -> ObjectStorage:
    return InMemoryStorage(bucket=settings.storage_bucket)


# Um novo fornecedor que não seja compatível com S3 entra aqui com uma linha
_BUILDERS: dict[str, Callable[[Settings], ObjectStorage]] = {
    "s3": _build_s3,
    "memory": _build_memory,
}


def create_storage(settings: Settings) -> ObjectStorage:
    try:
        builder = _BUILDERS[settings.storage_backend]
    except KeyError:
        available = ", ".join(sorted(_BUILDERS))
        raise ValueError(
            f"STORAGE_BACKEND desconhecido: {settings.storage_backend!r}. Disponíveis: {available}"
        ) from None
    return builder(settings)


@lru_cache
def get_storage() -> ObjectStorage:
    """Dependência do FastAPI (`Depends(get_storage)`). Uma instância só por processo: o client do
    boto3 é caro de criar e pode ser compartilhado entre requisições.

    Nos testes, troque com `app.dependency_overrides[get_storage] = lambda: InMemoryStorage()`.
    """
    return create_storage(get_settings())
