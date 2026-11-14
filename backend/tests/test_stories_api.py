"""Testes da lista de histórias (GET /stories) e da rota de saúde (GET /health)."""
from app.modules.stories.repository import SegmentRepository, StoryRepository


def test_health_responde_200_sem_precisar_de_token(api):
    resposta = api.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_swagger_e_o_openapi_estao_disponiveis(api):
    assert api.get("/docs").status_code == 200
    rotas = api.get("/openapi.json").json()["paths"]
    for rota in ("/health", "/auth/login", "/filters", "/stories", "/stories/{story_id}/segments", "/audio/stream"):
        assert rota in rotas


def test_lista_de_historias_exige_token(api):
    assert api.get("/stories").status_code == 401


def test_lista_de_historias_traz_id_titulo_e_descricao(api, make_user, db_session):
    _, headers = make_user()
    historia = StoryRepository(db_session).create("História de teste XYZ", "Uma descrição", "en")

    lista = api.get("/stories", headers=headers).json()
    achada = next(h for h in lista if h["id"] == historia.id)
    assert achada == {
        "id": historia.id, "title": "História de teste XYZ", "description": "Uma descrição", "segment_count": 0,
    }


def test_lista_de_historias_vem_em_ordem_de_id(api, make_user, db_session):
    _, headers = make_user()
    repo = StoryRepository(db_session)
    repo.create("Primeira XYZ", None, "en")
    repo.create("Segunda XYZ", None, "pt")

    ids = [h["id"] for h in api.get("/stories", headers=headers).json()]
    assert ids == sorted(ids)


def test_descricao_pode_ser_nula(api, make_user, db_session):
    _, headers = make_user()
    historia = StoryRepository(db_session).create("Sem descrição XYZ", None, "en")
    achada = next(h for h in api.get("/stories", headers=headers).json() if h["id"] == historia.id)
    assert achada["description"] is None


def test_lista_de_historias_traz_o_numero_de_frases_de_cada_uma(api, make_user, db_session):
    _, headers = make_user()
    repo = StoryRepository(db_session)
    com_tres = repo.create("Com três frases XYZ", None, "en")
    sem_frases = repo.create("Sem frases XYZ", None, "en")
    for posicao in range(3):
        SegmentRepository(db_session).create(com_tres.id, posicao, f"Sentence {posicao}.", f"Frase {posicao}.")

    lista = {h["id"]: h for h in api.get("/stories", headers=headers).json()}

    assert lista[com_tres.id]["segment_count"] == 3
    assert lista[sem_frases.id]["segment_count"] == 0


def test_o_numero_de_consultas_da_lista_nao_cresce_com_o_numero_de_historias(api, make_user, db_session):
    from sqlalchemy import event

    _, headers = make_user()
    repo = StoryRepository(db_session)
    consultas: list[str] = []

    def contar(conn, cursor, statement, *args):
        if "FROM stories" in statement or "FROM segments" in statement:
            consultas.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", contar)
    try:
        api.get("/stories", headers=headers)
        antes = len(consultas)
        for i in range(5):
            historia = repo.create(f"Muitas histórias {i} XYZ", None, "en")
            SegmentRepository(db_session).create(historia.id, 0, "One.", "Um.")
        consultas.clear()
        api.get("/stories", headers=headers)
        depois = len(consultas)
    finally:
        event.remove(engine, "before_cursor_execute", contar)

    assert depois == antes
