"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.filters.models import ListeningFilter
from app.modules.filters.repository import FilterRepository
from app.modules.filters.schemas import FilterRead, FilterWrite
from app.modules.filters.service import FilterNotFoundError, FilterService
from app.modules.users.models import User

# dependencies no router: todas as rotas de /filters exigem token, sem precisar repetir em cada uma
router = APIRouter(
    prefix="/filters", tags=["filters"], dependencies=[Depends(get_current_user)]
)


def get_filter_service(db: Session = Depends(get_db)) -> FilterService:
    return FilterService(FilterRepository(db))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filtro não encontrado")


@router.get("", response_model=list[FilterRead])
def list_filters(
    user: User = Depends(get_current_user),
    service: FilterService = Depends(get_filter_service),
) -> list[ListeningFilter]:
    return service.list(user)


@router.post("", response_model=FilterRead, status_code=status.HTTP_201_CREATED)
def create_filter(
    data: FilterWrite,
    user: User = Depends(get_current_user),
    service: FilterService = Depends(get_filter_service),
) -> ListeningFilter:
    return service.create(user, data)


@router.get("/{filter_id}", response_model=FilterRead)
def get_filter(
    filter_id: int,
    user: User = Depends(get_current_user),
    service: FilterService = Depends(get_filter_service),
) -> ListeningFilter:
    try:
        return service.get(user, filter_id)
    except FilterNotFoundError:
        raise _not_found()


@router.put("/{filter_id}", response_model=FilterRead)
def update_filter(
    filter_id: int,
    data: FilterWrite,
    user: User = Depends(get_current_user),
    service: FilterService = Depends(get_filter_service),
) -> ListeningFilter:
    try:
        return service.update(user, filter_id, data)
    except FilterNotFoundError:
        raise _not_found()


@router.delete("/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_filter(
    filter_id: int,
    user: User = Depends(get_current_user),
    service: FilterService = Depends(get_filter_service),
) -> Response:
    try:
        service.delete(user, filter_id)
    except FilterNotFoundError:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
