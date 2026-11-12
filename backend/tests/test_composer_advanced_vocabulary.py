"""Testes do Cenário C (US11): idioma base português com o vocabulário avançado falado em inglês.

Anotações simuladas (sem banco, sem spaCy, sem rede): as mesmas de palavras difíceis do Cenário B, lidas na
direção oposta.
"""
from dataclasses import dataclass, field
from xml.etree import ElementTree

import pytest

from app.modules.audio.composer import (
    AdvancedVocabularyStrategy,
    AudioComposer,
    SwapStrategyFactory,
    UnknownSwapStrategyError,
)
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB

composer = AudioComposer()
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass
class Anot:
    id: int
    kind: str
    en_start: int
    en_end: int
    en_text: str
    pt_start: int | None
    pt_end: int | None
    pt_text: str | None
    extra: dict = field(default_factory=dict)


@dataclass
class Frase:
    text_en: str
    text_pt: str
    id: int = 1
    position: int = 0
    annotations: list = field(default_factory=list)


def palavra(id, frase, en, pt, nivel="advanced", kind=KIND_DIFFICULT_WORD):
    es = frase.text_en.index(en)
    if pt is None:
        return Anot(id, kind, es, es + len(en), en, None, None, None, {"level": nivel})
    ps = frase.text_pt.index(pt)
    return Anot(id, kind, es, es + len(en), en, ps, ps + len(pt), pt, {"level": nivel})


def historia_simulada(n=20):
    """n frases, cada uma com uma palavra difícil; as pares são 'advanced', as ímpares 'intermediate'."""
    frases = []
    for i in range(n):
        f = Frase(f"The tortoise number {i} won.", f"A tartaruga número {i} venceu.", id=i + 1, position=i)
        f.annotations = [palavra(i + 1, f, "tortoise", "tartaruga", "advanced" if i % 2 == 0 else "intermediate")]
        frases.append(f)
    return frases


# ---------- estratégia e fábrica ----------

def test_fabrica_cria_a_estrategia_de_vocabulario_avancado():
    assert isinstance(SwapStrategyFactory.create("advanced_vocabulary"), AdvancedVocabularyStrategy)
    assert "advanced_vocabulary" in SwapStrategyFactory.types()


def test_vocabulario_avancado_ignora_o_word_level_e_usa_so_as_raras():
    assert SwapStrategyFactory.create("advanced_vocabulary", "intermediate").levels == {"advanced"}


def test_so_as_palavras_raras_e_alinhadas_sao_candidatas():
    frases = historia_simulada(20)
    selecionadas = composer.select_swaps(frases, ["advanced_vocabulary"], "high")
    pares = {i + 1 for i in range(0, 20, 2)}
    assert selecionadas and selecionadas <= pares
    assert composer.count_candidates(frases, ["advanced_vocabulary"]) == 10


def test_sem_equivalente_em_portugues_nao_troca():
    frase = Frase("The tortoise won.", "A tartaruga venceu.")
    frase.annotations = [palavra(1, frase, "tortoise", None)]
    assert composer.select_swaps([frase], ["advanced_vocabulary"], "high") == set()


def test_ssml_do_cenario_c_tem_speak_pt_br_e_lang_en_us():
    frase = Frase("The tortoise won & the hare dozed.", "A tartaruga venceu & a lebre cochilou.")
    frase.annotations = [
        palavra(1, frase, "tortoise", "tartaruga"),
        palavra(2, frase, "dozed", "cochilou", "intermediate"),
    ]
    selecionadas = composer.select_swaps([frase], ["advanced_vocabulary"], "high")
    composto = composer.compose(frase, selecionadas, "pt")

    raiz = ElementTree.fromstring(composto.ssml)
    assert raiz.get(XML_LANG) == "pt-BR"
    assert [(e.text, e.get(XML_LANG)) for e in raiz.iter("lang")] == [("tortoise", "en-US")]
    # o texto exibido continua em português, com o trecho na posição da palavra em português
    troca = composto.swaps[0]
    assert composto.text[troca.start : troca.end] == "tartaruga" and troca.spoken == "tortoise"


def test_fabrica_da_erro_claro_para_tipo_desconhecido():
    with pytest.raises(UnknownSwapStrategyError, match="advanced_vocabulary"):
        SwapStrategyFactory.create("idioms")


def compor_tudo(frase):
    """Compõe a frase trocando todas as candidatas (densidade alta numa frase só = todas as escolhidas)."""
    return composer.compose(frase, {a.id for a in frase.annotations}, "pt")


def test_frase_com_zero_trocas_fica_so_em_portugues():
    frase = Frase("The fox ran.", "A raposa correu.")
    composto = composer.compose(frase, composer.select_swaps([frase], ["advanced_vocabulary"], "high"), "pt")
    assert composto.swaps == []
    assert composto.ssml == '<speak version="1.0" xml:lang="pt-BR">A raposa correu.</speak>'


def test_frase_com_varias_trocas_aponta_cada_uma_para_o_texto_em_portugues():
    frase = Frase("The famished and weary fox was forlorn.", "A raposa faminta e exausta estava desamparada.")
    frase.annotations = [
        palavra(1, frase, "famished", "faminta"),
        palavra(2, frase, "weary", "exausta"),
        palavra(3, frase, "forlorn", "desamparada"),
    ]
    composto = compor_tudo(frase)
    assert [(s.text, s.spoken, s.lang) for s in composto.swaps] == [
        ("faminta", "famished", "en-US"), ("exausta", "weary", "en-US"), ("desamparada", "forlorn", "en-US"),
    ]
    assert all(composto.text[s.start : s.end] == s.text for s in composto.swaps)
    assert composto.ssml.count('<lang xml:lang="en-US">') == 3


def test_palavras_sobrepostas_na_mesma_frase_mantem_so_a_primeira():
    frase = Frase("The ravenous wolf howled.", "O lobo esfomeado uivou.")
    lobo = palavra(1, frase, "ravenous wolf", "lobo esfomeado")
    esfomeado = palavra(2, frase, "ravenous", "esfomeado")  # dentro da primeira, no texto em português
    frase.annotations = [lobo, esfomeado]
    composto = compor_tudo(frase)
    assert [s.annotation_id for s in composto.swaps] == [1]
    ElementTree.fromstring(composto.ssml)  # continua um XML válido


def test_phrasal_verbs_e_vocabulario_avancado_juntos_no_compositor():
    # o filtro não permite misturar os Cenários A e C, mas o compositor sabe lidar com os dois tipos
    frase = Frase("She put on the cerulean coat.", "Ela vestiu o casaco cerúleo.")
    frase.annotations = [
        palavra(1, frase, "put on", "vestiu", kind=KIND_PHRASAL_VERB),
        palavra(2, frase, "cerulean", "cerúleo"),
    ]
    selecionadas = composer.select_swaps([frase], ["phrasal_verbs", "advanced_vocabulary"], "high")
    composto = composer.compose(frase, selecionadas, "pt")
    assert [s.spoken for s in composto.swaps] == ["put on", "cerulean"]
