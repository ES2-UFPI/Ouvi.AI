"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.audio.preview_schemas import (
    DensityPointRead,
    PreviewRead,
    PreviewSegmentRead,
    PreviewStory,
    PreviewTotals,
    SwapRead,
)
from app.modules.audio.preview_service import (
    FilterOfOtherStoryError,
    InvalidFilterRulesError,
    PreviewService,
    StoryPreview,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.filters.repository import FilterRepository
from app.modules.filters.service import FilterNotFoundError, FilterService
from app.modules.stories.repository import SegmentRepository, StoryRepository
from app.modules.stories.service import StoryService
from app.modules.users.models import User

router = APIRouter(prefix="/stories", tags=["stories"])


def get_preview_service(db: Session = Depends(get_db)) -> PreviewService:
    return PreviewService(
        StoryService(StoryRepository(db), SegmentRepository(db)),
        FilterService(FilterRepository(db)),
    )


def _to_read(preview: StoryPreview) -> PreviewRead:
    return PreviewRead(
        story=PreviewStory.model_validate(preview.story),
        rules=preview.rules,
        totals=PreviewTotals(
            segments=len(preview.segments), candidates=preview.candidates, swapped=preview.swapped
        ),
        density_profile=[DensityPointRead.model_validate(point) for point in preview.density_profile],
        segments=[
            PreviewSegmentRead(
                id=s.id,
                position=s.position,
                text=s.composed.text,
                swaps=[SwapRead.model_validate(swap) for swap in s.composed.swaps],
            )
            for s in preview.segments
        ],
    )


@router.get(
    "/{story_id}/preview",
    response_model=PreviewRead,
    summary="Prévia do texto da história com as trocas de idioma",
    responses={
        401: {"description": "Sem token ou token inválido"},
        404: {"description": "História inexistente, ou filtro inexistente ou de outro usuário"},
        422: {"description": "Filtro de outra história, regras do filtro inválidas ou `filter_id` ausente"},
    },
)
def get_story_preview(
    story_id: int,
    filter_id: int = Query(..., description="Filtro de audição, do usuário logado, que define as trocas"),
    user: User = Depends(get_current_user),
    service: PreviewService = Depends(get_preview_service),
) -> PreviewRead:
    """Mostra **o que vai mudar de idioma** sem gerar áudio: não gasta TTS e não grava nada.

    Devolve todas as frases em ordem, no idioma base do filtro, e em cada uma os trechos trocados com a
    posição no texto (`text[start:end]`) e o que será falado no lugar (`spoken`). A seleção é a mesma que a
    geração de áudio usa, e o mesmo filtro devolve sempre a mesma prévia.
    """
    try:
        preview = service.preview(user, story_id, filter_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="História não encontrada")
    except FilterNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filtro não encontrado")
    except FilterOfOtherStoryError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O filtro é de outra história"
        )
    except InvalidFilterRulesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"As regras do filtro não podem ser usadas: {exc}",
        )
    return _to_read(preview)
