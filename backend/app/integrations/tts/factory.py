"""Fábrica do provedor de TTS: a implementação é escolhida pelas Settings, sem mudar código."""
from collections.abc import Callable
from functools import lru_cache

from app.core.config import FAKE_VOICE_ID, Settings, get_settings
from app.integrations.tts.azure import AzureTTSAdapter
from app.integrations.tts.base import TTSProvider
from app.integrations.tts.fake import FakeTTSProvider


def _build_fake(settings: Settings) -> TTSProvider:
    return FakeTTSProvider()


def _build_azure(settings: Settings) -> TTSProvider:
    # Falta de configuração derruba a subida da API, com o nome da variável (e nunca o valor da chave)
    missing = [name for name, value in (("TTS_API_KEY", settings.tts_api_key), ("TTS_REGION", settings.tts_region))
               if not value]
    if missing:
        raise ValueError(f"TTS_PROVIDER=azure precisa de {' e '.join(missing)} no ambiente (ou no backend/.env)")
    # A voz padrão é a do provedor falso: o Azure recusaria com 400 só na primeira síntese
    # (vale para as duas vozes por idioma base: cada uma cai na TTS_VOICE_ID quando não é definida)
    if any(not settings.voice_for(lang) or settings.voice_for(lang) == FAKE_VOICE_ID for lang in ("pt", "en")):
        raise ValueError(
            "TTS_PROVIDER=azure precisa de uma voz do Azure em TTS_VOICE_ID "
            "(ex.: pt-BR-ThalitaMultilingualNeural), ou em TTS_VOICE_ID_PT e TTS_VOICE_ID_EN"
        )
    return AzureTTSAdapter(api_key=settings.tts_api_key, region=settings.tts_region)


# Um novo fornecedor entra aqui com uma linha
_BUILDERS: dict[str, Callable[[Settings], TTSProvider]] = {
    "fake": _build_fake,
    "azure": _build_azure,
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
