"""Testes da lista de histórias (GET /stories) e da rota de saúde (GET /health)."""
from app.modules.stories.repository import StoryRepository


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
    assert achada == {"id": historia.id, "title": "História de teste XYZ", "description": "Uma descrição"}


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
