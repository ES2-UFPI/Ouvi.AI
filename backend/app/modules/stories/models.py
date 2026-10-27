"""Modelos SQLAlchemy deste módulo (tabelas do banco)."""
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Tipos de anotação. É texto (e não enum do banco) para novos tipos entrarem sem migração.
KIND_PHRASAL_VERB = "phrasal_verb"


class Story(Base):
    """História disponível no catálogo. O texto dela é a junção dos segmentos, em ordem."""

    __tablename__ = "stories"
    __table_args__ = (
        # Só os dois idiomas do produto. Um novo idioma exige alterar esta restrição numa migração.
        CheckConstraint("language IN ('en', 'pt')", name="ck_stories_language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Idioma original do texto ("en" ou "pt"). As histórias já cadastradas são em inglês.
    language: Mapped[str] = mapped_column(String(2), server_default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # passive_deletes: quem apaga os segmentos é o ON DELETE CASCADE do banco, sem carregá-los antes
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="story",
        order_by="Segment.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Segment(Base):
    """Uma frase da história, com o texto nos dois idiomas (um é a tradução do outro)."""

    __tablename__ = "segments"
    __table_args__ = (
        # Duas frases não podem ocupar a mesma posição na mesma história
        UniqueConstraint("story_id", "position", name="uq_segments_story_position"),
        CheckConstraint("position >= 0", name="ck_segments_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), index=True
    )
    # Ordem da frase na história, começando em 0
    position: Mapped[int]
    text_en: Mapped[str] = mapped_column(Text)
    text_pt: Mapped[str] = mapped_column(Text)

    story: Mapped[Story] = relationship(back_populates="segments")
    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="segment",
        order_by="Annotation.en_start",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Annotation(Base):
    """Trecho de uma frase candidato à troca de idioma, localizado no texto em inglês e no em português.

    As posições são em caracteres, com fim exclusivo, então `text_en[en_start:en_end] == en_text`.
    Os campos `pt_*` ficam nulos quando o trecho ainda não tem equivalente em português.
    """

    __tablename__ = "annotations"
    __table_args__ = (
        Index("ix_annotations_segment_kind", "segment_id", "kind"),
        CheckConstraint("en_start >= 0 AND en_end > en_start", name="ck_annotations_en_span"),
        # O equivalente em português é tudo ou nada: ou os três campos, ou nenhum
        CheckConstraint(
            "(pt_start IS NULL AND pt_end IS NULL AND pt_text IS NULL) OR "
            "(pt_start IS NOT NULL AND pt_end IS NOT NULL AND pt_text IS NOT NULL "
            "AND pt_start >= 0 AND pt_end > pt_start)",
            name="ck_annotations_pt_span",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    # Forma de dicionário, ex.: "turn off"
    lemma: Mapped[str] = mapped_column(String(100))
    en_start: Mapped[int]
    en_end: Mapped[int]
    # Trecho exato em inglês, ex.: "turned the light off"
    en_text: Mapped[str] = mapped_column(String(200))
    pt_start: Mapped[int | None]
    pt_end: Mapped[int | None]
    pt_text: Mapped[str | None] = mapped_column(String(200))
    # Dados extras do detector, ex.: {"separable": true}
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", default=dict
    )

    segment: Mapped[Segment] = relationship(back_populates="annotations")

    @property
    def is_aligned(self) -> bool:
        """True quando já se sabe onde está o equivalente em português."""
        return self.pt_start is not None
