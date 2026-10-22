"""Modelos SQLAlchemy deste módulo (tabelas do banco)."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ListeningFilter(Base):
    """Filtro de Audição de um usuário: decide quando o áudio troca de idioma.

    As regras ficam em JSONB para novos tipos de trecho entrarem sem migração, ex.:
    {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "medium"}
    """

    __tablename__ = "listening_filters"

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE: apagar o usuário apaga os filtros dele junto
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Ainda sem FK: a tabela de histórias não existe nesta Sprint
    story_id: Mapped[int | None] = mapped_column(Integer)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # onupdate: o SQLAlchemy atualiza a data em todo UPDATE feito pelo ORM
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
