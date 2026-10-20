"""Camada Service: regras de negócio. Usa o Repository, nunca o banco direto."""
from app.core.security import hash_password
from app.modules.auth.schemas import RegisterRequest
from app.modules.users.models import User
from app.modules.users.repository import EmailAlreadyExistsError, UserRepository


class EmailAlreadyRegisteredError(Exception):
    """Já existe uma conta com este e-mail."""


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register(self, data: RegisterRequest) -> User:
        # E-mail é comparado sempre em minúsculas, para "Ana@x.com" e "ana@x.com" serem a mesma conta
        email = data.email.strip().lower()

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
