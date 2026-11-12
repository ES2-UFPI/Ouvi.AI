"""Schemas Pydantic de entrada e saída da API deste módulo."""
from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

# Literal: qualquer valor fora da lista é recusado com 422 antes de chegar ao Service.
# Novos tipos de trecho entram aqui sem migração, porque as regras ficam em JSONB.
BaseLanguage = Literal["pt", "en"]
# `advanced_vocabulary` (US11, Cenário C): as palavras raras da história, faladas em inglês sobre a base português
SegmentType = Literal["phrasal_verbs", "difficult_words", "advanced_vocabulary"]
Density = Literal["low", "medium", "high"]
# Nível das palavras difíceis: `intermediate` troca mais palavras (as pouco frequentes e as raras),
# `advanced` só as raras
WordLevel = Literal["intermediate", "advanced"]


class Scenario(BaseModel):
    """Uma combinação permitida de idioma base e tipos de trecho."""

    base_language: BaseLanguage
    segment_types: list[SegmentType]
    # Níveis aceitos neste cenário. Lista vazia: o cenário não usa nível e `word_level` deve ficar ausente.
    word_levels: list[WordLevel]
    description: str


# Tabela ÚNICA das combinações permitidas: a API valida com ela e o front a lê em GET /filters/options.
# Um novo cenário entra aqui com uma linha, sem mexer na validação. Um idioma base pode ter mais de um
# cenário (A e C são ambos em português): os tipos aceitos para ele são a união dos cenários.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        base_language="pt",
        segment_types=["phrasal_verbs"],
        word_levels=[],
        description="Cenário A: história em português com os phrasal verbs falados em inglês",
    ),
    Scenario(
        base_language="en",
        segment_types=["difficult_words"],
        word_levels=list(get_args(WordLevel)),
        description="Cenário B: história em inglês com as palavras difíceis faladas em português",
    ),
    Scenario(
        base_language="pt",
        segment_types=["advanced_vocabulary"],
        word_levels=[],
        description="Cenário C: história em português com o vocabulário avançado falado em inglês",
    ),
)


def scenarios_for(base_language: str) -> list[Scenario]:
    return [s for s in SCENARIOS if s.base_language == base_language]


def allowed_segment_types(base_language: str) -> list[SegmentType]:
    """Tipos de trecho aceitos com o idioma base: a união dos cenários dele, na ordem da tabela."""
    types: list[SegmentType] = []
    for scenario in scenarios_for(base_language):
        types.extend(t for t in scenario.segment_types if t not in types)
    return types


def allowed_word_levels(base_language: str) -> list[WordLevel]:
    levels: list[WordLevel] = []
    for scenario in scenarios_for(base_language):
        levels.extend(level for level in scenario.word_levels if level not in levels)
    return levels


class StoredFilterRules(BaseModel):
    """Regras como estão guardadas na coluna JSONB `rules`, sem conferir as combinações.

    Usada na LEITURA: um filtro salvo antes da tabela de combinações (ex.: `en` com `phrasal_verbs`)
    continua sendo listado e lido, em vez de quebrar a resposta. Gravar exige `FilterRules`.
    """

    base_language: BaseLanguage
    # min_length=1: não é possível salvar sem pelo menos um tipo de trecho (critério da US04)
    segment_types: list[SegmentType] = Field(min_length=1)
    density: Density
    word_level: WordLevel | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_level(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # Sem nível, a chave nem aparece: as regras do Cenário A (e o hash do cache de áudio) ficam iguais
        # às de antes deste campo existir
        data = handler(self)
        if data.get("word_level") is None:
            data.pop("word_level", None)
        return data


class FilterRules(StoredFilterRules):
    """Regras do Filtro de Audição, conferidas contra a tabela de combinações permitidas (`SCENARIOS`)."""

    @model_validator(mode="after")
    def _check_combination(self) -> "FilterRules":
        allowed_types = allowed_segment_types(self.base_language)
        if not allowed_types:  # pragma: no cover - hoje todo idioma base tem cenário
            raise ValueError(f"o idioma base {self.base_language!r} ainda não tem nenhum cenário disponível")

        invalid = [t for t in self.segment_types if t not in allowed_types]
        if invalid:
            allowed = ", ".join(allowed_types)
            raise ValueError(
                f"combinação não disponível: idioma base {self.base_language!r} com {', '.join(invalid)}. "
                f"Com idioma base {self.base_language!r} os tipos aceitos são: {allowed}"
            )

        word_levels = allowed_word_levels(self.base_language)
        if word_levels and self.word_level is None:
            levels = ", ".join(word_levels)
            raise ValueError(f"word_level é obrigatório com idioma base {self.base_language!r} ({levels})")
        if not word_levels and self.word_level is not None:
            raise ValueError(f"word_level não se aplica ao idioma base {self.base_language!r}: remova o campo")
        return self


class FilterWrite(BaseModel):
    """Corpo do POST e do PUT. O PUT substitui o filtro inteiro, por isso usa o mesmo schema."""

    story_id: int | None = None
    rules: FilterRules


class FilterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int | None
    rules: StoredFilterRules
    created_at: datetime
    updated_at: datetime


class FilterOptions(BaseModel):
    """Resposta de GET /filters/options: o que o front pode oferecer no Filtro de Audição."""

    scenarios: list[Scenario]
    densities: list[Density]
    word_levels: list[WordLevel]
