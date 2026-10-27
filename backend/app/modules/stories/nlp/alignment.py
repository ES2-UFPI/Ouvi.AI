"""Alinhamento: dado um trecho em inglês, acha o equivalente na frase em português."""
import json
import re
import unicodedata
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.modules.stories.nlp.base import DetectedSpan

EQUIVALENTS_FILE = Path(__file__).parent / "data" / "pt_equivalents.json"

# Marcador de "algumas palavras aqui" nas formas do dicionário: "deixou ... para trás"
# casa com "deixou a tartaruga para trás". Vale de 1 a 4 palavras no lugar das reticências.
WILDCARD = "..."
MAX_WILDCARD_WORDS = 4


class AnnotationAligner(Protocol):
    """Estratégia de alinhamento. Hoje é um dicionário curado; no futuro pode ser um LLM,
    sem mudar o `TextAnnotator`."""

    name: str

    def align(
        self,
        span: DetectedSpan,
        text_en: str,
        text_pt: str,
        taken: Sequence[tuple[int, int]] = (),
    ) -> tuple[int, int] | None:
        """Devolve (início, fim) do equivalente em `text_pt` (fim exclusivo), ou None se não achar.

        `taken` são trechos do português já usados por outras anotações da mesma frase,
        que não podem ser escolhidos de novo."""
        ...


class EquivalentsFileError(ValueError):
    """O arquivo de equivalentes tem problemas. A mensagem lista todos."""


@lru_cache
def load_pt_equivalents(path: Path = EQUIVALENTS_FILE) -> dict[str, tuple[str, ...]]:
    """Lê `pt_equivalents.json`: cada phrasal verb (lema) aponta para as formas em português."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    result: dict[str, tuple[str, ...]] = {}

    if not isinstance(raw, dict):
        raise EquivalentsFileError("o JSON deve ser um objeto {lema: [formas]}")

    for lemma, forms in raw.items():
        if lemma != lemma.lower().strip() or len(lemma.split(" ")) != 2:
            problems.append(f"{lemma!r}: o lema deve ter a forma 'verbo partícula', em minúsculas")
        if not isinstance(forms, list) or not forms:
            problems.append(f"{lemma!r}: precisa de uma lista não vazia de formas em português")
            continue
        seen: set[str] = set()
        for form in forms:
            if not isinstance(form, str) or not form.strip() or form != form.strip():
                problems.append(f"{lemma!r}: forma inválida {form!r} (vazia ou com espaços nas pontas)")
                continue
            tokens = form.split()
            if tokens[0] == WILDCARD or tokens[-1] == WILDCARD:
                problems.append(f"{lemma!r}: {form!r} não pode começar nem terminar com {WILDCARD!r}")
            folded, _ = _fold(form)
            if folded in seen:
                problems.append(f"{lemma!r}: forma repetida {form!r}")
            seen.add(folded)
        result[lemma] = tuple(forms)

    if problems:
        raise EquivalentsFileError("\n".join(f"- {p}" for p in problems))
    return result


def _fold(text: str) -> tuple[str, list[int]]:
    """Põe em minúsculas e tira os acentos, guardando de onde veio cada letra.

    Devolve o texto "dobrado" e, para cada letra dele, a posição da letra original. Assim a busca
    ignora maiúsculas e acentos e as posições encontradas valem para o texto original."""
    chars: list[str] = []
    origin: list[int] = []
    for i, char in enumerate(text):
        decomposed = unicodedata.normalize("NFD", char)
        base = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
        for c in base:
            chars.append(c)
            origin.append(i)
    return "".join(chars), origin


def _pattern_for(form: str) -> re.Pattern[str]:
    """Transforma uma forma do dicionário numa expressão regular com limites de palavra."""
    folded, _ = _fold(form)
    pattern = ""
    for token in folded.split():
        if token == WILDCARD:
            pattern += rf"(?:\s+[\w-]+){{1,{MAX_WILDCARD_WORDS}}}"
        else:
            pattern += (r"\s+" if pattern else "") + re.escape(token)
    return re.compile(rf"(?<!\w){pattern}(?!\w)")


class DictionaryAligner:
    """Acha o equivalente em português consultando um dicionário curado de formas por phrasal verb.

    Regras da busca:
    - ignora maiúsculas e acentos ("saíram" casa com "SAIRAM");
    - respeita limites de palavra ("sair" não casa dentro de "sairemos");
    - se várias formas casam no mesmo lugar, fica a mais longa ("sentou-se", e não "sentou");
    - se casam em lugares diferentes, fica a mais próxima da posição relativa do trecho no inglês;
    - ignora trechos do português que outra anotação da mesma frase já usou.

    A forma em português deve cobrir os mesmos "pedaços" que o trecho em inglês: o detector acha
    "chase me away" (sem o sujeito), então o equivalente é "me expulsem", e não "eles me expulsem".
    """

    name = "dictionary"

    def __init__(self, equivalents: dict[str, Sequence[str]] | None = None) -> None:
        source = equivalents if equivalents is not None else load_pt_equivalents()
        self._patterns = {lemma: [_pattern_for(form) for form in forms] for lemma, forms in source.items()}

    @property
    def lemmas(self) -> frozenset[str]:
        return frozenset(self._patterns)

    def align(
        self,
        span: DetectedSpan,
        text_en: str,
        text_pt: str,
        taken: Sequence[tuple[int, int]] = (),
    ) -> tuple[int, int] | None:
        patterns = self._patterns.get(span.lemma)
        if not patterns or not text_pt:
            return None

        folded, origin = _fold(text_pt)
        found: set[tuple[int, int]] = set()
        for pattern in patterns:
            for match in pattern.finditer(folded):
                start, end = origin[match.start()], origin[match.end() - 1] + 1
                if not any(start < t_end and end > t_start for t_start, t_end in taken):
                    found.add((start, end))
        if not found:
            return None

        # Um trecho contido em outro mais longo (ex.: "sentou" dentro de "sentou-se") sai da disputa
        candidates = [c for c in found if not any(o != c and o[0] <= c[0] and c[1] <= o[1] for o in found)]

        # Posição relativa no inglês (0 = início da frase, 1 = fim): serve para escolher entre ocorrências
        target = (span.start + span.end) / 2 / max(len(text_en), 1)

        def rank(candidate: tuple[int, int]) -> tuple[float, int, int]:
            center = (candidate[0] + candidate[1]) / 2 / max(len(text_pt), 1)
            return (abs(center - target), -(candidate[1] - candidate[0]), candidate[0])

        return min(candidates, key=rank)

