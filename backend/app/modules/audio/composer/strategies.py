"""Estratégias de troca (Strategy) e a fábrica que escolhe a estratégia pelo tipo de trecho do filtro."""
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol

from app.modules.audio.composer.density import pick_evenly
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB
from app.modules.stories.nlp.levels import LEVEL_INTERMEDIATE, levels_for_filter

if TYPE_CHECKING:
    from app.modules.stories.models import Annotation


class UnknownSwapStrategyError(ValueError):
    """O filtro pede um tipo de trecho para o qual não existe estratégia de troca."""


class SwapStrategy(Protocol):
    kind: str  # tipo de ANOTAÇÃO que a estratégia escolhe (no filtro o tipo tem outro nome)

    def select(self, annotations: "Sequence[Annotation]", density: str) -> set[int]:
        """Ids das anotações que serão trocadas. Recebe as anotações da história inteira, em ordem de aparição."""
        ...


def _is_aligned(annotation: "Annotation") -> bool:
    return annotation.pt_start is not None and annotation.pt_end is not None and annotation.pt_text is not None


class PhrasalVerbStrategy:
    """Troca phrasal verbs. Só entram os que têm equivalente alinhado em português: sem ele não há o
    que trocar nem onde (e a conta da densidade também só considera esses)."""

    kind = KIND_PHRASAL_VERB

    def select(self, annotations: "Sequence[Annotation]", density: str) -> set[int]:
        candidates = [a for a in annotations if a.kind == self.kind and _is_aligned(a)]
        return {candidates[i].id for i in pick_evenly(len(candidates), density)}


class DifficultWordStrategy:
    """Troca palavras difíceis (Cenário B: base inglês, a palavra é falada em português).

    Entram só as alinhadas e do nível pedido no filtro: `intermediate` considera as pouco frequentes e as
    raras; `advanced` só as raras, então troca menos palavras. A densidade vale sobre esses candidatos."""

    kind = KIND_DIFFICULT_WORD

    def __init__(self, word_level: str | None = None) -> None:
        self.levels = levels_for_filter(word_level or LEVEL_INTERMEDIATE)

    def select(self, annotations: "Sequence[Annotation]", density: str) -> set[int]:
        candidates = [
            a
            for a in annotations
            if a.kind == self.kind and _is_aligned(a) and (a.extra or {}).get("level") in self.levels
        ]
        return {candidates[i].id for i in pick_evenly(len(candidates), density)}


class SwapStrategyFactory:
    # O tipo do FILTRO ("phrasal_verbs", no plural) liga à estratégia. Um novo tipo entra aqui com uma linha.
    # Cada construtor recebe as opções do filtro (hoje só `word_level`) e usa as que lhe interessam.
    _registry: dict[str, Callable[[str | None], SwapStrategy]] = {
        "phrasal_verbs": lambda word_level: PhrasalVerbStrategy(),
        "difficult_words": DifficultWordStrategy,
    }

    @classmethod
    def types(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def create(cls, segment_type: str, word_level: str | None = None) -> SwapStrategy:
        try:
            builder = cls._registry[segment_type]
        except KeyError:
            available = ", ".join(cls.types())
            raise UnknownSwapStrategyError(
                f"Tipo de trecho sem estratégia de troca: {segment_type!r}. Disponíveis: {available}"
            ) from None
        return builder(word_level)
