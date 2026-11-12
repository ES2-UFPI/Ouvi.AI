"""Detector de palavras difíceis em inglês, pela frequência de uso (Cenário B, US10)."""
from functools import lru_cache
from pathlib import Path

from spacy.tokens import Token

from app.modules.stories.models import KIND_DIFFICULT_WORD
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.nlp.spacy_model import get_english_model

DATA_DIR = Path(__file__).parent / "data"
FREQUENCY_FILE = DATA_DIR / "en_word_frequency.txt"
EXCLUDE_FILE = DATA_DIR / "difficult_words_exclude.txt"
INCLUDE_FILE = DATA_DIR / "difficult_words_include.txt"

# Escala Zipf (log10 de ocorrências por bilhão de palavras): "house" ≈ 5,7; "tortoise" ≈ 3,3.
# Abaixo de INTERMEDIATE_MAX_ZIPF a palavra é difícil para quem está no nível intermediário;
# abaixo de ADVANCED_MAX_ZIPF ela é rara o bastante para desafiar também quem está no avançado.
INTERMEDIATE_MAX_ZIPF = 4.0
ADVANCED_MAX_ZIPF = 3.4
# Palavras fora do arquivo de frequência (Zipf < 3) recebem este valor: são as mais raras
UNKNOWN_ZIPF = 0.0

LEVEL_INTERMEDIATE = "intermediate"
LEVEL_ADVANCED = "advanced"

# Só palavras de conteúdo. PROPN (nomes próprios), números, pronomes e preposições nunca entram.
CONTENT_POS = frozenset({"NOUN", "VERB", "ADJ", "ADV"})
MIN_LENGTH = 3


@lru_cache
def load_word_frequency(path: Path = FREQUENCY_FILE) -> dict[str, float]:
    """Lê o arquivo `palavra zipf` (uma por linha; # começa um comentário)."""
    result: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        word, zipf = line.split(" ")
        result[word] = float(zipf)
    return result


@lru_cache
def load_word_list(path: Path) -> frozenset[str]:
    """Lê uma lista de lemas (um por linha; # começa um comentário)."""
    lines = (line.split("#", 1)[0].strip().lower() for line in path.read_text(encoding="utf-8").splitlines())
    return frozenset(line for line in lines if line)


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


class DifficultWordDetector:
    """Encontra palavras difíceis: substantivos, verbos, adjetivos e advérbios pouco frequentes no inglês.

    Como funciona:
    1. O spaCy analisa a frase e dá a classe gramatical e o lema de cada palavra.
    2. Ficam só palavras de conteúdo (sem nomes próprios, números e palavras vazias como "the", "very").
    3. A frequência é a MAIOR entre a da forma ("boasted") e a do lema ("boast"): uma flexão rara de uma
       palavra comum não vira palavra difícil.
    4. Abaixo de `INTERMEDIATE_MAX_ZIPF` a palavra é difícil; o nível diz quão rara ela é.

    Listas de exceção (em `nlp/data`, um lema por linha): `difficult_words_exclude.txt` nunca entra
    (ex.: palavras que a frequência marca como raras, mas que um iniciante conhece); `difficult_words_include.txt`
    sempre entra (como `advanced`), mesmo se for frequente.
    """

    kind = KIND_DIFFICULT_WORD

    def __init__(
        self,
        frequency: dict[str, float] | None = None,
        exclude: frozenset[str] | None = None,
        include: frozenset[str] | None = None,
    ) -> None:
        self._frequency = frequency if frequency is not None else load_word_frequency()
        self._exclude = exclude if exclude is not None else load_word_list(EXCLUDE_FILE)
        self._include = include if include is not None else load_word_list(INCLUDE_FILE)
        self._nlp = get_english_model()

    def zipf(self, word: str, lemma: str | None = None) -> float:
        """Frequência Zipf da palavra (a maior entre a forma e o lema)."""
        values = [self._frequency.get(word.lower(), UNKNOWN_ZIPF)]
        if lemma:
            values.append(self._frequency.get(lemma.lower(), UNKNOWN_ZIPF))
        return max(values)

    def detect(self, text: str) -> list[DetectedSpan]:
        if not text or not text.strip():
            return []
        doc = self._nlp(text)
        return [span for token in doc if (span := self._span_for(token, doc.text))]

    def _span_for(self, token: Token, text: str) -> DetectedSpan | None:
        lemma = token.lemma_.lower()
        if lemma in self._exclude or token.lower_ in self._exclude:
            return None
        if not _is_candidate(token):
            return None

        zipf = self.zipf(token.text, lemma)
        if lemma in self._include or token.lower_ in self._include:
            level = LEVEL_ADVANCED
        else:
            level = level_for(zipf)
        if level is None:
            return None

        start, end = token.idx, token.idx + len(token.text)
        return DetectedSpan(
            kind=self.kind,
            lemma=lemma,
            start=start,
            end=end,
            text=text[start:end],
            extra={"zipf": round(zipf, 2), "level": level, "pos": token.pos_},
        )


def _is_candidate(token: Token) -> bool:
    """Palavra de conteúdo, só letras, que não é nome próprio, número nem palavra vazia."""
    if token.pos_ not in CONTENT_POS or not token.is_alpha or token.is_stop or token.like_num:
        return False
    if len(token.text) < MIN_LENGTH:
        return False
    # Maiúscula no meio da frase é quase sempre nome próprio que o modelo pequeno classificou errado
    if token.text[0].isupper() and not token.is_sent_start:
        return False
    return True
