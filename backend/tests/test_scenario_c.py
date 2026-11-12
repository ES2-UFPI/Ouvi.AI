"""Testes de ponta a ponta do Cenário C (US11): base português, vocabulário avançado falado em inglês e
densidade crescente.

Rodam contra a API e o banco de teste (transação desfeita no final), com o FakeTTSProvider e o
InMemoryStorage: sem rede. Conferem que a prévia (o que o usuário vê) e a geração (o que ele ouve) usam a
mesma seleção, inclusive com a curva.
"""
import re
from xml.etree import ElementTree

import pytest

from app.integrations.storage import InMemoryStorage
from app.integrations.tts import FakeTTSProvider
from app.modules.audio.facade import build_facade
from app.modules.audio.models import STATUS_READY, AudioAsset
from app.modules.audio.repository import compute_rules_hash
from app.modules.filters.schemas import FilterRules
from app.modules.stories.models import KIND_DIFFICULT_WORD, Annotation, Segment, Story

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Nove frases (três por terço), cada uma com uma palavra rara (nível avançado) alinhada ao português
FRASES = [
    ("The famished fox looked up.", "A raposa faminta olhou para cima.", "famished", "faminta"),
    ("The weary hare slept.", "A lebre exausta dormiu.", "weary", "exausta"),
    ("A cunning crow sang.", "Um corvo astuto cantou.", "cunning", "astuto"),
    ("The vineyard was vast.", "A vinha era vasta.", "vineyard", "vinha"),
    ("The grapes were luscious.", "As uvas eram suculentas.", "luscious", "suculentas"),
    ("The trellis was tall.", "A treliça era alta.", "trellis", "treliça"),
    ("The fox felt forlorn.", "A raposa se sentiu desamparada.", "forlorn", "desamparada"),
    ("Its stomach was rumbling.", "Seu estômago estava roncando.", "rumbling", "roncando"),
    ("It left, disgruntled.", "Ela foi embora, descontente.", "disgruntled", "descontente"),
]

REGRAS_C = {
    "base_language": "pt",
    "segment_types": ["advanced_vocabulary"],
    "density": "high",
    "progression": "increasing",
}


@pytest.fixture
def historia_c(db_session):
    segments = []
    for i, (en, pt, palavra_en, palavra_pt) in enumerate(FRASES):
        es, ps = en.index(palavra_en), pt.index(palavra_pt)
        segments.append(
            Segment(
                position=i, text_en=en, text_pt=pt,
                annotations=[
                    Annotation(
                        kind=KIND_DIFFICULT_WORD, lemma=palavra_en, en_start=es, en_end=es + len(palavra_en),
                        en_text=palavra_en, pt_start=ps, pt_end=ps + len(palavra_pt), pt_text=palavra_pt,
                        extra={"level": "advanced"},
                    ),
                ],
            )
        )
    story = Story(title="Cenário C de teste", language="en", segments=segments)
    db_session.add(story)
    db_session.commit()
    return story


def falados_por_frase(tts):
    """Para cada chamada ao TTS (uma por frase, em ordem), as palavras faladas em inglês."""
    return [[e.text for e in ElementTree.fromstring(c.ssml).iter("lang")] for c in tts.calls]


def test_geracao_do_cenario_c_com_densidade_crescente(db_session, historia_c):
    tts, storage = FakeTTSProvider(), InMemoryStorage()
    facade = build_facade(db_session, tts, storage, "voz-multilingue", sleep=lambda _: None)

    resultado = facade.generate(historia_c.id, FilterRules.model_validate(REGRAS_C).model_dump())

    assert len(resultado.generated) == 9 and not resultado.failed
    for call in tts.calls:
        raiz = ElementTree.fromstring(call.ssml)
        assert raiz.get(XML_LANG) == "pt-BR"  # a história é narrada em português
        assert all(e.get(XML_LANG) == "en-US" for e in raiz.iter("lang"))  # a palavra rara, em inglês
    trocas = [len(f) for f in falados_por_frase(tts)]
    # alta (60%) com a curva: 30% no início, 60% no meio e 90% no fim de cada terço de 3 frases
    assert [sum(trocas[0:3]), sum(trocas[3:6]), sum(trocas[6:9])] == [1, 2, 3]
    db_session.expire_all()
    assets = db_session.query(AudioAsset).filter(AudioAsset.story_id == historia_c.id).all()
    assert len(assets) == 9 and all(a.status == STATUS_READY for a in assets)


def test_constante_e_crescente_geram_audios_separados(db_session, historia_c):
    tts, storage = FakeTTSProvider(), InMemoryStorage()
    facade = build_facade(db_session, tts, storage, "voz-multilingue", sleep=lambda _: None)
    constante = FilterRules.model_validate({**REGRAS_C, "progression": "constant"}).model_dump()
    crescente = FilterRules.model_validate(REGRAS_C).model_dump()

    facade.generate(historia_c.id, constante)
    facade.generate(historia_c.id, crescente)

    hashes = {a.rules_hash for a in db_session.query(AudioAsset).filter(AudioAsset.story_id == historia_c.id)}
    assert hashes == {compute_rules_hash(constante), compute_rules_hash(crescente)}


def test_previa_mostra_o_mesmo_que_o_audio_fala(api, make_user, db_session, historia_c):
    _, headers = make_user()
    criado = api.post("/filters", json={"story_id": historia_c.id, "rules": REGRAS_C}, headers=headers)
    assert criado.status_code == 201, criado.text

    resposta = api.get(f"/stories/{historia_c.id}/preview", params={"filter_id": criado.json()["id"]}, headers=headers)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["rules"] == REGRAS_C
    assert [s["text"] for s in corpo["segments"]] == [pt for _, pt, _, _ in FRASES]
    assert corpo["totals"]["candidates"] == 9

    tts = FakeTTSProvider()
    build_facade(db_session, tts, InMemoryStorage(), "voz", sleep=lambda _: None).generate(
        historia_c.id, FilterRules.model_validate(REGRAS_C).model_dump()
    )
    assert [[t["spoken"] for t in s["swaps"]] for s in corpo["segments"]] == falados_por_frase(tts)
    for s in corpo["segments"]:
        for t in s["swaps"]:
            assert s["text"][t["start"] : t["end"]] == t["text"] and t["lang"] == "en-US"


def test_ssml_do_cenario_c_nao_tem_marcacao_quebrada(db_session, historia_c):
    tts = FakeTTSProvider()
    build_facade(db_session, tts, InMemoryStorage(), "voz", sleep=lambda _: None).generate(
        historia_c.id, FilterRules.model_validate({**REGRAS_C, "progression": None}).model_dump()
    )
    for call in tts.calls:
        assert re.fullmatch(r'<speak version="1\.0" xml:lang="pt-BR">.*</speak>', call.ssml)
