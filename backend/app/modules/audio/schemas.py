from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AudioUrlRead(BaseModel):
    """URL que o player coloca direto no `src` da tag `<audio>`, sem precisar de token."""

    url: str
    expires_at: datetime


class AudioGenerationCreate(BaseModel):
    """Corpo do POST /stories/{story_id}/audio."""

    filter_id: int = Field(description="Filtro de audição, do usuário logado, que define as trocas de idioma")


class SegmentAudioStatusRead(BaseModel):
    segment_id: int
    position: int
    status: Literal["pending", "generating", "ready", "failed"]
    duration_ms: int | None = Field(description="Duração do áudio da frase, quando pronto")
    error: str | None = Field(description="Motivo da falha, quando `status` é `failed`")


class AudioGenerationStatusRead(BaseModel):
    """Progresso da geração do áudio de uma história com um filtro. O front consulta por polling."""

    story_id: int
    filter_id: int
    state: Literal["pending", "generating", "ready", "failed"] = Field(
        description=(
            "pending: nada em andamento e ainda há frases sem áudio; generating: geração em andamento; "
            "ready: todas as frases prontas; failed: terminou com alguma frase em falha (um novo POST tenta de novo)"
        )
    )
    total: int = Field(description="Número de frases da história")
    ready: int = Field(description="Frases com áudio pronto")
    failed: int = Field(description="Frases cuja geração falhou")
    segments: list[SegmentAudioStatusRead] = Field(description="Estado de cada frase, em ordem de posição")


class SegmentAudioRead(AudioUrlRead):
    """URL assinada do áudio de uma frase: vai direto no `src` do `<audio>` (com suporte a Range)."""

    segment_id: int
    duration_ms: int
    format: str = Field(description="wav ou mp3")
