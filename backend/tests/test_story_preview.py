"""Testes de GET /stories/{id}/preview: o texto da história com as trocas de idioma já calculadas (#83).

Escritos antes do código (TDD). Rodam contra a API inteira e o banco de teste (transação desfeita no final),
com autenticação real. A prévia não gasta TTS nem grava nada no banco.
"""
import pytest
from sqlalchemy import event

from app.integrations.tts.fake import FakeTTSProvider
from app.modules.filters.models import ListeningFilter
from app.modules.stories.repository import AnnotationRepository, SegmentRepository, StoryRepository

# (inglês, português, [(lema, trecho em inglês, trecho em português ou None se não tem equivalente)])
FRASES = [
    ("The fox gave up the grapes.", "A raposa desistiu das uvas.", [("give up", "gave up", "desistiu")]),
    ("She woke up early.", "Ela acordou cedo.", [("wake up", "woke up", "acordou")]),
    ("He put on his coat.", "Ele vestiu o casaco.", [("put on", "put on", None)]),  # sem equivalente
    (
        "They set out at dawn and gave up later.",
        "Eles partiram ao amanhecer e desistiram depois.",
        [("set out", "set out", "partiram"), ("give up", "gave up", "desistiram")],
    ),
]


def criar_historia(db, titulo: str = "Prévia de teste", frases=FRASES) -> int:
    story = StoryRepository(db).create(titulo, None, "en")
    for posicao, (en, pt, trechos) in enumerate(frases):
        segmento = SegmentRepository(db).create(story.id, posicao, en, pt)
        for lema, trecho_en, trecho_pt in trechos:
            es = en.index(trecho_en)
            ps = pt.index(trecho_pt) if trecho_pt else None
            AnnotationRepository(db).create(
                segmento, "phrasal_verb", lema, es, es + len(trecho_en),
                ps, ps + len(trecho_pt) if trecho_pt else None,
            )
    return story.id


def criar_filtro(api, headers, story_id=None, base="pt", densidade="high") -> int:
    corpo = {"story_id": story_id, "rules": {"base_language": base, "segment_types": ["phrasal_verbs"], "density": densidade}}
    resposta = api.post("/filters", json=corpo, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def previa(api, headers, story_id, filter_id):
    return api.get(f"/stories/{story_id}/preview", params={"filter_id": filter_id}, headers=headers)


@pytest.fixture
def cenario(api, make_user, db_session):
    """Um usuário, uma história com 4 frases e um filtro de densidade alta para ela."""
    _, headers = make_user()
    story_id = criar_historia(db_session)
    filter_id = criar_filtro(api, headers, story_id)
    return headers, story_id, filter_id


# ---------- o conteúdo da prévia ----------

def test_devolve_a_historia_as_regras_do_filtro_e_todas_as_frases(api, cenario):
    headers, story_id, filter_id = cenario
    resposta = previa(api, headers, story_id, filter_id)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["story"] == {"id": story_id, "title": "Prévia de teste", "language": "en"}
    assert corpo["rules"] == {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"}
    assert [s["position"] for s in corpo["segments"]] == [0, 1, 2, 3]
    assert [s["text"] for s in corpo["segments"]] == [pt for _, pt, _ in FRASES]


def test_as_trocas_vem_com_posicao_no_texto_exibido_e_o_que_sera_falado(api, cenario):
    headers, story_id, filter_id = cenario
    corpo = previa(api, headers, story_id, filter_id).json()

    # densidade alta: 60% dos 4 candidatos com equivalente = 2 trocas, espalhadas pela história
    trocas = {s["position"]: s["swaps"] for s in corpo["segments"]}
    assert trocas[0] == [] and trocas[2] == []
    assert [(t["start"], t["end"], t["text"], t["spoken"], t["lang"]) for t in trocas[1]] == [
        (4, 11, "acordou", "woke up", "en-US")
    ]
    assert [(t["text"], t["spoken"]) for t in trocas[3]] == [("desistiram", "gave up")]
    assert all(isinstance(t["annotation_id"], int) for s in trocas.values() for t in s)


def test_cada_troca_aponta_para_o_texto_exato_da_frase(api, cenario):
    headers, story_id, filter_id = cenario
    for segmento in previa(api, headers, story_id, filter_id).json()["segments"]:
        for troca in segmento["swaps"]:
            assert segmento["text"][troca["start"] : troca["end"]] == troca["text"]


def test_os_totais_conferem_com_as_trocas_retornadas(api, cenario):
    headers, story_id, filter_id = cenario
    corpo = previa(api, headers, story_id, filter_id).json()

    assert corpo["totals"]["segments"] == len(corpo["segments"]) == 4
    assert corpo["totals"]["swapped"] == sum(len(s["swaps"]) for s in corpo["segments"]) == 2
    assert corpo["totals"]["candidates"] == 4  # a anotação sem equivalente ("put on") não é candidata


@pytest.mark.parametrize("densidade, trocas", [("low", 1), ("medium", 1), ("high", 2)])
def test_a_densidade_do_filtro_define_quantas_trocas(api, make_user, db_session, densidade, trocas):
    _, headers = make_user()
    story_id = criar_historia(db_session)
    filter_id = criar_filtro(api, headers, story_id, densidade=densidade)
    assert previa(api, headers, story_id, filter_id).json()["totals"]["swapped"] == trocas


def test_anotacao_sem_equivalente_em_portugues_nunca_vira_troca(api, cenario):
    headers, story_id, filter_id = cenario
    frase_sem = previa(api, headers, story_id, filter_id).json()["segments"][2]
    assert frase_sem["text"] == "Ele vestiu o casaco." and frase_sem["swaps"] == []


def test_com_idioma_base_ingles_o_texto_e_o_ingles_e_o_falado_e_o_portugues(api, make_user, db_session):
    _, headers = make_user()
    story_id = criar_historia(db_session)
    filter_id = criar_filtro(api, headers, story_id, base="en", densidade="high")

    corpo = previa(api, headers, story_id, filter_id).json()

    assert [s["text"] for s in corpo["segments"]] == [en for en, _, _ in FRASES]
    trocas = [t for s in corpo["segments"] for t in s["swaps"]]
    assert len(trocas) == 2 and all(t["lang"] == "pt-BR" for t in trocas)
    assert {(t["text"], t["spoken"]) for t in trocas} == {("woke up", "acordou"), ("gave up", "desistiram")}


def test_as_frases_vem_em_ordem_mesmo_criadas_fora_de_ordem(api, make_user, db_session):
    _, headers = make_user()
    story = StoryRepository(db_session).create("Fora de ordem", None, "en")
    for posicao in (2, 0, 1):
        SegmentRepository(db_session).create(story.id, posicao, f"Sentence {posicao}.", f"Frase {posicao}.")
    filter_id = criar_filtro(api, headers, story.id)

    corpo = previa(api, headers, story.id, filter_id).json()
    assert [s["text"] for s in corpo["segments"]] == ["Frase 0.", "Frase 1.", "Frase 2."]
    assert corpo["totals"] == {"segments": 3, "candidates": 0, "swapped": 0}


def test_o_mesmo_filtro_devolve_sempre_a_mesma_previa(api, cenario):
    headers, story_id, filter_id = cenario
    primeira = previa(api, headers, story_id, filter_id).json()
    for _ in range(5):
        assert previa(api, headers, story_id, filter_id).json() == primeira


def test_filtro_sem_historia_vale_para_qualquer_historia(api, make_user, db_session):
    _, headers = make_user()
    story_id = criar_historia(db_session)
    filter_id = criar_filtro(api, headers, story_id=None)
    assert previa(api, headers, story_id, filter_id).status_code == 200


# ---------- erros ----------

def test_sem_token_responde_401(api, cenario):
    _, story_id, filter_id = cenario
    assert previa(api, {}, story_id, filter_id).status_code == 401


def test_historia_inexistente_responde_404(api, cenario):
    headers, _, filter_id = cenario
    resposta = previa(api, headers, 999999, filter_id)
    assert resposta.status_code == 404


def test_filtro_inexistente_responde_404(api, cenario):
    headers, story_id, _ = cenario
    assert previa(api, headers, story_id, 999999).status_code == 404


def test_filtro_de_outro_usuario_responde_404(api, make_user, cenario):
    _, story_id, filter_id = cenario
    _, outro = make_user(email="outro@teste.com")
    assert previa(api, outro, story_id, filter_id).status_code == 404


def test_filtro_de_outra_historia_responde_422(api, make_user, db_session):
    _, headers = make_user()
    story_id = criar_historia(db_session, "A")
    outra_id = criar_historia(db_session, "B")
    filter_id = criar_filtro(api, headers, story_id=outra_id)

    resposta = previa(api, headers, story_id, filter_id)

    assert resposta.status_code == 422
    assert "outra história" in resposta.json()["detail"]


def test_sem_filter_id_responde_422(api, cenario):
    headers, story_id, _ = cenario
    assert api.get(f"/stories/{story_id}/preview", headers=headers).status_code == 422


def test_regras_guardadas_com_tipo_sem_estrategia_respondem_422(api, make_user, db_session):
    usuario, headers = make_user()
    story_id = criar_historia(db_session)
    regras = {"base_language": "pt", "segment_types": ["idioms"], "density": "high"}
    antigo = ListeningFilter(user_id=usuario["id"], story_id=story_id, rules=regras)  # só o banco aceitaria isto
    db_session.add(antigo)
    db_session.commit()

    assert previa(api, headers, story_id, antigo.id).status_code == 422


def test_tipo_de_trecho_sem_estrategia_de_troca_responde_422(api, cenario, monkeypatch):
    """O filtro passa a aceitar um tipo novo antes de existir a estratégia dele: erro claro, e não 500."""
    from app.modules.audio.composer import AudioComposer, UnknownSwapStrategyError

    def sem_estrategia(self, segments, segment_types, density):
        raise UnknownSwapStrategyError("Tipo de trecho sem estratégia de troca: 'difficult_words'")

    monkeypatch.setattr(AudioComposer, "select_swaps", sem_estrategia)
    headers, story_id, filter_id = cenario

    resposta = previa(api, headers, story_id, filter_id)

    assert resposta.status_code == 422
    assert "difficult_words" in resposta.json()["detail"]


# ---------- só leitura: sem TTS e sem gravar no banco ----------

def instrumentar(db_session):
    comandos: list[str] = []

    def registrar(conn, cursor, statement, *args):
        comandos.append(statement)

    engine = db_session.get_bind().engine
    event.listen(engine, "before_cursor_execute", registrar)
    return comandos, lambda: event.remove(engine, "before_cursor_execute", registrar)


def test_a_previa_nao_grava_nada_no_banco(api, cenario, db_session):
    headers, story_id, filter_id = cenario
    comandos, parar = instrumentar(db_session)
    try:
        assert previa(api, headers, story_id, filter_id).status_code == 200
    finally:
        parar()

    escritas = [c for c in comandos if c.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert comandos and escritas == []


def test_a_previa_nao_chama_o_tts(api, cenario, monkeypatch):
    def proibido(self, ssml, voice_id):
        raise AssertionError("a prévia não pode gastar TTS")

    monkeypatch.setattr(FakeTTSProvider, "synthesize", proibido)
    headers, story_id, filter_id = cenario
    assert previa(api, headers, story_id, filter_id).status_code == 200


def test_o_numero_de_consultas_nao_cresce_com_o_numero_de_frases(api, make_user, db_session):
    _, headers = make_user()
    frases_curta = FRASES[:2]
    frases_longa = FRASES * 10  # 40 frases
    curta = criar_historia(db_session, "Curta", frases_curta)
    longa = criar_historia(db_session, "Longa", frases_longa)
    f_curta = criar_filtro(api, headers, curta)
    f_longa = criar_filtro(api, headers, longa)

    def consultas(story_id, filter_id) -> int:
        db_session.expire_all()
        comandos, parar = instrumentar(db_session)
        try:
            assert previa(api, headers, story_id, filter_id).status_code == 200
        finally:
            parar()
        return len(comandos)

    assert consultas(curta, f_curta) == consultas(longa, f_longa)


# ---------- o contrato no /docs ----------

def test_o_contrato_aparece_no_openapi(api):
    esquema = api.get("/openapi.json").json()
    operacao = esquema["paths"]["/stories/{story_id}/preview"]["get"]

    parametros = {p["name"]: p for p in operacao["parameters"]}
    assert parametros["filter_id"]["required"] is True
    assert {"200", "401", "404", "422"} <= set(operacao["responses"])

    previa_schema = esquema["components"]["schemas"]["PreviewRead"]
    assert set(previa_schema["properties"]) == {"story", "rules", "totals", "segments"}
    troca = esquema["components"]["schemas"]["SwapRead"]
    assert set(troca["properties"]) == {"start", "end", "text", "spoken", "lang", "annotation_id"}


# ---------- com as histórias reais do seed ----------

def test_a_previa_funciona_com_as_historias_reais(api, make_user, db_session):
    from app.modules.stories.annotator import TextAnnotator
    from app.modules.stories.seed.loader import load_seed

    load_seed(db_session)
    TextAnnotator.with_defaults(db_session).annotate_all()
    _, headers = make_user()
    story_id = StoryRepository(db_session).get_by_title("A Raposa e as Uvas").id
    filter_id = criar_filtro(api, headers, story_id, densidade="high")

    corpo = previa(api, headers, story_id, filter_id).json()

    assert corpo["totals"] == {"segments": 12, "candidates": 9, "swapped": 5}
    for segmento in corpo["segments"]:
        for troca in segmento["swaps"]:
            assert segmento["text"][troca["start"] : troca["end"]] == troca["text"]
