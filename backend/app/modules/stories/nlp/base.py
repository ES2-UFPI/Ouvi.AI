"""Contrato dos detectores de anotação (Strategy)."""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class DetectedSpan:
    """Trecho encontrado em um texto. As posições são em caracteres, com fim exclusivo,
    então `texto_original[start:end] == text`."""

    kind: str  # tipo do trecho, ex.: "phrasal_verb"
    lemma: str  # forma de dicionário, ex.: "turn off"
    start: int
    end: int
    text: str  # trecho exato, ex.: "turned the light off"
    extra: dict[str, Any] = field(default_factory=dict)  # ex.: {"separable": True}


class AnnotationDetector(Protocol):
    """Estratégia de detecção: recebe um texto e devolve os trechos candidatos, em ordem."""

    kind: str

    def detect(self, text: str) -> list[DetectedSpan]: ...


class UnknownDetectorError(ValueError):
    """Pediram um tipo de detector que não existe."""
