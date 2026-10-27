"""Dependências do FastAPI para proteger rotas: basta declarar `Depends(get_current_user)`."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import InvalidTokenError, decode_token
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

# Faz o Swagger (/docs) mostrar o botão "Authorize". auto_error=False porque quem responde
# o erro é a função abaixo, para a mensagem e o status serem sempre os mesmos.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Lê o header `Authorization: Bearer <access_token>` e devolve o usuário dono do token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        # expected_type="access": um refresh token não abre rotas protegidas
        user_id = decode_token(credentials.credentials, expected_type="access")
    except InvalidTokenError:
        raise unauthorized

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        # Token válido de uma conta que foi apagada
        raise unauthorized

    return user
