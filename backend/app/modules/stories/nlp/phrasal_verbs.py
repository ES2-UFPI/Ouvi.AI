"""Detector de phrasal verbs em inglês, com spaCy."""
from functools import lru_cache
from pathlib import Path

from spacy.tokens import Token

from app.modules.stories.models import KIND_PHRASAL_VERB
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.nlp.spacy_model import get_english_model

ACCEPTED_FILE = Path(__file__).parent / "data" / "phrasal_verbs.txt"

# Máximo de palavras entre o verbo e a partícula num phrasal verb separável.
# "turned the light off" tem 2; "turned the big old red lamp off" tem 5 e já é improvável.
MAX_GAP = 4


@lru_cache
def load_accepted_phrasal_verbs(path: Path = ACCEPTED_FILE) -> frozenset[str]:
    """Lê a lista de phrasal verbs aceitos (um por linha; # começa um comentário)."""
    lines = (line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines())
    return frozenset(line for line in lines if line and not line.startswith("#"))


class PhrasalVerbDetector:
    """Encontra phrasal verbs (verbo + partícula) e informa se são separáveis.

    Como funciona:
    1. O spaCy analisa a frase e liga cada palavra à que ela modifica.
    2. Procura uma partícula (up, off, away...) ligada a um verbo que vem antes dela.
    3. Só vira anotação se o par "verbo + partícula" estiver na lista de aceitos. É a lista que
       evita falsos positivos como "walked up the hill", em que `up` é preposição.

    O spaCy nem sempre classifica a partícula como `prt`: *flew away* e *ran away* saem como
    advérbio, *held on* como preposição sem objeto e *cracked open* como adjetivo. Por isso a regra
    aceita essas formas, e a lista de aceitos é quem garante a precisão.

    Limitação conhecida: o modelo pequeno do spaCy às vezes erra a análise em frases compostas e trata
    "put on his coat" como expressão preposicional ("on" + objeto), a mesma estrutura de "looked down the
    street". As duas são indistinguíveis pela análise, então esses casos não são detectados.
    """

    kind = KIND_PHRASAL_VERB

    def __init__(self, accepted: frozenset[str] | None = None) -> None:
        self._accepted = accepted if accepted is not None else load_accepted_phrasal_verbs()
        self._particles = frozenset(entry.rsplit(" ", 1)[1] for entry in self._accepted)
        self._nlp = get_english_model()

    def detect(self, text: str) -> list[DetectedSpan]:
        if not text or not text.strip():
            return []
        doc = self._nlp(text)
        candidates = [span for token in doc if (span := self._span_for(token, doc.text))]
        return _resolve_overlaps(candidates)

    def _span_for(self, particle: Token, text: str) -> DetectedSpan | None:
        verb = particle.head
        if verb.pos_ != "VERB" or verb.i >= particle.i:
            return None
        if particle.lower_ not in self._particles or not _acts_as_particle(particle):
            return None

        lemma = f"{verb.lemma_.lower()} {particle.lower_}"
        if lemma not in self._accepted:
            return None

        # O que fica entre o verbo e a partícula (ex.: "the light") tem de pertencer ao verbo
        between = particle.doc[verb.i + 1 : particle.i]
        if len(between) > MAX_GAP or any(t.is_punct or not verb.is_ancestor(t) for t in between):
            return None

        start = verb.idx
        end = particle.idx + len(particle.text)
        return DetectedSpan(
            kind=self.kind,
            lemma=lemma,
            start=start,
            end=end,
            text=text[start:end],
            extra={"separable": len(between) > 0},
        )


def _acts_as_particle(token: Token) -> bool:
    """Diz se a palavra funciona como partícula do verbo, e não como preposição com objeto."""
    if token.dep_ == "prt":
        return True
    if token.dep_ == "prep":
        # Preposição sem objeto é partícula: "held on until spring". Com objeto não é:
        # "walked up the hill".
        return not any(child.dep_ in ("pobj", "pcomp") for child in token.children)
    # Partícula que o spaCy tratou como advérbio ("flew away") ou como resultado ("cracked open")
    return token.dep_ in ("advmod", "oprd", "acomp") and token.pos_ in ("ADV", "ADJ", "ADP", "PART")


def _resolve_overlaps(spans: list[DetectedSpan]) -> list[DetectedSpan]:
    """Se dois trechos se sobrepõem, fica o mais longo. O resultado sai em ordem de posição."""
    kept: list[DetectedSpan] = []
    for span in sorted(spans, key=lambda s: (-(s.end - s.start), s.start)):
        if all(span.end <= other.start or span.start >= other.end for other in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)
