"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.stories.repository import SegmentRepository, StoryRepository
from app.modules.stories.schemas import StoryRead, StorySegmentsRead
from app.modules.stories.service import StoryService
from app.modules.users.models import User

router = APIRouter(prefix="/stories", tags=["stories"])


def get_story_service(db: Session = Depends(get_db)) -> StoryService:
    return StoryService(StoryRepository(db), SegmentRepository(db))


@router.get("", response_model=list[StoryRead])
def list_stories(
    # A dependência só protege a rota: o usuário em si não é usado na listagem
    _: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
) -> list[StoryRead]:
    """Lista simples das histórias disponíveis, para escolher no Filtro de Audição."""
    return service.list_stories()


@router.get("/{story_id}/segments", response_model=StorySegmentsRead)
def get_story_segments(
    story_id: int,
    # Literal: valor desconhecido vira 422 e o /docs lista as opções. Acompanha os tipos do DetectorFactory.
    kind: Literal["phrasal_verb"] | None = Query(None, description="Só anotações deste tipo"),
    aligned_only: bool = Query(False, description="Só anotações que já têm equivalente em português"),
    _: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
) -> StorySegmentsRead:
    """Frases da história em ordem, cada uma com seus trechos candidatos à troca de idioma.

    Sem paginação: as histórias têm algumas dezenas de frases (limite de projeto: ~200).
    """
    try:
        story, segments = service.get_segments(story_id, kind=kind, aligned_only=aligned_only)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="História não encontrada")
    return StorySegmentsRead(story=story, segments=segments)
