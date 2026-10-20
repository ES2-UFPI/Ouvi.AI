"""Modelos SQLAlchemy deste módulo (tabelas do banco)."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """Conta de usuário. A senha nunca é guardada: só o hash argon2."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # unique cria o índice que garante e-mail não repetido e acelera o login
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # server_default: quem preenche a data é o próprio banco, no momento do INSERT
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
