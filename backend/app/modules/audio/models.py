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

    # Arquivo do cache (US08) de onde veio o áudio. Nulo nos áudios ainda não gerados (ou gerados antes do
    # cache). SET NULL: apagar o blob não apaga o áudio da frase; a limpeza do cache o devolve para `pending`
    blob_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_blobs.id", ondelete="SET NULL"), index=True
    )

    # Último erro (só o texto do TTSError, que nunca traz a chave do fornecedor) e quantas vezes já começou
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(server_default="0", default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Muda a cada transição de estado: é por ele que o reset_stale acha as frases presas em "generating"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AudioBlob(Base):
    """Um arquivo de áudio do cache, identificado SÓ pelo conteúdo enviado ao TTS (veja `build_cache_key`).

    Vários `AudioAsset` (de filtros e usuários diferentes) podem apontar para o mesmo blob: a frase sem
    troca de idioma é sintetizada uma única vez para todo mundo.
    """

    __tablename__ = "audio_blobs"
    __table_args__ = (
        # Única: é ela que impede dois arquivos para o mesmo conteúdo (e o alvo do ON CONFLICT)
        UniqueConstraint("cache_key", name="uq_audio_blobs_cache_key"),
        CheckConstraint("duration_ms >= 0", name="ck_audio_blobs_duration"),
        CheckConstraint("size_bytes >= 0", name="ck_audio_blobs_size"),
        CheckConstraint("char_count >= 0", name="ck_audio_blobs_char_count"),
        CheckConstraint("hit_count >= 0", name="ck_audio_blobs_hit_count"),
        CheckConstraint("miss_count >= 0", name="ck_audio_blobs_miss_count"),
        # A limpeza do cache apaga primeiro os menos usados recentemente
        Index("ix_audio_blobs_last_used_at", "last_used_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # SHA-256 em hexadecimal (veja build_cache_key)
    cache_key: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(10))
    duration_ms: Mapped[int]
    size_bytes: Mapped[int]
    # Caracteres enviados ao TTS (o fornecedor cobra por caractere): cada acerto economiza esse tanto
    char_count: Mapped[int]
    # Acertos (reaproveitamentos) e erros (sínteses: a primeira e as regenerações de arquivo sumido)
    hit_count: Mapped[int] = mapped_column(server_default="0", default=0)
    miss_count: Mapped[int] = mapped_column(server_default="1", default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
