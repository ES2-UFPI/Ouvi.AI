"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.stories.repository import SegmentRepository, StoryRepository
from app.modules.stories.importer import MAX_FILE_BYTES, StoryImportError, StoryImportService
from app.modules.stories.schemas import StoryImportRead, StoryRead, StorySegmentsRead
from app.modules.stories.service import StoryService
from app.modules.users.models import User

router = APIRouter(prefix="/stories", tags=["stories"])


def get_story_service(db: Session = Depends(get_db)) -> StoryService:
    return StoryService(StoryRepository(db), SegmentRepository(db))


@router.get("", response_model=list[StoryRead])
def list_stories(
    user: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
) -> list[StoryRead]:
    """Histórias do catálogo e as enviadas pelo usuário logado, para escolher no Filtro de Audição."""
    return [
        StoryRead(
            id=story.id,
            title=story.title,
            description=story.description,
            segment_count=total,
            is_mine=story.owner_id == user.id,
        )
        for story, total in service.list_stories_with_counts(user.id)
    ]


@router.post(
    "/import",
    response_model=StoryImportRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "Arquivo vazio, grande demais, de tipo não suportado ou mal formatado"}},
)
async def import_story(
    file: UploadFile = File(..., description="`.txt` (inglês e português, linha a linha) ou `.json` do seed"),
    title: str | None = Form(None, description="Título; sem ele, vale o do arquivo"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryImportRead:
    """Envia um texto bilíngue do usuário (US18). A história é anotada na hora e fica visível só para ele."""
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        result = StoryImportService(db).import_file(user.id, file.filename or "", data, title)
    except StoryImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    story = result.story
    return StoryImportRead(
        story=StoryRead(
            id=story.id,
            title=story.title,
            description=story.description,
            segment_count=result.segments,
            is_mine=True,
        ),
        annotations=result.annotations,
        aligned=result.aligned,
    )


@router.get("/{story_id}/segments", response_model=StorySegmentsRead)
def get_story_segments(
    story_id: int,
    # Literal: valor desconhecido vira 422 e o /docs lista as opções. Acompanha os tipos do DetectorFactory.
    kind: Literal["phrasal_verb"] | None = Query(None, description="Só anotações deste tipo"),
    aligned_only: bool = Query(False, description="Só anotações que já têm equivalente em português"),
    user: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
) -> StorySegmentsRead:
    """Frases da história em ordem, cada uma com seus trechos candidatos à troca de idioma.

    Sem paginação: as histórias têm algumas dezenas de frases (limite de projeto: ~200).
    """
    try:
        story, segments = service.get_segments(story_id, kind=kind, aligned_only=aligned_only)
        if story.owner_id is not None and story.owner_id != user.id:
            raise LookupError(story_id)  # história particular de outro usuário: como se não existisse
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="História não encontrada")
    return StorySegmentsRead(story=story, segments=segments)
