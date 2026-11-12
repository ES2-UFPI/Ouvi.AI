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
# `advanced_vocabulary` é da US11: já faz parte do contrato, mas ainda não está em nenhuma combinação permitida
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
# Um novo cenário (ex.: US11) entra aqui com uma linha, sem mexer na validação.
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
)


def scenario_for(base_language: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.base_language == base_language), None)


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
        scenario = scenario_for(self.base_language)
        if scenario is None:  # pragma: no cover - hoje todo idioma base tem cenário
            raise ValueError(f"o idioma base {self.base_language!r} ainda não tem nenhum cenário disponível")

        invalid = [t for t in self.segment_types if t not in scenario.segment_types]
        if invalid:
            allowed = ", ".join(scenario.segment_types)
            raise ValueError(
                f"combinação não disponível: idioma base {self.base_language!r} com {', '.join(invalid)}. "
                f"Com idioma base {self.base_language!r} os tipos aceitos são: {allowed}"
            )

        if scenario.word_levels and self.word_level is None:
            levels = ", ".join(scenario.word_levels)
            raise ValueError(f"word_level é obrigatório com idioma base {self.base_language!r} ({levels})")
        if not scenario.word_levels and self.word_level is not None:
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
