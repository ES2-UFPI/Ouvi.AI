"""Testes do detector de phrasal verbs, da fábrica e do corpus de referência.

Rodam sem banco de dados e sem rede. Precisam do modelo do spaCy, que já vem na imagem Docker.
"""
import json
from pathlib import Path
from unittest import mock

import pytest
import spacy

from app.modules.stories.models import KIND_PHRASAL_VERB
from app.modules.stories.nlp import spacy_model
from app.modules.stories.nlp.base import DetectedSpan, UnknownDetectorError
from app.modules.stories.nlp.factory import DetectorFactory
from app.modules.stories.nlp.phrasal_verbs import (
    ACCEPTED_FILE,
    MAX_GAP,
    PhrasalVerbDetector,
    _resolve_overlaps,
    load_accepted_phrasal_verbs,
)
from app.modules.stories.seed.validation import read_seed_files

CORPUS_FILE = Path(__file__).parent / "data" / "phrasal_verbs_corpus.json"

# Metas da issue para o corpus
MIN_PRECISION = 0.85
MIN_RECALL = 0.80


@pytest.fixture(scope="module")
def detector() -> PhrasalVerbDetector:
    return DetectorFactory.create(KIND_PHRASAL_VERB)


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    return json.loads(CORPUS_FILE.read_text(encoding="utf-8"))["sentences"]


def found(detector, text: str) -> list[tuple[str, str]]:
    return [(d.lemma, d.text) for d in detector.detect(text)]


# ---------- critérios de aceite da issue ----------

def test_verbo_e_particula_juntos(detector):
    spans = detector.detect("He turned off the light.")
    assert len(spans) == 1
    span = spans[0]
    assert (span.kind, span.lemma, span.text) == (KIND_PHRASAL_VERB, "turn off", "turned off")
    assert (span.start, span.end) == (3, 13)
    assert span.extra == {"separable": False}


def test_separavel_cobre_do_verbo_ate_a_particula(detector):
    spans = detector.detect("She turned the light off.")
    assert len(spans) == 1
    assert spans[0].lemma == "turn off"
    assert spans[0].text == "turned the light off"
    assert spans[0].extra == {"separable": True}


def test_verbo_com_preposicao_nao_gera_anotacao(detector):
    assert detector.detect("They walked up the hill.") == []


# ---------- comportamento do detector ----------

def test_posicoes_apontam_para_o_trecho_exato(detector, corpus):
    for item in corpus:
        for span in detector.detect(item["en"]):
            assert item["en"][span.start : span.end] == span.text, item["en"]


def test_varios_na_mesma_frase_saem_em_ordem_e_sem_sobreposicao(detector):
    spans = detector.detect("She woke up, sat down and gave up.")
    assert [s.lemma for s in spans] == ["wake up", "sit down", "give up"]
    assert all(a.end <= b.start for a, b in zip(spans, spans[1:]))


@pytest.mark.xfail(
    strict=True,
    reason="Limitação do modelo pequeno do spaCy: em frase composta ele analisa 'on his coat' como "
    "expressão preposicional e não acha 'put on'. Se este teste passar, o modelo melhorou: remova o xfail.",
)
def test_limitacao_conhecida_phrasal_verb_em_frase_composta(detector):
    spans = detector.detect("He got up, put on his coat and went out.")
    assert [s.lemma for s in spans] == ["get up", "put on", "go out"]


@pytest.mark.parametrize("texto", ["", "   ", "\n\t"])
def test_texto_vazio_nao_gera_anotacao(detector, texto):
    assert detector.detect(texto) == []


def test_aceita_ate_o_limite_de_palavras_entre_verbo_e_particula(detector):
    # "the old red light" tem 4 palavras entre o verbo e a partícula, exatamente o limite
    assert MAX_GAP == 4
    assert found(detector, "She turned the old red light off.") == [("turn off", "turned the old red light off")]


def test_recusa_objeto_longo_demais_entre_verbo_e_particula(detector):
    # 6 palavras no meio: passa do limite, então a frase não gera anotação
    assert found(detector, "She turned the big old red wooden light off.") == []


def test_so_aceita_o_que_esta_na_lista(detector):
    restrito = PhrasalVerbDetector(accepted=frozenset({"turn off"}))
    assert found(restrito, "She gave up and turned off the light.") == [("turn off", "turned off")]


def test_sobreposicao_mantem_o_trecho_mais_longo():
    curto = DetectedSpan(KIND_PHRASAL_VERB, "a b", 4, 8, "xxxx")
    longo = DetectedSpan(KIND_PHRASAL_VERB, "a c", 0, 10, "yyyyyyyyyy")
    solto = DetectedSpan(KIND_PHRASAL_VERB, "d e", 12, 15, "zzz")
    assert _resolve_overlaps([curto, solto, longo]) == [longo, solto]


# ---------- modelo carregado uma vez ----------

def test_modelo_do_spacy_e_carregado_uma_vez_por_processo():
    spacy_model.get_english_model.cache_clear()
    try:
        with mock.patch.object(spacy_model.spacy, "load", wraps=spacy.load) as load:
            primeiro = PhrasalVerbDetector()
            segundo = DetectorFactory.create(KIND_PHRASAL_VERB)
            primeiro.detect("He turned off the light.")
            segundo.detect("She gave up.")
            assert load.call_count == 1
            assert primeiro._nlp is segundo._nlp
    finally:
        spacy_model.get_english_model.cache_clear()


# ---------- fábrica ----------

def test_fabrica_cria_o_detector_pelo_tipo():
    detector = DetectorFactory.create("phrasal_verb")
    assert isinstance(detector, PhrasalVerbDetector)
    assert detector.kind == "phrasal_verb"
    assert DetectorFactory.kinds() == ["phrasal_verb"]


def test_fabrica_levanta_erro_claro_para_tipo_desconhecido():
    with pytest.raises(UnknownDetectorError) as exc:
        DetectorFactory.create("palavra_dificil")
    mensagem = str(exc.value)
    assert "palavra_dificil" in mensagem and "phrasal_verb" in mensagem


# ---------- lista de phrasal verbs aceitos ----------

def entradas_do_arquivo() -> list[str]:
    linhas = [linha.strip() for linha in ACCEPTED_FILE.read_text(encoding="utf-8").splitlines()]
    return [linha for linha in linhas if linha and not linha.startswith("#")]


def test_lista_tem_formato_valido():
    for entrada in entradas_do_arquivo():
        palavras = entrada.split(" ")
        assert len(palavras) == 2, f"{entrada!r}: use o formato 'verbo partícula'"
        assert entrada == entrada.lower(), f"{entrada!r}: use minúsculas"


def test_lista_nao_tem_repeticao_e_tem_cerca_de_150_entradas():
    entradas = entradas_do_arquivo()
    assert len(entradas) == len(set(entradas)), "há entradas repetidas"
    assert 140 <= len(entradas) <= 300
    assert load_accepted_phrasal_verbs() == frozenset(entradas)


def test_lista_cobre_todos_os_phrasal_verbs_do_seed():
    aceitos = load_accepted_phrasal_verbs()
    do_seed = {pv.lemma for s in read_seed_files() for seg in s.segments for pv in seg.phrasal_verbs}
    assert do_seed - aceitos == set()


# ---------- corpus de referência ----------

def test_corpus_atende_aos_requisitos_da_issue(corpus):
    por_categoria = {}
    for item in corpus:
        por_categoria[item["category"]] = por_categoria.get(item["category"], 0) + 1
    com_phrasal = [i for i in corpus if i["expected"]]
    assert len(corpus) >= 30
    assert len(com_phrasal) >= 15
    assert por_categoria["separable"] >= 5
    assert por_categoria["negative"] >= 10
    assert por_categoria["trap"] >= 5
    for item in corpus:
        for esperado in item["expected"]:
            assert esperado["text"] in item["en"], item["id"]


def test_precisao_e_recall_no_corpus(detector, corpus, request):
    tp, fp, fn = 0, [], []
    for item in corpus:
        esperado = {(e["lemma"], e["text"]) for e in item["expected"]}
        obtido = set(found(detector, item["en"]))
        tp += len(esperado & obtido)
        fp += [(item["id"], item["en"], x) for x in sorted(obtido - esperado)]
        fn += [(item["id"], item["en"], x) for x in sorted(esperado - obtido)]

    precisao = tp / (tp + len(fp))
    recall = tp / (tp + len(fn))

    relatorio = [
        f"frases: {len(corpus)} | trechos esperados: {tp + len(fn)} | acertos: {tp}",
        f"precisão: {precisao:.1%} (meta {MIN_PRECISION:.0%}) | recall: {recall:.1%} (meta {MIN_RECALL:.0%})",
    ]
    relatorio += [f"  falso positivo  #{i}: {x} em {en!r}" for i, en, x in fp]
    relatorio += [f"  falso negativo  #{i}: {x} em {en!r}" for i, en, x in fn]
    request.config.corpus_report = relatorio

    assert precisao >= MIN_PRECISION, "\n".join(relatorio)
    assert recall >= MIN_RECALL, "\n".join(relatorio)


# ---------- coerência com o seed ----------

def test_detector_acha_os_mesmos_phrasal_verbs_que_a_equipe_marcou_no_seed(detector):
    """Para cada frase do seed: os phrasal verbs encontrados são exatamente os marcados
    (comparando o lema), e o trecho do detector cabe dentro do trecho marcado no seed.
    O trecho do seed pode ser maior, porque inclui sujeito ou auxiliar quando a troca de idioma
    precisa dele ('they chase me away'). Isso é assunto do alinhamento (#9), não do detector."""
    for story in read_seed_files():
        for numero, seg in enumerate(story.segments, 1):
            esperado = {pv.lemma: pv.en for pv in seg.phrasal_verbs}
            obtido = {d.lemma: d.text for d in detector.detect(seg.en)}
            assert set(obtido) == set(esperado), f"{story.title}, frase {numero}: {seg.en!r}"
            for lemma, trecho in obtido.items():
                assert trecho in esperado[lemma], f"{story.title}, frase {numero}: {lemma!r}"
