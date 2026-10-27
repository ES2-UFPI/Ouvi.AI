"""Schemas Pydantic de entrada e saída da API deste módulo."""
from typing import Any

from pydantic import BaseModel, ConfigDict


class StoryRead(BaseModel):
    # from_attributes permite montar o schema direto a partir do modelo SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None


class StoryHeader(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    language: str


class AnnotationRead(BaseModel):
    """Trecho candidato à troca. Os campos `pt_*` são nulos quando ainda não há equivalente em português."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    lemma: str
    en_start: int
    en_end: int
    en_text: str
    pt_start: int | None
    pt_end: int | None
    pt_text: str | None
    extra: dict[str, Any]


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text_en: str
    text_pt: str
    annotations: list[AnnotationRead]


class StorySegmentsRead(BaseModel):
    story: StoryHeader
    segments: list[SegmentRead]
