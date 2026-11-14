"""Testes do detector de palavras difíceis (#102, #109): regras, listas de exceção, fábrica e corpus.

Rodam sem banco e sem rede. Precisam do modelo do spaCy e do arquivo de frequência versionado.
"""
import json
from pathlib import Path

import pytest

from app.modules.stories import candidates
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB
from app.modules.stories.nlp.alignment import DictionaryAligner
from app.modules.stories.nlp.difficult_words import (
    ADVANCED_MAX_ZIPF,
    INTERMEDIATE_MAX_ZIPF,
    LEVEL_ADVANCED,
    LEVEL_INTERMEDIATE,
    DifficultWordDetector,
    level_for,
    levels_for_filter,
    load_word_frequency,
)
from app.modules.stories.nlp.factory import DetectorFactory
from app.modules.stories.seed.validation import read_seed_files

CORPUS_FILE = Path(__file__).parent / "data" / "difficult_words_corpus.json"

# Metas da issue #102 para o corpus
MIN_PRECISION = 0.80
MIN_RECALL = 0.70


@pytest.fixture(scope="module")
def detector() -> DifficultWordDetector:
    return DetectorFactory.create(KIND_DIFFICULT_WORD)


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    return json.loads(CORPUS_FILE.read_text(encoding="utf-8"))["sentences"]


def lemmas(detector, text: str) -> list[str]:
    return [s.lemma for s in detector.detect(text)]


# ---------- fábrica ----------

def test_fabrica_cria_o_detector_e_lista_o_tipo():
    assert isinstance(DetectorFactory.create(KIND_DIFFICULT_WORD), DifficultWordDetector)
    assert DetectorFactory.kinds() == sorted([KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB])


# ---------- critérios de aceite ----------

@pytest.mark.parametrize("frase, palavra", [
    ("The tortoise won the race.", "tortoise"),
    ("She was reluctant to answer.", "reluctant"),
])
def test_palavras_raras_sao_detectadas(detector, frase, palavra):
    assert palavra in lemmas(detector, frase)


@pytest.mark.parametrize("frase", ["The house is big.", "He said hello to his friend."])
def test_palavras_comuns_nao_sao_detectadas(detector, frase):
    assert lemmas(detector, frase) == []


@pytest.mark.parametrize("frase", [
    "Zephyrine visited Ignatius.",  # nomes próprios
    "There were 1999 people and twelve dogs.",  # números
    "It was very much the same as before.",  # palavras vazias
    "",
    "   ",
])
def test_nomes_proprios_numeros_e_palavras_vazias_nunca_entram(detector, frase):
    assert lemmas(detector, frase) == []


def test_trecho_traz_posicao_lema_frequencia_e_nivel(detector):
    texto = "The hare dozed while the tortoise kept walking."
    spans = detector.detect(texto)
    assert [s.lemma for s in spans] == ["hare", "doze", "tortoise"]
    for span in spans:
        assert texto[span.start : span.end] == span.text
        assert span.kind == KIND_DIFFICULT_WORD
        assert span.extra["level"] in (LEVEL_INTERMEDIATE, LEVEL_ADVANCED)
        assert span.extra["zipf"] < INTERMEDIATE_MAX_ZIPF
        assert span.extra["pos"] in ("NOUN", "VERB", "ADJ", "ADV")
    dozed = spans[1]
    assert (dozed.text, dozed.start, dozed.end) == ("dozed", 9, 14)


def test_frequencia_usa_a_maior_entre_forma_e_lema(detector):
    # uma flexão rara de uma palavra comum não vira palavra difícil
    assert detector.zipf("walked", "walk") == detector.zipf("walk")


def test_nivel_pela_frequencia():
    assert level_for(ADVANCED_MAX_ZIPF - 0.01) == LEVEL_ADVANCED
    assert level_for(ADVANCED_MAX_ZIPF) == LEVEL_INTERMEDIATE
    assert level_for(INTERMEDIATE_MAX_ZIPF) is None


def test_niveis_do_filtro():
    assert levels_for_filter("intermediate") == {LEVEL_INTERMEDIATE, LEVEL_ADVANCED}
    assert levels_for_filter("advanced") == {LEVEL_ADVANCED}
    with pytest.raises(ValueError, match="nível desconhecido"):
        levels_for_filter("beginner")


def test_listas_de_excecao_e_inclusao_sao_respeitadas():
    detector = DifficultWordDetector(exclude=frozenset({"tortoise"}), include=frozenset({"house"}))
    achados = {s.lemma: s.extra["level"] for s in detector.detect("The tortoise left the house.")}
    assert "tortoise" not in achados
    assert achados["house"] == LEVEL_ADVANCED


def test_listas_padrao_excluem_interjeicoes(detector):
    assert lemmas(detector, "Okay, hello there.") == []


def test_arquivo_de_frequencia_tem_palavras_comuns_e_valores_coerentes():
    freq = load_word_frequency()
    assert len(freq) > 20_000
    assert freq["the"] > freq["house"] > freq["tortoise"]
    assert all(w.isalpha() and w.islower() for w in list(freq)[:500])


# ---------- comando de candidatos ----------

def test_candidatos_saem_em_ordem_de_aparicao(detector):
    aligner = DictionaryAligner()
    for story in read_seed_files():
        achados = candidates.candidates_for(story, detector, aligner)
        assert achados, story.title
        ordem = [(c.position, c.span.start) for c in achados]
        assert ordem == sorted(ordem)
        avancados = candidates.candidates_for(story, detector, aligner, "advanced")
        assert len(avancados) <= len(achados)


def test_comando_de_candidatos_imprime_cada_historia(capsys):
    assert candidates.main([]) == 0
    saida = capsys.readouterr().out
    for story in read_seed_files():
        assert story.title in saida
    assert "tortoise" in saida


# ---------- corpus de referência ----------

def test_corpus_tem_o_tamanho_minimo(corpus):
    assert len(corpus) >= 30
    for item in corpus:
        for lemma in item["expected"]:
            assert lemma == lemma.lower(), item["id"]


def test_precisao_e_recall_no_corpus(detector, corpus, request):
    tp, fp, fn = 0, [], []
    for item in corpus:
        esperado = set(item["expected"])
        obtido = set(lemmas(detector, item["en"]))
        tp += len(esperado & obtido)
        fp += [(item["id"], item["en"], x) for x in sorted(obtido - esperado)]
        fn += [(item["id"], item["en"], x) for x in sorted(esperado - obtido)]

    precisao = tp / (tp + len(fp))
    recall = tp / (tp + len(fn))
    relatorio = [
        f"frases: {len(corpus)} | palavras esperadas: {tp + len(fn)} | acertos: {tp}",
        f"precisão: {precisao:.1%} (meta {MIN_PRECISION:.0%}) | recall: {recall:.1%} (meta {MIN_RECALL:.0%})",
    ]
    relatorio += [f"  falso positivo  #{i}: {x} em {en!r}" for i, en, x in fp]
    relatorio += [f"  falso negativo  #{i}: {x} em {en!r}" for i, en, x in fn]
    request.config.difficult_words_corpus_report = relatorio

    assert precisao >= MIN_PRECISION, "\n".join(relatorio)
    assert recall >= MIN_RECALL, "\n".join(relatorio)
