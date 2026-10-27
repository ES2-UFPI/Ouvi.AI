"""Contrato do armazenamento de objetos.

Os mesmos testes rodam na `InMemoryStorage` e na `S3Storage`, para garantir que as duas se
comportam igual. A versão S3 precisa do MinIO no ar (docker compose up -d) e é pulada sem ele.
"""
import uuid
from urllib.request import Request, urlopen

import pytest

from app.core.config import Settings
from app.integrations.storage import (
    InMemoryStorage,
    InvalidByteRange,
    ObjectStorage,
    StorageError,
    StorageObjectNotFound,
    create_storage,
)

DATA = bytes(range(256)) * 4  # 1024 bytes, cada posição com valor conhecido
TEST_BUCKET = "ouveai-tests"  # separado do bucket da aplicação


_minio_available: bool | None = None  # testado uma vez só; sem MinIO cada tentativa leva segundos


def _s3_storage() -> ObjectStorage:
    global _minio_available
    storage = create_storage(Settings(storage_backend="s3", storage_bucket=TEST_BUCKET))
    if _minio_available is None:
        try:
            storage.ensure_bucket()
            _minio_available = True
        except StorageError:
            _minio_available = False
    if not _minio_available:
        pytest.skip("MinIO indisponível (suba com: docker compose up -d)")
    return storage


@pytest.fixture(params=["memory", "s3"])
def storage(request):
    return InMemoryStorage() if request.param == "memory" else _s3_storage()


@pytest.fixture
def key(storage):
    """Chave única por teste, apagada no final."""
    key = f"tests/{uuid.uuid4().hex}.bin"
    yield key
    storage.delete(key)


@pytest.fixture
def stored(storage, key):
    storage.put(key, DATA, content_type="audio/mpeg")
    return key


def test_put_and_get(storage, stored):
    assert storage.get(stored) == DATA


def test_put_overwrites(storage, stored):
    storage.put(stored, b"novo")
    assert storage.get(stored) == b"novo"


def test_size(storage, stored):
    assert storage.size(stored) == len(DATA)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (0, 99, DATA[0:100]),  # bytes=0-99 devolve exatamente 100 bytes
        (500, 500, DATA[500:501]),  # um byte só
        (1000, 1023, DATA[1000:]),  # até o último byte
        (1000, 5000, DATA[1000:]),  # fim além do arquivo é cortado
    ],
)
def test_get_range(storage, stored, start, end, expected):
    assert storage.get_range(stored, start, end) == expected


@pytest.mark.parametrize(("start", "end"), [(1024, 2000), (-1, 10), (10, 5)])
def test_get_range_invalid(storage, stored, start, end):
    with pytest.raises(InvalidByteRange):
        storage.get_range(stored, start, end)


def test_delete(storage, stored):
    storage.delete(stored)
    with pytest.raises(StorageObjectNotFound):
        storage.get(stored)


def test_delete_missing_key_is_not_an_error(storage, key):
    storage.delete(key)


@pytest.mark.parametrize("operation", ["get", "size", "get_range"])
def test_missing_key_raises_not_found(storage, key, operation):
    args = (key, 0, 10) if operation == "get_range" else (key,)
    with pytest.raises(StorageObjectNotFound):
        getattr(storage, operation)(*args)


def test_presigned_url_contains_key(storage, stored):
    assert stored.split("/")[-1] in storage.presigned_url(stored, expires_in=60)


def test_presigned_url_is_readable_with_range():
    """Só S3: a URL assinada abre sem credenciais e respeita o header Range."""
    storage = _s3_storage()
    key = f"tests/{uuid.uuid4().hex}.bin"
    storage.put(key, DATA)
    try:
        request = Request(storage.presigned_url(key, expires_in=60), headers={"Range": "bytes=0-99"})
        with urlopen(request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == f"bytes 0-99/{len(DATA)}"
            assert response.read() == DATA[:100]
    finally:
        storage.delete(key)


def test_wrong_credentials_do_not_leak_boto_exceptions():
    _s3_storage()  # pula se o MinIO não estiver no ar
    storage = create_storage(
        Settings(storage_backend="s3", storage_bucket=TEST_BUCKET, storage_secret_key="errada")
    )
    with pytest.raises(StorageError) as exc_info:
        storage.get("qualquer")
    assert type(exc_info.value).__module__.startswith("app.integrations.storage")


def test_unreachable_endpoint_raises_storage_error():
    # Porta 1 não tem nada escutando: o boto3 falha ao conectar, sem precisar de MinIO
    storage = create_storage(
        Settings(storage_backend="s3", storage_endpoint="http://127.0.0.1:1", storage_bucket=TEST_BUCKET)
    )
    with pytest.raises(StorageError):
        storage.get("qualquer")


def test_factory_chooses_by_settings():
    assert isinstance(create_storage(Settings(storage_backend="memory")), InMemoryStorage)
    from app.integrations.storage.s3 import S3Storage

    assert isinstance(create_storage(Settings(storage_backend="s3")), S3Storage)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        create_storage(Settings(storage_backend="ftp"))
