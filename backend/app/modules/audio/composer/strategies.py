"""Estratégias de troca (Strategy) e a fábrica que escolhe a estratégia pelo tipo de trecho do filtro."""
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol

from app.modules.audio.composer.density import pick_evenly
from app.modules.stories.models import KIND_PHRASAL_VERB

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


class SwapStrategyFactory:
    # O tipo do FILTRO ("phrasal_verbs", no plural) liga à estratégia. Um novo tipo entra aqui com uma linha.
    _registry: dict[str, Callable[[], SwapStrategy]] = {
        "phrasal_verbs": PhrasalVerbStrategy,
    }

    @classmethod
    def types(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def create(cls, segment_type: str) -> SwapStrategy:
        try:
            builder = cls._registry[segment_type]
        except KeyError:
            available = ", ".join(cls.types())
            raise UnknownSwapStrategyError(
                f"Tipo de trecho sem estratégia de troca: {segment_type!r}. Disponíveis: {available}"
            ) from None
        return builder()
