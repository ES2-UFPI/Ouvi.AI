"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.stories.repository import StoryRepository
from app.modules.stories.schemas import StoryRead
from app.modules.stories.service import StoryService
from app.modules.users.models import User

router = APIRouter(prefix="/stories", tags=["stories"])


def get_story_service(db: Session = Depends(get_db)) -> StoryService:
    return StoryService(StoryRepository(db))


@router.get("", response_model=list[StoryRead])
def list_stories(
    # A dependência só protege a rota: o usuário em si não é usado na listagem
    _: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
) -> list[StoryRead]:
    """Lista simples das histórias disponíveis, para escolher no Filtro de Audição."""
    return service.list_stories()
