"""Schemas da prévia do texto com as trocas de idioma (GET /stories/{id}/preview)."""
from pydantic import BaseModel, ConfigDict, Field

from app.modules.filters.schemas import FilterRules


class PreviewStory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    language: str = Field(description="Idioma original do texto da história (en ou pt)")


class SwapRead(BaseModel):
    """Um trecho que muda de idioma na fala. As posições valem para o `text` da frase, no idioma base."""

    model_config = ConfigDict(from_attributes=True)

    start: int = Field(description="Início do trecho no texto da frase, em caracteres")
    end: int = Field(description="Fim do trecho (exclusivo): text[start:end] é o trecho trocado")
    text: str = Field(description="O trecho original, no idioma base (o que aparece na tela)")
    spoken: str = Field(description="O que será falado no lugar dele, no outro idioma")
    lang: str = Field(description="Idioma do trecho falado: en-US ou pt-BR")
    annotation_id: int


class PreviewSegmentRead(BaseModel):
    id: int
    position: int
    text: str = Field(description="Texto da frase no idioma base do filtro, sem marcação")
    swaps: list[SwapRead] = Field(description="Trechos trocados desta frase, em ordem de posição")


class PreviewTotals(BaseModel):
    segments: int = Field(description="Número de frases da história")
    candidates: int = Field(description="Trechos que poderiam ser trocados (têm equivalente), antes da densidade")
    swapped: int = Field(description="Trechos de fato trocados: a soma de `swaps` de todas as frases")


class PreviewRead(BaseModel):
    story: PreviewStory
    rules: FilterRules
    totals: PreviewTotals
    segments: list[PreviewSegmentRead]
