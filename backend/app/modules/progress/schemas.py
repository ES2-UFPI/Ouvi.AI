"""Schemas Pydantic de entrada e saída da API deste módulo."""
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProgressWrite(BaseModel):
    """Corpo do PUT: grava onde o usuário parou. Cria na primeira vez e atualiza nas seguintes."""

    # ge=0: posição ou deslocamento negativo é recusado com 422 antes de chegar ao Service
    segment_position: int = Field(ge=0)
    offset_ms: int = Field(ge=0)
    # AwareDatetime: exige fuso horário (ex.: "2026-11-12T10:00:00Z"), senão a comparação com o salvo fica ambígua
    client_time: AwareDatetime
    filter_id: int | None = None
    completed: bool = False


class ProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    story_id: int
    filter_id: int | None
    segment_position: int
    offset_ms: int
    completed: bool
    client_time: datetime
    updated_at: datetime
