"""Testes de GET /stories/{id}/segments, no banco de dados (transação desfeita no final)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.stories.models import KIND_PHRASAL_VERB
from app.modules.stories.repository import (
    AnnotationRepository,
    SegmentRepository,
    StoryRepository,
)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(db_session):
    """Cliente sem token: só o banco é trocado, a autenticação é a real."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def criar_historia(db, n_frases: int = 2) -> int:
    """Cada frase "He gave up now." tem 'gave up' (alinhado) e 'now' fictício sem equivalente."""
    story = StoryRepository(db).create("Historia de teste", None, "en")
    segments, annotations = SegmentRepository(db), AnnotationRepository(db)
    # criadas fora de ordem de propósito: a API deve devolver por position
    for position in reversed(range(n_frases)):
        seg = segments.create(story.id, position, "He gave up now.", "Ele desistiu agora.")
        annotations.create(seg, KIND_PHRASAL_VERB, "give out", 3, 7, extra={"x": 1})  # sem equivalente
        annotations.create(
            seg, KIND_PHRASAL_VERB, "give up", 3, 10, pt_start=4, pt_end=12, extra={"separable": False}
        )
    return story.id


def test_devolve_segmentos_em_ordem_com_anotacoes(client, db_session):
    story_id = criar_historia(db_session, n_frases=3)
    resposta = client.get(f"/stories/{story_id}/segments")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["story"] == {"id": story_id, "title": "Historia de teste", "language": "en"}
    assert [s["position"] for s in corpo["segments"]] == [0, 1, 2]
    primeira = corpo["segments"][0]
    assert primeira["text_en"] == "He gave up now." and primeira["text_pt"] == "Ele desistiu agora."
    assert [a["en_start"] for a in primeira["annotations"]] == [3, 3]
    alinhada = next(a for a in primeira["annotations"] if a["lemma"] == "give up")
    assert alinhada == {
        "id": alinhada["id"], "kind": "phrasal_verb", "lemma": "give up",
        "en_start": 3, "en_end": 10, "en_text": "gave up",
        "pt_start": 4, "pt_end": 12, "pt_text": "desistiu",
        "extra": {"separable": False},
    }


def test_filtro_aligned_only(client, db_session):
    story_id = criar_historia(db_session)
    corpo = client.get(f"/stories/{story_id}/segments?aligned_only=true").json()
    for seg in corpo["segments"]:
        assert [a["lemma"] for a in seg["annotations"]] == ["give up"]
    # as frases continuam na lista, só as anotações são filtradas
    assert len(corpo["segments"]) == 2


def test_filtro_kind(client, db_session):
    story_id = criar_historia(db_session)
    todas = client.get(f"/stories/{story_id}/segments?kind=phrasal_verb").json()
    assert all(len(s["annotations"]) == 2 for s in todas["segments"])
    combinado = client.get(f"/stories/{story_id}/segments?kind=phrasal_verb&aligned_only=true").json()
    assert all(len(s["annotations"]) == 1 for s in combinado["segments"])


def test_historia_inexistente_responde_404(client):
    assert client.get("/stories/999999/segments").status_code == 404


def test_sem_token_responde_401(anonymous_client, db_session):
    story_id = criar_historia(db_session)
    assert anonymous_client.get(f"/stories/{story_id}/segments").status_code == 401


def test_kind_desconhecido_responde_422(client, db_session):
    story_id = criar_historia(db_session)
    assert client.get(f"/stories/{story_id}/segments?kind=idiom").status_code == 422


def test_historia_sem_frases_devolve_lista_vazia(client, db_session):
    story = StoryRepository(db_session).create("Vazia", None, "en")
    assert client.get(f"/stories/{story.id}/segments").json()["segments"] == []


def contar_consultas(client, db_session, url: str) -> int:
    consultas = []

    def registrar(conn, cursor, statement, *args):
        consultas.append(statement)

    engine = db_session.get_bind().engine
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        assert client.get(url).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", registrar)
    return len(consultas)


def test_numero_de_consultas_nao_cresce_com_o_numero_de_frases(client, db_session):
    pequena = criar_historia(db_session, n_frases=2)
    grande = criar_historia(db_session, n_frases=30)
    db_session.expire_all()
    a = contar_consultas(client, db_session, f"/stories/{pequena}/segments")
    db_session.expire_all()
    b = contar_consultas(client, db_session, f"/stories/{grande}/segments")
    assert a == b


def test_contrato_aparece_no_openapi(client):
    schema = client.get("/openapi.json").json()
    operacao = schema["paths"]["/stories/{story_id}/segments"]["get"]
    assert {p["name"] for p in operacao["parameters"]} >= {"kind", "aligned_only"}
