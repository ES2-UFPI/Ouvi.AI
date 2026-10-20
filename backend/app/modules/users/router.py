"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Dados do usuário logado. Também serve de exemplo de rota protegida."""
    return current_user
