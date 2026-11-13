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


class DensityPointRead(BaseModel):
    """Densidade de uma frase da história (US11). Com a progressão crescente, `target` sobe ao longo da
    história; com a fixa, é a mesma em todas as frases."""

    model_config = ConfigDict(from_attributes=True)

    segment_id: int
    position: int
    candidates: int = Field(description="Trechos da frase que podem ser trocados")
    swapped: int = Field(description="Trechos trocados na frase: o mesmo que len(swaps) dela")
    target: float = Field(description="Fração-alvo de trocas nesta altura da história, de 0 a 1 (a curva)")


class PreviewRead(BaseModel):
    story: PreviewStory
    rules: FilterRules
    totals: PreviewTotals
    density_profile: list[DensityPointRead] = Field(
        description="Perfil de densidade por frase, em ordem de posição (o player desenha a faixa com ele)"
    )
    segments: list[PreviewSegmentRead]
