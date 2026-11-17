"""Níveis das palavras difíceis. Módulo leve (sem spaCy): o compositor de áudio também o usa."""

# Escala Zipf (log10 de ocorrências por bilhão de palavras): "house" ≈ 5,7; "tortoise" ≈ 3,3.
# Abaixo de INTERMEDIATE_MAX_ZIPF a palavra é difícil para quem está no nível intermediário;
# abaixo de ADVANCED_MAX_ZIPF ela é rara o bastante para desafiar também quem está no avançado.
INTERMEDIATE_MAX_ZIPF = 4.0
ADVANCED_MAX_ZIPF = 3.4

LEVEL_INTERMEDIATE = "intermediate"
LEVEL_ADVANCED = "advanced"


def level_for(zipf: float) -> str | None:
    """Nível da palavra pela frequência, ou None se ela é comum demais para ser difícil."""
    if zipf < ADVANCED_MAX_ZIPF:
        return LEVEL_ADVANCED
    if zipf < INTERMEDIATE_MAX_ZIPF:
        return LEVEL_INTERMEDIATE
    return None


def levels_for_filter(word_level: str) -> frozenset[str]:
    """Níveis de anotação que um filtro seleciona: o intermediário troca as pouco frequentes E as raras;
    o avançado só as raras (por isso troca menos palavras)."""
    if word_level == LEVEL_ADVANCED:
        return frozenset({LEVEL_ADVANCED})
    if word_level == LEVEL_INTERMEDIATE:
        return frozenset({LEVEL_INTERMEDIATE, LEVEL_ADVANCED})
    raise ValueError(f"nível desconhecido: {word_level!r}. Valores válidos: {LEVEL_INTERMEDIATE}, {LEVEL_ADVANCED}")
