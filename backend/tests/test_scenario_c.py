"""Testes de ponta a ponta do Cenário C (US11, #112 e #115): base português, vocabulário avançado falado em
inglês pela mesma voz e densidade crescente.

Percorrem o caminho do front (filtro, prévia, geração, status e áudio de cada frase) e conferem a coerência
entre as etapas: a prévia mostra exatamente o SSML que vai ao TTS, o perfil de densidade bate com as trocas,
e as frases sem troca reaproveitam o cache de áudio gerado em outro cenário, sem chamar o TTS.

Sem rede e sem créditos de TTS: FakeTTSProvider + InMemoryStorage + banco de teste (transação desfeita).
"""
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import pytest

from app.modules.audio.composer import AudioComposer
from app.modules.audio.models import STATUS_READY, AudioAsset
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB, Annotation, Segment, Story

# Fixtures da API de geração (troca o TTS e o storage pelos falsos); o pytest as encontra neste módulo
from tests.test_audio_generation_api import (  # noqa: F401
    audio_da_frase,
    criar_filtro,
    gerar,
    sessoes,
    status_de,
    storage,
    tts,
)

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Pares (inglês, português) de palavras raras (nível avançado) que a história usa
PALAVRAS = [
    ("famished", "faminta"), ("weary", "exausta"), ("cunning", "astuta"), ("forlorn", "desamparada"),
    ("disgruntled", "descontente"), ("ravenous", "esfomeada"),
]


def frases_da_historia(total=24):
    """`total` frases; a cada 4, uma (posições 2, 6, 10...) não tem palavra rara. A primeira também tem um
    phrasal verb, para o Cenário A ter o que trocar."""
    frases = []
    for i in range(total):
        if i % 4 == 2:
            frases.append((f"Day {i} was calm.", f"O dia {i} foi calmo.", None))
            continue
        en_word, pt_word = PALAVRAS[i % len(PALAVRAS)]
        frases.append((f"On day {i} the fox was {en_word}.", f"No dia {i} a raposa estava {pt_word}.", (en_word, pt_word)))
    frases[0] = ("On day 0 the fox gave up, famished.", "No dia 0 a raposa desistiu, faminta.", ("famished", "faminta"))
    return frases


FRASES = frases_da_historia()
TOTAL = len(FRASES)
CANDIDATAS = sum(1 for _, _, p in FRASES if p)

REGRAS_C = {
    "base_language": "pt",
    "segment_types": ["advanced_vocabulary"],
    "density": "high",
    "progression": "increasing",
}
REGRAS_A = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"}


def anotacao(kind, en, pt, trecho_en, trecho_pt, nivel=None):
    es, ps = en.index(trecho_en), pt.index(trecho_pt)
    return Annotation(
        kind=kind, lemma=trecho_en, en_start=es, en_end=es + len(trecho_en), en_text=trecho_en,
        pt_start=ps, pt_end=ps + len(trecho_pt), pt_text=trecho_pt, extra={"level": nivel} if nivel else {},
    )


@pytest.fixture
def historia_c(db_session):
    segments = []
    for i, (en, pt, palavra) in enumerate(FRASES):
        anotacoes = [anotacao(KIND_DIFFICULT_WORD, en, pt, *palavra, nivel="advanced")] if palavra else []
        if i == 0:
            anotacoes.append(anotacao(KIND_PHRASAL_VERB, en, pt, "gave up", "desistiu"))
        segments.append(Segment(position=i, text_en=en, text_pt=pt, annotations=anotacoes))
    story = Story(title="Cenário C de teste", language="en", segments=segments)
    db_session.add(story)
    db_session.commit()
    return story


def previa(api, headers, story_id, filter_id) -> dict:
    resposta = api.get(f"/stories/{story_id}/preview", params={"filter_id": filter_id}, headers=headers)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def ssml_da_previa(frase: dict) -> str:
    """O SSML que a frase da prévia descreve: o texto exibido com cada troca falada em inglês."""
    escapar = lambda t: escape(t, {'"': "&quot;", "'": "&apos;"})  # noqa: E731
    partes, cursor = [], 0
    for troca in frase["swaps"]:
        partes.append(escapar(frase["text"][cursor : troca["start"]]))
        partes.append(f'<lang xml:lang="{troca["lang"]}">{escapar(troca["spoken"])}</lang>')
        cursor = troca["end"]
    partes.append(escapar(frase["text"][cursor:]))
    return f'<speak version="1.0" xml:lang="pt-BR">{"".join(partes)}</speak>'


# ---------- fluxo completo ----------

def test_fluxo_completo_do_cenario_c_com_o_provedor_falso(api, make_user, sessoes, historia_c, tts, db_session):
    _, headers = make_user("Ana")
    filtro = criar_filtro(api, headers, historia_c.id, REGRAS_C)

    corpo_previa = previa(api, headers, historia_c.id, filtro)
    assert gerar(api, headers, historia_c.id, filtro).status_code == 202

    estado = status_de(api, headers, historia_c.id, filtro).json()
    assert (estado["state"], estado["total"], estado["ready"], estado["failed"]) == ("ready", TOTAL, TOTAL, 0)
    for frase in historia_c.segments:
        assert audio_da_frase(api, headers, frase.id, filtro).status_code == 200

    # narrado em português, com as palavras escolhidas em inglês, todas pela MESMA voz
    assert len(tts.calls) == TOTAL
    assert len({call.voice_id for call in tts.calls}) == 1
    for call in tts.calls:
        raiz = ElementTree.fromstring(call.ssml)
        assert raiz.get(XML_LANG) == "pt-BR"
        assert all(e.get(XML_LANG) == "en-US" for e in raiz.iter("lang"))

    # o que a prévia mostra é IDÊNTICO ao que foi enviado ao TTS
    assert [ssml_da_previa(s) for s in corpo_previa["segments"]] == [call.ssml for call in tts.calls]
    db_session.expire_all()
    assets = db_session.query(AudioAsset).filter(AudioAsset.story_id == historia_c.id).all()
    assert len(assets) == TOTAL and all(a.status == STATUS_READY for a in assets)


def test_ssml_tem_mais_lang_no_final_que_no_comeco(api, make_user, sessoes, historia_c, tts):
    _, headers = make_user()
    gerar(api, headers, historia_c.id, criar_filtro(api, headers, historia_c.id, REGRAS_C))

    langs = [call.ssml.count("<lang") for call in tts.calls]
    terco = TOTAL // 3
    assert sum(langs[-terco:]) > sum(langs[:terco])
    # as palavras faladas são as originais da história, em inglês
    faladas = {e.text for call in tts.calls for e in ElementTree.fromstring(call.ssml).iter("lang")}
    assert faladas <= {p[0] for _, _, p in FRASES if p}


# ---------- perfil de densidade da prévia ----------

def test_previa_devolve_o_perfil_de_densidade_coerente_com_as_trocas(api, make_user, historia_c):
    _, headers = make_user()
    corpo = previa(api, headers, historia_c.id, criar_filtro(api, headers, historia_c.id, REGRAS_C))
    perfil = corpo["density_profile"]

    assert [p["segment_id"] for p in perfil] == [s["id"] for s in corpo["segments"]]
    assert [p["swapped"] for p in perfil] == [len(s["swaps"]) for s in corpo["segments"]]
    assert sum(p["swapped"] for p in perfil) == corpo["totals"]["swapped"]
    assert sum(p["candidates"] for p in perfil) == corpo["totals"]["candidates"] == CANDIDATAS
    assert all(p["swapped"] <= p["candidates"] for p in perfil)

    alvos = [p["target"] for p in perfil]
    assert alvos == sorted(alvos) and alvos[0] < alvos[-1] <= 0.60  # a curva sobe até a densidade final
    # as trocas acompanham a curva em qualquer ponto da história (acumulador: no máximo meia troca)
    esperado = trocado = 0.0
    for p in perfil:
        esperado += p["target"] * p["candidates"]
        trocado += p["swapped"]
        assert abs(trocado - esperado) <= 0.5 + 1e-9


def test_perfil_da_densidade_fixa_tem_o_mesmo_alvo_em_todas_as_frases(api, make_user, historia_c):
    _, headers = make_user()
    corpo = previa(api, headers, historia_c.id, criar_filtro(api, headers, historia_c.id, REGRAS_A))
    assert {p["target"] for p in corpo["density_profile"]} == {0.60}
    assert sum(p["swapped"] for p in corpo["density_profile"]) == corpo["totals"]["swapped"] == 1


# ---------- cache entre cenários ----------

def test_frases_sem_troca_do_cenario_c_reaproveitam_o_cache_do_cenario_a(api, make_user, sessoes, historia_c, tts):
    _, headers = make_user()
    gerar(api, headers, historia_c.id, criar_filtro(api, headers, historia_c.id, REGRAS_A))
    ssml_do_a = {call.ssml for call in tts.calls}
    assert len(ssml_do_a) == TOTAL

    filtro_c = criar_filtro(api, headers, historia_c.id, REGRAS_C)
    frases_c = previa(api, headers, historia_c.id, filtro_c)["segments"]
    chamadas_antes = len(tts.calls)
    gerar(api, headers, historia_c.id, filtro_c)
    novas = [call.ssml for call in tts.calls[chamadas_antes:]]

    # Sem troca no C, a frase é narrada só em português: o mesmo SSML que o A gerou para ela (quando o A também
    # não trocou nada nela). Essas vêm do cache; o TTS só é chamado para as outras.
    reaproveitadas = [s for s in frases_c if not s["swaps"] and ssml_da_previa(s) in ssml_do_a]
    assert len(reaproveitadas) >= TOTAL // 2
    assert novas == [ssml_da_previa(s) for s in frases_c if ssml_da_previa(s) not in ssml_do_a]
    assert not {ssml_da_previa(s) for s in reaproveitadas} & set(novas)
    assert status_de(api, headers, historia_c.id, filtro_c).json()["ready"] == TOTAL


def test_cenario_a_continua_igual_ao_de_antes(historia_c):
    # densidade fixa: a mesma seleção de antes da US11, com ou sem a progressão explícita
    composer = AudioComposer()
    sem_campo = composer.select_swaps(historia_c.segments, ["phrasal_verbs"], "high")
    assert sem_campo == composer.select_swaps(historia_c.segments, ["phrasal_verbs"], "high", progression="fixed")
    assert len(sem_campo) == 1
