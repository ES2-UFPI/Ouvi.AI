"""Camada Repository: único ponto de acesso aos dados deste módulo."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.stories.models import Story


class StoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Story]:
        # Ordem fixa por id: a lista não muda de posição entre uma chamada e outra
        return list(self.db.scalars(select(Story).order_by(Story.id)))
