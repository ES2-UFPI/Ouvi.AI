"""Camada Repository: único ponto de acesso aos dados deste módulo."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.filters.models import ListeningFilter


class FilterRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user(self, user_id: int) -> list[ListeningFilter]:
        stmt = (
            select(ListeningFilter)
            .where(ListeningFilter.user_id == user_id)
            .order_by(ListeningFilter.id)
        )
        return list(self.db.scalars(stmt))

    def get_by_id(self, filter_id: int) -> ListeningFilter | None:
        return self.db.get(ListeningFilter, filter_id)

    def create(
        self, user_id: int, story_id: int | None, rules: dict[str, Any]
    ) -> ListeningFilter:
        listening_filter = ListeningFilter(user_id=user_id, story_id=story_id, rules=rules)
        self.db.add(listening_filter)
        self.db.commit()
        self.db.refresh(listening_filter)
        return listening_filter

    def update(
        self, listening_filter: ListeningFilter, story_id: int | None, rules: dict[str, Any]
    ) -> ListeningFilter:
        listening_filter.story_id = story_id
        # Atribuir um dict novo (e não alterar o antigo) é o que faz o SQLAlchemy perceber a mudança no JSONB
        listening_filter.rules = rules
        self.db.commit()
        # refresh traz o updated_at que o banco acabou de gravar
        self.db.refresh(listening_filter)
        return listening_filter

    def delete(self, listening_filter: ListeningFilter) -> None:
        self.db.delete(listening_filter)
        self.db.commit()
