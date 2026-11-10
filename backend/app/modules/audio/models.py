"""Modelos SQLAlchemy deste módulo (tabelas do banco)."""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Estados da geração de uma frase. É texto com CHECK (e não enum do banco), como o `kind` das anotações
STATUS_PENDING = "pending"  # na fila, ainda não começou
STATUS_GENERATING = "generating"  # um worker está sintetizando agora
STATUS_READY = "ready"  # o arquivo está no armazenamento
STATUS_FAILED = "failed"  # falhou de vez (as novas tentativas do TTS já se esgotaram)
STATUSES = (STATUS_PENDING, STATUS_GENERATING, STATUS_READY, STATUS_FAILED)


class AudioAsset(Base):
    """Áudio de uma frase, composto por um conjunto de regras de filtro e falado por uma voz.

    O áudio depende das *regras* do filtro (pelo `rules_hash`), e não do filtro em si: dois filtros com as
    mesmas regras usam o mesmo áudio. O arquivo fica no armazenamento de objetos; aqui só a chave dele.
    """

    __tablename__ = "audio_assets"
    __table_args__ = (
        # Uma frase tem um único áudio por regras e voz. Também é o índice da busca do get_or_create
        UniqueConstraint("segment_id", "rules_hash", "voice_id", name="uq_audio_assets_segment_rules_voice"),
        # O status de uma história inteira (a tela de progresso da geração)
        Index("ix_audio_assets_story_rules_voice", "story_id", "rules_hash", "voice_id"),
        CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'failed')", name="ck_audio_assets_status"
        ),
        # Pronto sem arquivo não existe: o player receberia um áudio que não está em lugar nenhum
        CheckConstraint(
            "status <> 'ready' OR "
            "(storage_key IS NOT NULL AND format IS NOT NULL AND duration_ms IS NOT NULL)",
            name="ck_audio_assets_ready_has_file",
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_audio_assets_duration"),
        CheckConstraint("attempts >= 0", name="ck_audio_assets_attempts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE nos dois: apagar a história (ou só a frase) apaga os áudios. O arquivo no armazenamento
    # fica órfão e sai na limpeza do cache (US08)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id", ondelete="CASCADE"))
    # SHA-256 das regras do filtro, em hexadecimal (veja compute_rules_hash no repositório)
    rules_hash: Mapped[str] = mapped_column(String(64))
    voice_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), server_default=STATUS_PENDING, default=STATUS_PENDING)

    # Preenchidos quando fica pronto
    storage_key: Mapped[str | None] = mapped_column(String(500))
    format: Mapped[str | None] = mapped_column(String(10))  # "mp3" ou "wav"
    duration_ms: Mapped[int | None]

    # Último erro (só o texto do TTSError, que nunca traz a chave do fornecedor) e quantas vezes já começou
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(server_default="0", default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Muda a cada transição de estado: é por ele que o reset_stale acha as frases presas em "generating"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
