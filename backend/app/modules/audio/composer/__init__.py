"""Composição do áudio: escolhe o que muda de idioma (Strategy) e monta o SSML de cada frase.

Sem rede, banco ou TTS: o `AudioComposer` só recebe frases e anotações. O pipeline de geração (Facade)
e a prévia do texto usam `select_swaps` e `compose`, para o que o usuário vê ser o que ele ouve.
"""
from app.modules.audio.composer.composer import AudioComposer
from app.modules.audio.composer.density import DENSITY_SHARE
from app.modules.audio.composer.strategies import (
    PhrasalVerbStrategy,
    SwapStrategy,
    SwapStrategyFactory,
    UnknownSwapStrategyError,
)
from app.modules.audio.composer.swap import ComposedText, Swap

__all__ = [
    "AudioComposer",
    "ComposedText",
    "DENSITY_SHARE",
    "PhrasalVerbStrategy",
    "Swap",
    "SwapStrategy",
    "SwapStrategyFactory",
    "UnknownSwapStrategyError",
]
