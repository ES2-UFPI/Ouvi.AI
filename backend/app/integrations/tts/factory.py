"""Fábrica do provedor de TTS: a implementação é escolhida pelas Settings, sem mudar código."""
from collections.abc import Callable
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.tts.base import TTSProvider
from app.integrations.tts.fake import FakeTTSProvider


def _build_fake(settings: Settings) -> TTSProvider:
    return FakeTTSProvider()


# Um novo fornecedor entra aqui com uma linha (o "azure" chega na issue do adaptador real)
_BUILDERS: dict[str, Callable[[Settings], TTSProvider]] = {
    "fake": _build_fake,
}


def create_tts_provider(settings: Settings) -> TTSProvider:
    try:
        builder = _BUILDERS[settings.tts_provider]
    except KeyError:
        available = ", ".join(sorted(_BUILDERS))
        raise ValueError(
            f"TTS_PROVIDER desconhecido: {settings.tts_provider!r}. Disponíveis: {available}"
        ) from None
    return builder(settings)


@lru_cache
def get_tts_provider() -> TTSProvider:
    """Dependência do FastAPI (`Depends(get_tts_provider)`). Uma instância só por processo.

    Nos testes, troque com `app.dependency_overrides[get_tts_provider] = lambda: FakeTTSProvider()`.
    """
    return create_tts_provider(get_settings())
