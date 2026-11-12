"""Camada Service: calcula a prévia do texto com as trocas de idioma. Só leitura: sem TTS e sem gravar no banco."""
from dataclasses import dataclass

from pydantic import ValidationError

from app.modules.audio.composer import AudioComposer, ComposedText
from app.modules.filters.schemas import FilterRules
from app.modules.filters.service import FilterService
from app.modules.stories.models import Story
from app.modules.stories.service import StoryService
from app.modules.users.models import User


class FilterOfOtherStoryError(Exception):
    """O filtro foi criado para outra história."""


class InvalidFilterRulesError(Exception):
    """As regras guardadas no filtro não são válidas ou pedem um tipo de trecho sem estratégia de troca."""


@dataclass(frozen=True)
class SegmentPreview:
    id: int
    position: int
    composed: ComposedText


@dataclass(frozen=True)
class StoryPreview:
    story: Story
    rules: FilterRules
    segments: list[SegmentPreview]
    candidates: int

    @property
    def swapped(self) -> int:
        return sum(len(s.composed.swaps) for s in self.segments)


class PreviewService:
    """Entre módulos só pelo Service: pede as frases ao `StoryService` e o filtro ao `FilterService`."""

    def __init__(self, stories: StoryService, filters: FilterService, composer: AudioComposer | None = None) -> None:
        self.stories = stories
        self.filters = filters
        self.composer = composer or AudioComposer()

    def preview(self, user: User, story_id: int, filter_id: int) -> StoryPreview:
        """Levanta LookupError (história inexistente), FilterNotFoundError (filtro inexistente ou de outro
        usuário), FilterOfOtherStoryError ou InvalidFilterRulesError."""
        story, segments = self.stories.get_segments(story_id)
        listening_filter = self.filters.get(user, filter_id)
        if listening_filter.story_id is not None and listening_filter.story_id != story_id:
            raise FilterOfOtherStoryError()

        try:
            rules = FilterRules.model_validate(listening_filter.rules)
        except ValidationError as exc:
            raise InvalidFilterRulesError(str(exc)) from exc

        # A mesma seleção que a geração de áudio usa: o que o usuário vê é o que ele ouve
        try:
            selected = self.composer.select_swaps(
                segments, rules.segment_types, rules.density, rules.word_level, rules.progression
            )
            candidates = self.composer.count_candidates(segments, rules.segment_types, rules.word_level)
        except ValueError as exc:  # inclui UnknownSwapStrategyError (tipo de trecho sem estratégia)
            raise InvalidFilterRulesError(str(exc)) from exc

        return StoryPreview(
            story=story,
            rules=rules,
            segments=[
                SegmentPreview(s.id, s.position, self.composer.compose(s, selected, rules.base_language))
                for s in segments
            ],
            candidates=candidates,
        )
