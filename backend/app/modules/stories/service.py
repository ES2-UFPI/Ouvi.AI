"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from app.modules.stories.models import Segment, Story
from app.modules.stories.repository import SegmentRepository, StoryRepository


class StoryService:
    def __init__(self, stories: StoryRepository, segments: SegmentRepository) -> None:
        self.stories = stories
        self.segments = segments

    def list_stories(self) -> list[Story]:
        return self.stories.list_all()

    def get_segments(
        self, story_id: int, kind: str | None = None, aligned_only: bool = False
    ) -> tuple[Story, list[Segment]]:
        """Frases da história, em ordem, com as anotações de cada uma.

        É a porta de entrada para outros módulos (ex.: áudio) lerem as anotações:
        eles pedem ao Service, nunca ao Repository. Levanta LookupError se a história não existe.
        """
        story = self.stories.get_by_id(story_id)
        if story is None:
            raise LookupError(f"História {story_id} não encontrada")
        return story, self.segments.list_by_story(story_id, kind=kind, aligned_only=aligned_only)
