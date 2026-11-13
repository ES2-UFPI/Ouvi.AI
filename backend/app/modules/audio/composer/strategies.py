"""Estratégias de troca (Strategy) e a fábrica que escolhe a estratégia pelo tipo de trecho do filtro."""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.modules.audio.composer.density import DensityCurve, pick_evenly
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB
from app.modules.stories.nlp.levels import LEVEL_ADVANCED, LEVEL_INTERMEDIATE, levels_for_filter

if TYPE_CHECKING:
    from app.modules.stories.models import Annotation


class UnknownSwapStrategyError(ValueError):
    """O filtro pede um tipo de trecho para o qual não existe estratégia de troca."""


@dataclass(frozen=True)
class StoryPositions:
    """Frase de cada anotação na história ordenada, para a curva de densidade crescente (US11)."""

    sentence_of: Mapping[int, int]  # id da anotação -> índice da frase (0 a total - 1)
    total: int  # número de frases da história


class SwapStrategy(Protocol):
    kind: str  # tipo de ANOTAÇÃO que a estratégia escolhe (no filtro o tipo tem outro nome)

    def select(
        self, annotations: "Sequence[Annotation]", density: str, positions: StoryPositions | None = None
    ) -> set[int]:
        """Ids das anotações que serão trocadas. Recebe as anotações da história inteira, em ordem de aparição.

        `positions` liga a densidade crescente (`DensityCurve`); sem ele, a densidade é fixa.
        """
        ...


def is_aligned(annotation: "Annotation") -> bool:
    """Só anotações com equivalente em português podem ser trocadas (e contam na densidade)."""
    return annotation.pt_start is not None and annotation.pt_end is not None and annotation.pt_text is not None


def pick(candidates: "Sequence[Annotation]", density: str, positions: StoryPositions | None) -> set[int]:
    """Aplica a densidade (fixa ou crescente) sobre os candidatos, em ordem de aparição."""
    if positions is None:
        indices = pick_evenly(len(candidates), density)
    else:
        sentences = [positions.sentence_of[a.id] for a in candidates]
        indices = DensityCurve(density).select(sentences, positions.total)
    return {candidates[i].id for i in indices}


class PhrasalVerbStrategy:
    """Troca phrasal verbs. Só entram os que têm equivalente alinhado em português: sem ele não há o
    que trocar nem onde (e a conta da densidade também só considera esses)."""

    kind = KIND_PHRASAL_VERB

    def select(
        self, annotations: "Sequence[Annotation]", density: str, positions: StoryPositions | None = None
    ) -> set[int]:
        candidates = [a for a in annotations if a.kind == self.kind and is_aligned(a)]
        return pick(candidates, density, positions)


class DifficultWordStrategy:
    """Troca palavras difíceis (Cenário B: base inglês, a palavra é falada em português).

    Entram só as alinhadas e do nível pedido no filtro: `intermediate` considera as pouco frequentes e as
    raras; `advanced` só as raras, então troca menos palavras. A densidade vale sobre esses candidatos."""

    kind = KIND_DIFFICULT_WORD

    def __init__(self, word_level: str | None = None) -> None:
        self.levels = levels_for_filter(word_level or LEVEL_INTERMEDIATE)

    def select(
        self, annotations: "Sequence[Annotation]", density: str, positions: StoryPositions | None = None
    ) -> set[int]:
        candidates = [
            a
            for a in annotations
            if a.kind == self.kind and is_aligned(a) and (a.extra or {}).get("level") in self.levels
        ]
        return pick(candidates, density, positions)


class AdvancedVocabularyStrategy(DifficultWordStrategy):
    """Troca o vocabulário avançado (Cenário C: base português, a palavra é falada em inglês).

    Reaproveita as anotações de palavras difíceis (a mesma lista de frequência), mas só as RARAS (nível
    avançado) e na direção oposta à do Cenário B: o texto fica em português e a palavra rara é ouvida em
    inglês. Não usa `word_level`: o próprio tipo já é o nível mais alto."""

    def __init__(self) -> None:
        super().__init__(LEVEL_ADVANCED)


class SwapStrategyFactory:
    # O tipo do FILTRO ("phrasal_verbs", no plural) liga à estratégia. Um novo tipo entra aqui com uma linha.
    # Cada construtor recebe as opções do filtro (hoje só `word_level`) e usa as que lhe interessam.
    _registry: dict[str, Callable[[str | None], SwapStrategy]] = {
        "phrasal_verbs": lambda word_level: PhrasalVerbStrategy(),
        "difficult_words": DifficultWordStrategy,
        "advanced_vocabulary": lambda word_level: AdvancedVocabularyStrategy(),
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
