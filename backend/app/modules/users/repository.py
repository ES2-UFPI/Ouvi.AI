"""Camada Repository: único ponto de acesso aos dados deste módulo."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.users.models import User


class EmailAlreadyExistsError(Exception):
    """O banco recusou o INSERT porque o e-mail já existe (índice único)."""


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def create(self, name: str, email: str, password_hash: str) -> User:
        user = User(name=name, email=email, password_hash=password_hash)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            # Sem o rollback a sessão fica inutilizável depois do erro
            self.db.rollback()
            raise EmailAlreadyExistsError(email) from exc
        # refresh busca no banco o que ele gerou sozinho (id e created_at)
        self.db.refresh(user)
        return user
