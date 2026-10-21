from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# argon2 é o algoritmo de hash de senhas definido para o projeto.
# deprecated="auto" faz o passlib marcar hashes antigos para serem refeitos se os parâmetros mudarem.
_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

TokenType = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    """Token malformado, com assinatura inválida, expirado ou do tipo errado."""


def hash_password(password: str) -> str:
    """Gera o hash argon2 da senha (já com salt aleatório embutido)."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Confere a senha digitada contra o hash guardado."""
    return _pwd_context.verify(password, password_hash)


def _create_token(user_id: int, token_type: TokenType, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),  # o padrão JWT exige que o "sub" seja texto
        "type": token_type,  # impede usar um refresh token onde se espera um access token
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    minutes = get_settings().access_token_expire_minutes
    return _create_token(user_id, "access", timedelta(minutes=minutes))


def create_refresh_token(user_id: int) -> str:
    days = get_settings().refresh_token_expire_days
    return _create_token(user_id, "refresh", timedelta(days=days))


def decode_token(token: str, expected_type: TokenType) -> int:
    """Valida o token e devolve o id do usuário. Lança InvalidTokenError se algo estiver errado."""
    settings = get_settings()
    try:
        # jwt.decode já confere assinatura e expiração; o algoritmo é fixado para evitar troca por "none"
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise InvalidTokenError("tipo de token incorreto")
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
