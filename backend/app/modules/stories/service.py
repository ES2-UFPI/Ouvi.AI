"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from sqlalchemy.orm import Session

from app.modules.stories.models import Segment, Story
from app.modules.stories.repository import SegmentRepository, StoryRepository


class StoryService:
    def __init__(self, stories: StoryRepository, segments: SegmentRepository) -> None:
        self.stories = stories
        self.segments = segments

    @classmethod
    def from_session(cls, db: Session) -> "StoryService":
        """Monta o Service sobre uma sessão. Outros módulos usam isto e não conhecem os repositórios daqui."""
        return cls(StoryRepository(db), SegmentRepository(db))

    def list_stories(self) -> list[Story]:
        return self.stories.list_all()

    def list_stories_with_counts(self, user_id: int | None = None) -> list[tuple[Story, int]]:
        """Cada história com o número de frases (uma consulta a mais, não uma por história).

        Com `user_id`, só o catálogo e as histórias enviadas por esse usuário (US18)."""
        counts = self.segments.count_by_stories()
        stories = self.stories.list_all() if user_id is None else self.stories.list_visible(user_id)
        return [(story, counts.get(story.id, 0)) for story in stories]

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

    def get_segment(self, segment_id: int) -> Segment:
        """Uma frase pelo id. Levanta LookupError se ela não existe."""
        segment = self.segments.get(segment_id)
        if segment is None:
            raise LookupError(f"Frase {segment_id} não encontrada")
        return segment

    def count_segments(self, story_id: int) -> int:
        """Quantas frases a história tem (ex.: o progresso valida a posição da frase com isto).

        Levanta LookupError se a história não existe.
        """
        if self.stories.get_by_id(story_id) is None:
            raise LookupError(f"História {story_id} não encontrada")
        return self.segments.count_by_story(story_id)
