"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest, service: AuthService = Depends(get_auth_service)
) -> UserRead:
    try:
        return service.register(data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado"
        )


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    try:
        return service.login(data)
    except InvalidCredentialsError:
        # A mesma mensagem para e-mail inexistente e senha errada, para não revelar quais contas existem
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    data: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    try:
        return service.refresh(data.refresh_token)
    except InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
