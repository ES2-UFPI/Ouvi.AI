"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from functools import lru_cache

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.modules.users.models import User
from app.modules.users.repository import EmailAlreadyExistsError, UserRepository


class EmailAlreadyRegisteredError(Exception):
    """Já existe uma conta com este e-mail."""


class InvalidCredentialsError(Exception):
    """E-mail ou senha incorretos."""


class InvalidRefreshTokenError(Exception):
    """Refresh token inválido, expirado ou de um usuário que não existe mais."""


@lru_cache
def _dummy_hash() -> str:
    return hash_password("senha-falsa-para-igualar-o-tempo")


def _normalize_email(email: str) -> str:
    # E-mail é comparado sempre em minúsculas, para "Ana@x.com" e "ana@x.com" serem a mesma conta
    return email.strip().lower()


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register(self, data: RegisterRequest) -> User:
        email = _normalize_email(data.email)

        if self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)

        try:
            return self.users.create(
                name=data.name.strip(),
                email=email,
                password_hash=hash_password(data.password),
            )
        except EmailAlreadyExistsError as exc:
            # Duas requisições simultâneas passam pela checagem acima; o índice único do banco barra a segunda
            raise EmailAlreadyRegisteredError(email) from exc

    def login(self, data: LoginRequest) -> TokenResponse:
        user = self.users.get_by_email(_normalize_email(data.email))

        if user is None:
            # Confere contra um hash falso para levar o mesmo tempo de quando o e-mail existe.
            # Assim ninguém descobre quais e-mails têm conta medindo o tempo da resposta.
            verify_password(data.password, _dummy_hash())
            raise InvalidCredentialsError()

        if not verify_password(data.password, user.password_hash):
            raise InvalidCredentialsError()

        return _issue_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            user_id = decode_token(refresh_token, expected_type="refresh")
        except InvalidTokenError as exc:
            raise InvalidRefreshTokenError() from exc

        # Reconsulta o usuário: se a conta foi apagada, o refresh token antigo deixa de valer
        user = self.users.get_by_id(user_id)
        if user is None:
            raise InvalidRefreshTokenError()

        return _issue_tokens(user)
