"""Fábrica de detectores (Factory Method): escolhe a estratégia pelo tipo de trecho."""
from collections.abc import Callable

from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB
from app.modules.stories.nlp.base import AnnotationDetector, UnknownDetectorError
from app.modules.stories.nlp.difficult_words import DifficultWordDetector
from app.modules.stories.nlp.phrasal_verbs import PhrasalVerbDetector


class DetectorFactory:
    # Um novo tipo de trecho entra aqui com uma linha. O vocabulário avançado (US11) não tem detector próprio:
    # reaproveita as anotações de palavras difíceis do nível avançado (veja AdvancedVocabularyStrategy)
    _registry: dict[str, Callable[[], AnnotationDetector]] = {
        KIND_PHRASAL_VERB: PhrasalVerbDetector,
        KIND_DIFFICULT_WORD: DifficultWordDetector,
    }

    @classmethod
    def kinds(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def create(cls, kind: str) -> AnnotationDetector:
        try:
            builder = cls._registry[kind]
        except KeyError:
            available = ", ".join(cls.kinds())
            raise UnknownDetectorError(
                f"Tipo de detector desconhecido: {kind!r}. Disponíveis: {available}"
            ) from None
        return builder()
