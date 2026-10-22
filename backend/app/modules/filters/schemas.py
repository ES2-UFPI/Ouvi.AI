"""Schemas Pydantic de entrada e saída da API deste módulo."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Literal: qualquer valor fora da lista é recusado com 422 antes de chegar ao Service.
# Novos tipos de trecho entram aqui sem migração, porque as regras ficam em JSONB.
BaseLanguage = Literal["pt", "en"]
SegmentType = Literal["phrasal_verbs"]
Density = Literal["low", "medium", "high"]


class FilterRules(BaseModel):
    """Regras do Filtro de Audição, guardadas na coluna JSONB `rules`."""

    base_language: BaseLanguage
    # min_length=1: não é possível salvar sem pelo menos um tipo de trecho (critério da US04)
    segment_types: list[SegmentType] = Field(min_length=1)
    density: Density


class FilterWrite(BaseModel):
    """Corpo do POST e do PUT. O PUT substitui o filtro inteiro, por isso usa o mesmo schema."""

    story_id: int | None = None
    rules: FilterRules


class FilterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int | None
    rules: FilterRules
    created_at: datetime
    updated_at: datetime
