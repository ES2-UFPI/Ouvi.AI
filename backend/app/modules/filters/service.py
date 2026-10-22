"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from app.modules.filters.models import ListeningFilter
from app.modules.filters.repository import FilterRepository
from app.modules.filters.schemas import FilterWrite
from app.modules.users.models import User


class FilterNotFoundError(Exception):
    """O filtro não existe ou pertence a outro usuário."""


class FilterService:
    def __init__(self, filters: FilterRepository) -> None:
        self.filters = filters

    def list(self, user: User) -> list[ListeningFilter]:
        return self.filters.list_by_user(user.id)

    def get(self, user: User, filter_id: int) -> ListeningFilter:
        listening_filter = self.filters.get_by_id(filter_id)
        # Filtro de outro usuário responde igual a inexistente (404), para não revelar quais ids existem
        if listening_filter is None or listening_filter.user_id != user.id:
            raise FilterNotFoundError()
        return listening_filter

    def create(self, user: User, data: FilterWrite) -> ListeningFilter:
        return self.filters.create(user.id, data.story_id, data.rules.model_dump())

    def update(self, user: User, filter_id: int, data: FilterWrite) -> ListeningFilter:
        listening_filter = self.get(user, filter_id)
        return self.filters.update(listening_filter, data.story_id, data.rules.model_dump())

    def delete(self, user: User, filter_id: int) -> None:
        self.filters.delete(self.get(user, filter_id))
