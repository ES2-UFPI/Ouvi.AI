"""Testes do AudioUrlSigner. Não usam banco nem MinIO: a hora é controlada por um relógio falso."""
from urllib.parse import parse_qs

import pytest

from app.modules.audio.signing import (
    AudioSignatureError,
    AudioUrlSigner,
    ExpiredSignature,
    InvalidSignature,
)

KEY = "samples/tom-440-660hz.wav"
NOW = 1_800_000_000


class FakeClock:
    def __init__(self, now: float = NOW) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def signer(clock):
    return AudioUrlSigner("segredo-de-teste", ttl_seconds=60, clock=clock)


def verify(signer, params):
    signer.verify(params["key"], int(params["expires"]), params["signature"])


def test_valid_signature(signer):
    verify(signer, signer.sign(KEY))


def test_sign_sets_expiration_from_ttl(signer):
    assert signer.sign(KEY)["expires"] == str(NOW + 60)


def test_still_valid_at_the_last_second(signer, clock):
    params = signer.sign(KEY)
    clock.now = NOW + 60
    verify(signer, params)


def test_expired(signer, clock):
    params = signer.sign(KEY)
    clock.now = NOW + 61
    with pytest.raises(ExpiredSignature):
        verify(signer, params)


@pytest.mark.parametrize(
    "tampered",
    [
        {"key": "samples/outro-audio.wav"},  # troca o arquivo
        {"expires": str(NOW + 999_999)},  # estica o prazo
        {"signature": "0" * 64},  # inventa a assinatura
        {"signature": ""},
    ],
)
def test_tampered(signer, tampered):
    params = {**signer.sign(KEY), **tampered}
    with pytest.raises(InvalidSignature):
        verify(signer, params)


def test_tampered_expiration_is_invalid_even_when_already_expired(signer, clock):
    """Mexer na expiração é adulteração, não importa a hora: a assinatura é conferida primeiro."""
    params = {**signer.sign(KEY), "expires": str(NOW - 10)}
    with pytest.raises(InvalidSignature):
        verify(signer, params)


def test_other_secret_does_not_accept_signature(signer, clock):
    other = AudioUrlSigner("outro-segredo", ttl_seconds=60, clock=clock)
    with pytest.raises(InvalidSignature):
        verify(other, signer.sign(KEY))


def test_both_errors_share_a_base_class():
    assert issubclass(InvalidSignature, AudioSignatureError)
    assert issubclass(ExpiredSignature, AudioSignatureError)


def test_query_string_round_trip(signer):
    """Chaves com espaço, acento e barra sobrevivem à ida e volta pela URL."""
    key = "samples/história do patinho.wav"
    params = {k: v[0] for k, v in parse_qs(signer.query_string(key)).items()}
    assert params["key"] == key
    verify(signer, params)


def test_empty_secret_is_rejected():
    with pytest.raises(ValueError):
        AudioUrlSigner("")
