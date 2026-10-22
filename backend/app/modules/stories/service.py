"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from app.modules.stories.models import Story
from app.modules.stories.repository import StoryRepository


class StoryService:
    def __init__(self, stories: StoryRepository) -> None:
        self.stories = stories

    def list_stories(self) -> list[Story]:
        return self.stories.list_all()
