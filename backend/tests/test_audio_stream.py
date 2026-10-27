"""Testes das rotas /audio/url e /audio/stream. Usam InMemoryStorage: não precisam de banco nem de MinIO."""
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.integrations.storage import InMemoryStorage, get_storage
from app.main import app
from app.modules.audio.router import get_audio_signer
from app.modules.audio.signing import AudioUrlSigner
from app.modules.auth.dependencies import get_current_user

KEY = "samples/teste.mp3"
DATA = bytes(range(256)) * 4  # 1024 bytes, cada posição com valor conhecido
NOW = 1_800_000_000


class FakeClock:
    now = NOW

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def client(clock):
    storage = InMemoryStorage()
    storage.put(KEY, DATA, content_type="audio/mpeg")
    signer = AudioUrlSigner("segredo-de-teste", ttl_seconds=60, clock=clock)

    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_audio_signer] = lambda: signer
    app.dependency_overrides[get_current_user] = lambda: object()
    # Sem `with`: o lifespan (que cria o bucket no MinIO) não roda
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def stream_url(client):
    """URL assinada, do jeito que o front recebe de GET /audio/url."""
    response = client.get("/audio/url", params={"key": KEY})
    assert response.status_code == 200
    return response.json()["url"]


def stream_params(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# --- GET /audio/url ---


def test_audio_url_points_to_stream(stream_url):
    assert urlsplit(stream_url).path == "/audio/stream"
    assert stream_params(stream_url)["key"] == KEY


def test_audio_url_expires_at(client):
    body = client.get("/audio/url", params={"key": KEY}).json()
    assert body["expires_at"].startswith("2027-01-15T08:01:00")  # NOW + 60 s, em UTC


def test_audio_url_missing_key_is_404(client):
    assert client.get("/audio/url", params={"key": "nao/existe.mp3"}).status_code == 404


def test_audio_url_requires_token(client):
    del app.dependency_overrides[get_current_user]
    assert client.get("/audio/url", params={"key": KEY}).status_code == 401


# --- GET /audio/stream ---


def test_stream_without_range_returns_whole_file(client, stream_url):
    response = client.get(stream_url)
    assert response.status_code == 200
    assert response.content == DATA
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "audio/mpeg"


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [
        ("bytes=0-99", 0, 99),  # critério de aceite: exatamente 100 bytes
        ("bytes=500-", 500, 1023),  # faixa aberta
        ("bytes=-200", 824, 1023),  # faixa final
    ],
)
def test_stream_range(client, stream_url, header, start, end):
    response = client.get(stream_url, headers={"Range": header})
    assert response.status_code == 206
    assert response.content == DATA[start : end + 1]
    assert response.headers["content-range"] == f"bytes {start}-{end}/{len(DATA)}"
    assert response.headers["content-length"] == str(end - start + 1)


@pytest.mark.parametrize("header", ["bytes=2000-", "bytes=100-50", "bytes=abc"])
def test_stream_invalid_range_is_416(client, stream_url, header):
    response = client.get(stream_url, headers={"Range": header})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(DATA)}"


@pytest.mark.parametrize(
    "tampered",
    [{"key": "samples/outro.mp3"}, {"expires": str(NOW + 9999)}, {"signature": "0" * 64}],
)
def test_stream_tampered_url_is_403(client, stream_url, tampered):
    params = {**stream_params(stream_url), **tampered}
    assert client.get("/audio/stream", params=params).status_code == 403


def test_stream_expired_url_is_403(client, stream_url, clock):
    clock.now = NOW + 61
    assert client.get(stream_url).status_code == 403


def test_stream_missing_key_is_404(client):
    """Assinatura válida para uma chave que não existe (ex.: o áudio foi apagado depois)."""
    signer = app.dependency_overrides[get_audio_signer]()
    params = signer.sign("nao/existe.mp3")
    assert client.get("/audio/stream", params=params).status_code == 404


def test_stream_does_not_require_token(client, stream_url):
    """O <audio> do navegador não manda Authorization: a URL assinada basta."""
    del app.dependency_overrides[get_current_user]
    assert client.get(stream_url, headers={"Range": "bytes=0-9"}).status_code == 206


def test_stream_is_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/audio/stream" in paths
    assert "/audio/url" in paths
