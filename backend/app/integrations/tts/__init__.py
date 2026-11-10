"""Síntese de voz (TTS), com troca de fornecedor por configuração.

Use sempre a interface `TTSProvider`, recebida pela dependência `get_tts_provider`. Em desenvolvimento e
nos testes o provedor é o `FakeTTSProvider`, que gera tons e não precisa de rede nem de chave.
"""
from app.integrations.tts.base import SynthesisResult, TTSError, TTSProvider
from app.integrations.tts.factory import create_tts_provider, get_tts_provider
from app.integrations.tts.fake import FakeCall, FakeTTSProvider

__all__ = [
    "FakeCall",
    "FakeTTSProvider",
    "SynthesisResult",
    "TTSError",
    "TTSProvider",
    "create_tts_provider",
    "get_tts_provider",
]
