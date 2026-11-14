"""AudioComposer: decide O QUE muda de idioma em cada frase e monta o texto com marcação SSML.

Não usa rede, banco nem TTS: recebe frases e anotações e devolve texto, o que o deixa fácil de testar.
O mesmo código serve a qualquer direção: com o português como base, os trechos são falados em inglês;
com o inglês como base (Cenário B), os trechos são falados em português.
"""
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from app.modules.audio.composer.density import PROGRESSION_INCREASING, check_progression, sentence_target
from app.modules.audio.composer.strategies import StoryPositions, SwapStrategyFactory, is_aligned
from app.modules.audio.composer.swap import ComposedText, SentenceDensity, Swap

if TYPE_CHECKING:
    from app.modules.stories.models import Annotation, Segment


@dataclass(frozen=True)
class _Direction:
    base_lang: str  # idioma do <speak>
    swapped_lang: str  # idioma dos trechos trocados (<lang>)

    text_attr: str  # campo da frase com o texto base
    start_attr: str  # posições do trecho no texto base
    end_attr: str
    original_attr: str  # campo da anotação com o trecho no texto base (para conferir as posições)
    spoken_attr: str  # campo da anotação com o que é falado no lugar


_DIRECTIONS = {
    "pt": _Direction("pt-BR", "en-US", "text_pt", "pt_start", "pt_end", "pt_text", "en_text"),
    "en": _Direction("en-US", "pt-BR", "text_en", "en_start", "en_end", "en_text", "pt_text"),
}

# O texto vai DENTRO do XML: além de & < >, as aspas também são escapadas
_ESCAPES = {'"': "&quot;", "'": "&apos;"}


def _escape(text: str) -> str:
    return escape(text, _ESCAPES)


class AudioComposer:
    def select_swaps(
        self,
        segments: "Iterable[Segment]",
        segment_types: Sequence[str],
        density: str,
        word_level: str | None = None,
        progression: str | None = None,
    ) -> set[int]:
        """Ids das anotações que serão trocadas, calculados sobre a HISTÓRIA INTEIRA.

        `word_level` é o nível das palavras difíceis (filtro do Cenário B); os outros tipos o ignoram.
        `progression` (US11): `increasing` aplica a curva de densidade crescente (`DensityCurve`), com
        `density` como a densidade FINAL; ausente ou `fixed`, a densidade é a mesma do começo ao fim.

        A prévia e a geração de áudio devem usar esta mesma função: assim o que o usuário vê é o que ele ouve.
        """
        increasing = check_progression(progression) == PROGRESSION_INCREASING
        ordered_segments = sorted(segments, key=lambda s: s.position)
        # Ordem de aparição (frase, depois posição na frase): faz parte do determinismo da escolha
        ordered = [
            annotation
            for segment in ordered_segments
            for annotation in sorted(segment.annotations, key=lambda a: (a.en_start, a.id))
        ]
        # Frase de cada anotação na história ordenada (só a densidade crescente usa a posição)
        positions = (
            StoryPositions(
                sentence_of={
                    annotation.id: index
                    for index, segment in enumerate(ordered_segments)
                    for annotation in segment.annotations
                },
                total=len(ordered_segments),
            )
            if increasing
            else None
        )
        selected: set[int] = set()
        for segment_type in segment_types:
            selected |= SwapStrategyFactory.create(segment_type, word_level).select(ordered, density, positions)
        return selected

    def count_candidates(
        self, segments: "Iterable[Segment]", segment_types: Sequence[str], word_level: str | None = None
    ) -> int:
        """Quantos trechos da história PODEM ser trocados (têm equivalente em português), antes da densidade.

        Com palavras difíceis, só contam as do nível do filtro (as mesmas que a estratégia considera).
        """
        return sum(self.candidates_per_segment(segments, segment_types, word_level).values())

    def candidates_per_segment(
        self, segments: "Iterable[Segment]", segment_types: Sequence[str], word_level: str | None = None
    ) -> dict[int, int]:
        """Candidatos de cada frase (id da frase -> quantidade), com as mesmas regras de `count_candidates`."""
        strategies = [SwapStrategyFactory.create(segment_type, word_level) for segment_type in segment_types]

        def candidate(a: "Annotation") -> bool:
            for strategy in strategies:
                levels = getattr(strategy, "levels", None)
                if a.kind == strategy.kind and is_aligned(a) and (levels is None or (a.extra or {}).get("level") in levels):
                    return True
            return False

        return {s.id: sum(1 for a in s.annotations if candidate(a)) for s in segments}

    def density_profile(
        self,
        segments: "Iterable[Segment]",
        swapped: Mapping[int, int],
        segment_types: Sequence[str],
        density: str,
        word_level: str | None = None,
        progression: str | None = None,
    ) -> list[SentenceDensity]:
        """Perfil de densidade por frase, em ordem de posição: candidatos, trocas feitas e a fração-alvo.

        `swapped` (id da frase -> trocas) vem do SSML já composto: assim o perfil bate com o que é falado.
        """
        ordered = sorted(segments, key=lambda s: s.position)
        candidates = self.candidates_per_segment(ordered, segment_types, word_level)
        return [
            SentenceDensity(
                segment_id=segment.id,
                position=segment.position,
                candidates=candidates[segment.id],
                swapped=swapped.get(segment.id, 0),
                target=sentence_target(density, progression, index, len(ordered)),
            )
            for index, segment in enumerate(ordered)
        ]

    def compose(self, segment: "Segment", selected: Collection[int], base_language: str) -> ComposedText:
        """Monta o SSML da frase, trocando só as anotações cujos ids estão em `selected`."""
        try:
            direction = _DIRECTIONS[base_language]
        except KeyError:
            valid = ", ".join(_DIRECTIONS)
            raise ValueError(f"idioma base desconhecido: {base_language!r}. Valores válidos: {valid}") from None

        text = getattr(segment, direction.text_attr)
        swaps = self._swaps(segment, selected, direction, text)

        parts: list[str] = []
        cursor = 0
        for swap in swaps:
            parts.append(_escape(text[cursor : swap.start]))
            parts.append(f'<lang xml:lang="{swap.lang}">{_escape(swap.spoken)}</lang>')
            cursor = swap.end
        parts.append(_escape(text[cursor:]))

        ssml = f'<speak version="1.0" xml:lang="{direction.base_lang}">{"".join(parts)}</speak>'
        return ComposedText(ssml=ssml, text=text, swaps=swaps)

    def _swaps(
        self, segment: "Segment", selected: Collection[int], direction: _Direction, text: str
    ) -> list[Swap]:
        swaps: list[Swap] = []
        for annotation in self._chosen(segment, selected):
            start = getattr(annotation, direction.start_attr)
            end = getattr(annotation, direction.end_attr)
            original = getattr(annotation, direction.original_attr)
            if text[start:end] != original:
                # A frase mudou depois da anotação: trocar assim estragaria o texto. Melhor falhar alto.
                raise ValueError(
                    f"As posições da anotação {annotation.id} não batem com o texto da frase {segment.id}: "
                    "reanote a história"
                )
            swaps.append(
                Swap(
                    start=start,
                    end=end,
                    text=original,
                    spoken=getattr(annotation, direction.spoken_attr),
                    lang=direction.swapped_lang,
                    annotation_id=annotation.id,
                )
            )

        # Em ordem de posição; se dois trechos se sobrepõem, vale o primeiro
        swaps.sort(key=lambda s: (s.start, s.end, s.annotation_id))
        kept: list[Swap] = []
        for swap in swaps:
            if not kept or swap.start >= kept[-1].end:
                kept.append(swap)
        return kept

    @staticmethod
    def _chosen(segment: "Segment", selected: Collection[int]) -> "list[Annotation]":
        """As anotações escolhidas desta frase que têm equivalente em português (as outras nunca são trocadas)."""
        return [a for a in segment.annotations if a.id in selected and is_aligned(a)]
