"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from app.modules.filters.service import FilterService
from app.modules.progress.models import PlaybackProgress
from app.modules.progress.repository import PlaybackProgressRepository
from app.modules.progress.schemas import ProgressWrite
from app.modules.stories.service import StoryService
from app.modules.users.models import User


class StoryNotFoundError(Exception):
    """A história não existe."""


class InvalidSegmentPositionError(Exception):
    """A frase indicada não existe na história (posição além da última frase)."""


class ProgressService:
    """Todas as operações recebem o usuário do token: ninguém lê nem altera o progresso de outro usuário.

    História e filtro são consultados pelos Services dos outros módulos, nunca pelos Repositories deles.
    """

    def __init__(
        self, progress: PlaybackProgressRepository, stories: StoryService, filters: FilterService
    ) -> None:
        self.progress = progress
        self.stories = stories
        self.filters = filters

    def _count_segments(self, story_id: int) -> int:
        try:
            return self.stories.count_segments(story_id)
        except LookupError:
            raise StoryNotFoundError()

    def get(self, user: User, story_id: int) -> PlaybackProgress | None:
        self._count_segments(story_id)
        return self.progress.get(user.id, story_id)

    def save(self, user: User, story_id: int, data: ProgressWrite) -> PlaybackProgress:
        """Cria ou atualiza o progresso e devolve o que ficou valendo no banco.

        Se o `client_time` for mais antigo que o já salvo, nada muda e volta o progresso mais novo.
        """
        if data.segment_position >= self._count_segments(story_id):
            raise InvalidSegmentPositionError()
        if data.filter_id is not None:
            # Levanta FilterNotFoundError se o filtro não existe ou é de outro usuário
            self.filters.get(user, data.filter_id)
        return self.progress.upsert(
            user_id=user.id,
            story_id=story_id,
            segment_position=data.segment_position,
            offset_ms=data.offset_ms,
            client_time=data.client_time,
            filter_id=data.filter_id,
            completed=data.completed,
        )

    def delete(self, user: User, story_id: int) -> None:
        """Apaga o progresso ("Recomeçar"). Não ter progresso para apagar não é erro."""
        self._count_segments(story_id)
        self.progress.delete(user.id, story_id)

    def list_recent(self, user: User, limit: int) -> list[PlaybackProgress]:
        """O "Continuar ouvindo": histórias em andamento do usuário, da mais recente para a mais antiga."""
        return self.progress.list_recent(user.id, limit=limit)
