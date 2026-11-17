"""Modelos SQLAlchemy deste módulo (tabelas do banco)."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlaybackProgress(Base):
    """Onde o usuário parou numa história: a frase e o ponto dentro dela.

    A posição é medida em frase + deslocamento, e não em segundos do arquivo inteiro: cada filtro gera um
    áudio de duração diferente, então "minuto 3" não significaria a mesma coisa com outro filtro. Já
    "frase 12, 1,5 s depois do começo dela" vale para qualquer filtro.
    """

    __tablename__ = "playback_progress"
    __table_args__ = (
        # Um único progresso por usuário e história: gravar de novo atualiza o mesmo registro
        UniqueConstraint("user_id", "story_id", name="uq_playback_progress_user_story"),
        # A lista "Continuar ouvindo" da tela inicial: os do usuário, do mais recente para o mais antigo
        Index("ix_playback_progress_user_client_time", "user_id", "client_time"),
        CheckConstraint("segment_position >= 0", name="ck_playback_progress_segment_position"),
        CheckConstraint("offset_ms >= 0", name="ck_playback_progress_offset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE: apagar o usuário ou a história apaga o progresso
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    # SET NULL: apagar o filtro mantém o progresso (o usuário continua da mesma frase, com outro filtro)
    filter_id: Mapped[int | None] = mapped_column(
        ForeignKey("listening_filters.id", ondelete="SET NULL"), index=True
    )

    # A frase em que parou (a mesma numeração de Segment.position, começando em 0)
    segment_position: Mapped[int]
    # Quantos milissegundos depois do começo da frase
    offset_ms: Mapped[int]
    # Chegou ao fim da história: a próxima abertura começa do início
    completed: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)

    # Quando o front gravou (relógio do navegador). Uma gravação atrasada, com client_time mais antigo,
    # não sobrescreve uma mais nova. Também ordena o "Continuar ouvindo"
    client_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
