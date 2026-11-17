"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.filters.repository import FilterRepository
from app.modules.filters.service import FilterNotFoundError, FilterService
from app.modules.progress.models import PlaybackProgress
from app.modules.progress.repository import DEFAULT_RECENT_LIMIT, PlaybackProgressRepository
from app.modules.progress.schemas import ProgressRead, ProgressWrite
from app.modules.progress.service import (
    InvalidSegmentPositionError,
    ProgressService,
    StoryNotFoundError,
)
from app.modules.stories.repository import SegmentRepository, StoryRepository
from app.modules.stories.service import StoryService
from app.modules.users.models import User

# Sem prefixo: as rotas ficam em /stories/{story_id}/progress e /progress/recent.
# dependencies no router: todas exigem token, sem precisar repetir em cada uma
router = APIRouter(tags=["progress"], dependencies=[Depends(get_current_user)])

MAX_RECENT_LIMIT = 50


def get_progress_service(db: Session = Depends(get_db)) -> ProgressService:
    return ProgressService(
        PlaybackProgressRepository(db),
        StoryService(StoryRepository(db), SegmentRepository(db)),
        FilterService(FilterRepository(db)),
    )


def _story_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="História não encontrada")


@router.get(
    "/stories/{story_id}/progress",
    response_model=ProgressRead,
    responses={204: {"description": "O usuário ainda não tem progresso nesta história"}},
)
def get_progress(
    story_id: int,
    user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> PlaybackProgress | Response:
    """Onde o usuário parou nesta história. 204 (sem corpo) se ele nunca ouviu."""
    try:
        progress = service.get(user, story_id)
    except StoryNotFoundError:
        raise _story_not_found()
    if progress is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return progress


@router.put("/stories/{story_id}/progress", response_model=ProgressRead)
def save_progress(
    story_id: int,
    data: ProgressWrite,
    user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> PlaybackProgress:
    """Grava onde o usuário parou. Devolve o que ficou valendo: uma gravação com `client_time` mais
    antigo que o salvo não sobrescreve nada, e a resposta traz o progresso mais novo."""
    try:
        return service.save(user, story_id, data)
    except StoryNotFoundError:
        raise _story_not_found()
    except InvalidSegmentPositionError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="segment_position além da última frase da história",
        )
    except FilterNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filtro não encontrado")


@router.delete("/stories/{story_id}/progress", status_code=status.HTTP_204_NO_CONTENT)
def delete_progress(
    story_id: int,
    user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> Response:
    """Apaga o progresso ("Recomeçar"). Responde 204 mesmo se não havia progresso."""
    try:
        service.delete(user, story_id)
    except StoryNotFoundError:
        raise _story_not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/progress/recent", response_model=list[ProgressRead])
def list_recent_progress(
    limit: int = Query(DEFAULT_RECENT_LIMIT, ge=1, le=MAX_RECENT_LIMIT),
    user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> list[PlaybackProgress]:
    """O "Continuar ouvindo": histórias em andamento (não concluídas), da mais recente para a mais antiga."""
    return service.list_recent(user, limit)
