"""Carrega o modelo do spaCy uma única vez por processo (Singleton)."""
from functools import lru_cache

import spacy
from spacy.language import Language

MODEL_NAME = "en_core_web_sm"


@lru_cache
def get_english_model() -> Language:
    """Carregar o modelo leva cerca de um segundo e ocupa memória, então o objeto é guardado
    e reaproveitado por todos os detectores. O reconhecimento de entidades fica desligado
    porque os detectores não o usam, o que deixa o carregamento e a análise mais rápidos."""
    return spacy.load(MODEL_NAME, exclude=["ner"])
