"""Testes do Cenário B (#105, #109): idioma base inglês com as palavras difíceis faladas em português.

A primeira parte usa anotações simuladas (sem banco, sem spaCy, sem rede). A última gera o áudio de ponta a
ponta com o FakeTTSProvider e o InMemoryStorage, no banco de teste (transação desfeita no final).
"""
from dataclasses import dataclass, field
from xml.etree import ElementTree

import pytest

from app.integrations.storage import InMemoryStorage
from app.integrations.tts import FakeTTSProvider
from app.modules.audio.composer import AudioComposer, DifficultWordStrategy, SwapStrategyFactory
from app.modules.audio.facade import build_facade
from app.modules.audio.models import STATUS_READY, AudioAsset
from app.modules.filters.schemas import FilterRules
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB, Annotation, Segment, Story

composer = AudioComposer()


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


def palavra(id, frase, en, pt, nivel="intermediate", kind=KIND_DIFFICULT_WORD):
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


def xml(ssml):
    return ElementTree.fromstring(ssml)


# ---------- estratégia e fábrica ----------

def test_fabrica_cria_a_estrategia_de_palavras_dificeis():
    estrategia = SwapStrategyFactory.create("difficult_words", "advanced")
    assert isinstance(estrategia, DifficultWordStrategy)
    assert "difficult_words" in SwapStrategyFactory.types()


def test_sem_nivel_usa_o_intermediario():
    assert DifficultWordStrategy().levels == {"intermediate", "advanced"}


def test_ssml_do_cenario_b_tem_speak_en_us_e_lang_pt_br_e_e_xml_valido():
    frase = Frase('The "hare" dozed & the tortoise won.', 'A "lebre" cochilou & a tartaruga venceu.')
    frase.annotations = [palavra(1, frase, "tortoise", "tartaruga"), palavra(2, frase, "dozed", "cochilou")]

    resultado = composer.compose(frase, {1, 2}, "en")

    raiz = xml(resultado.ssml)
    assert raiz.attrib["{http://www.w3.org/XML/1998/namespace}lang"] == "en-US"
    langs = raiz.findall("lang")
    assert [(e.text, e.attrib["{http://www.w3.org/XML/1998/namespace}lang"]) for e in langs] == [
        ("cochilou", "pt-BR"),
        ("tartaruga", "pt-BR"),
    ]
    assert resultado.text == frase.text_en
    for swap in resultado.swaps:
        assert resultado.text[swap.start : swap.end] == swap.text  # posições no texto em inglês
        assert swap.lang == "pt-BR"
    assert [(s.text, s.spoken) for s in resultado.swaps] == [("dozed", "cochilou"), ("tortoise", "tartaruga")]


def test_avancado_seleciona_menos_palavras_que_intermediario():
    frases = historia_simulada()
    for densidade in ("low", "medium", "high"):
        inter = composer.select_swaps(frases, ["difficult_words"], densidade, "intermediate")
        avanc = composer.select_swaps(frases, ["difficult_words"], densidade, "advanced")
        assert len(avanc) < len(inter), densidade
        ids_avancados = {a.id for f in frases for a in f.annotations if a.extra["level"] == "advanced"}
        assert avanc <= ids_avancados


def test_densidade_muda_a_quantidade_e_o_resultado_e_deterministico():
    frases = historia_simulada()
    tamanhos = [len(composer.select_swaps(frases, ["difficult_words"], d, "intermediate")) for d in ("low", "medium", "high")]
    assert tamanhos == [3, 7, 12]  # 15%, 35% e 60% de 20
    primeira = composer.select_swaps(frases, ["difficult_words"], "medium", "intermediate")
    assert all(composer.select_swaps(frases, ["difficult_words"], "medium", "intermediate") == primeira for _ in range(5))


def test_sem_equivalente_nunca_e_trocada():
    frase = Frase("The tortoise and the owl.", "A tartaruga e a coruja.")
    frase.annotations = [palavra(1, frase, "tortoise", None), palavra(2, frase, "owl", "coruja")]
    selecionadas = composer.select_swaps([frase], ["difficult_words"], "high", "intermediate")
    assert selecionadas == {2}
    # mesmo se o id vier selecionado, a composição não troca o que não tem português
    assert [s.annotation_id for s in composer.compose(frase, {1, 2}, "en").swaps] == [2]


def test_cenario_b_ignora_phrasal_verbs():
    frase = Frase("The tortoise gave up.", "A tartaruga desistiu.")
    frase.annotations = [palavra(1, frase, "tortoise", "tartaruga"), palavra(2, frase, "gave up", "desistiu", kind=KIND_PHRASAL_VERB)]
    assert composer.select_swaps([frase], ["difficult_words"], "high", "intermediate") == {1}


# ---------- ponta a ponta com o provedor falso ----------

REGRAS_B = FilterRules.model_validate(
    {"base_language": "en", "segment_types": ["difficult_words"], "word_level": "intermediate", "density": "high"}
).model_dump()

FRASES = [
    ("The tortoise won the race.", "A tartaruga venceu a corrida.", "tortoise", "tartaruga"),
    ("The hare dozed in the shade.", "A lebre cochilou na sombra.", "dozed", "cochilou"),
    ("The grapes were sour.", "As uvas estavam azedas.", "sour", "azedas"),
]


@pytest.fixture
def historia_b(db_session):
    segments = []
    for i, (en, pt, trecho_en, trecho_pt) in enumerate(FRASES):
        es, ps = en.index(trecho_en), pt.index(trecho_pt)
        segments.append(
            Segment(
                position=i, text_en=en, text_pt=pt,
                annotations=[
                    Annotation(
                        kind=KIND_DIFFICULT_WORD, lemma=trecho_en, en_start=es, en_end=es + len(trecho_en),
                        en_text=trecho_en, pt_start=ps, pt_end=ps + len(trecho_pt), pt_text=trecho_pt,
                        extra={"level": "advanced"},
                    )
                ],
            )
        )
    story = Story(title="Cenário B de teste", language="en", segments=segments)
    db_session.add(story)
    db_session.commit()
    return story


def test_geracao_de_ponta_a_ponta_no_cenario_b_com_o_provedor_falso(db_session, historia_b):
    tts, storage = FakeTTSProvider(), InMemoryStorage()
    facade = build_facade(db_session, tts, storage, "voz-multilingue", sleep=lambda _: None)

    resultado = facade.generate(historia_b.id, REGRAS_B)

    assert len(resultado.generated) == 3 and not resultado.failed
    assert len(tts.calls) == 3
    trocadas = 0
    for call in tts.calls:
        raiz = xml(call.ssml)
        assert raiz.attrib["{http://www.w3.org/XML/1998/namespace}lang"] == "en-US"
        assert call.voice_id == "voz-multilingue"  # a MESMA voz fala o inglês e o português
        trocadas += len(raiz.findall("lang"))
    assert trocadas == 2  # 60% de 3 candidatas
    assert all('xml:lang="pt-BR"' in c.ssml for c in tts.calls if "<lang" in c.ssml)
    db_session.expire_all()
    assets = db_session.query(AudioAsset).filter(AudioAsset.story_id == historia_b.id).all()
    assert len(assets) == 3 and all(a.status == STATUS_READY for a in assets)
