"""Composição do áudio: escolhe o que muda de idioma (Strategy) e monta o SSML de cada frase.

Sem rede, banco ou TTS: o `AudioComposer` só recebe frases e anotações. O pipeline de geração (Facade)
e a prévia do texto usam `select_swaps` e `compose`, para o que o usuário vê ser o que ele ouve.
"""
from app.modules.audio.composer.composer import AudioComposer
from app.modules.audio.composer.density import (
    DENSITY_SHARE,
    PROGRESSION_FIXED,
    PROGRESSION_INCREASING,
    PROGRESSIONS,
    DensityCurve,
)
from app.modules.audio.composer.strategies import (
    AdvancedVocabularyStrategy,
    DifficultWordStrategy,
    PhrasalVerbStrategy,
    SwapStrategy,
    StoryPositions,
    SwapStrategyFactory,
    UnknownSwapStrategyError,
)
from app.modules.audio.composer.swap import ComposedText, SentenceDensity, Swap

__all__ = [
    "AdvancedVocabularyStrategy",
    "AudioComposer",
    "ComposedText",
    "DENSITY_SHARE",
    "DifficultWordStrategy",
    "DensityCurve",
    "PROGRESSIONS",
    "PROGRESSION_FIXED",
    "PROGRESSION_INCREASING",
    "PhrasalVerbStrategy",
    "SentenceDensity",
    "Swap",
    "SwapStrategy",
    "SwapStrategyFactory",
    "StoryPositions",
    "UnknownSwapStrategyError",
]
