"""Contrato do provedor de TTS, síntese de voz (Adapter).

O resto do sistema só conhece `TTSProvider`, `SynthesisResult` e `TTSError`. Nenhum SDK ou chamada de
rede de fornecedor pode aparecer fora de `app/integrations/tts`, para trocar de fornecedor sem mexer
no resto (e para o pipeline inteiro rodar nos testes com o provedor falso, sem chave nem custo).
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class TTSError(Exception):
    """Falha ao sintetizar. `retryable` diz se vale tentar de novo: tempo esgotado e fornecedor
    sobrecarregado (429 e 5xx) sim; SSML inválido e chave recusada (400 e 401) não."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class SynthesisResult:
    data: bytes  # o arquivo de áudio inteiro
    format: str  # "wav" ou "mp3": vira a extensão do arquivo no armazenamento
    duration_ms: int  # duração do áudio, para o player e para a barra de progresso


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(self, ssml: str, voice_id: str) -> SynthesisResult:
        """Transforma o SSML em áudio com a voz pedida. Levanta `TTSError` se não conseguir."""
        ...
