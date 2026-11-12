"""Testes do Filtro de Audição (US04): CRUD em /filters, regras em JSONB e posse por usuário."""
import pytest

REGRAS = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "medium"}


def corpo(story_id=None, **mudancas):
    return {"story_id": story_id, "rules": {**REGRAS, **mudancas}}


# ---------- criar ----------

def test_cria_filtro_e_devolve_201_com_as_regras(api, make_user):
    _, headers = make_user()
    resposta = api.post("/filters", json=corpo(story_id=1), headers=headers)
    assert resposta.status_code == 201
    filtro = resposta.json()
    assert filtro["story_id"] == 1 and filtro["rules"] == REGRAS
    assert filtro["id"] and filtro["created_at"] and filtro["updated_at"]


def test_filtro_pode_ser_criado_sem_historia(api, make_user):
    _, headers = make_user()
    assert api.post("/filters", json=corpo(), headers=headers).json()["story_id"] is None


CENARIO_B = {"base_language": "en", "segment_types": ["difficult_words"], "word_level": "intermediate"}


@pytest.mark.parametrize("densidade", ["low", "medium", "high"])
@pytest.mark.parametrize("cenario", [{}, CENARIO_B], ids=["cenario_a", "cenario_b"])
def test_aceita_todos_os_cenarios_e_densidades(api, make_user, cenario, densidade):
    _, headers = make_user()
    resposta = api.post("/filters", json=corpo(**cenario, density=densidade), headers=headers)
    assert resposta.status_code == 201


@pytest.mark.parametrize(
    "regras",
    [
        {"segment_types": []},  # critério da US04: pelo menos um tipo de trecho
        {"base_language": "fr"},
        {"density": "extreme"},
        {"segment_types": ["idioms"]},
    ],
)
def test_regras_invalidas_respondem_422(api, make_user, regras):
    _, headers = make_user()
    assert api.post("/filters", json=corpo(**regras), headers=headers).status_code == 422


@pytest.mark.parametrize("campo", ["base_language", "segment_types", "density"])
def test_regra_obrigatoria_ausente_responde_422(api, make_user, campo):
    _, headers = make_user()
    regras = {k: v for k, v in REGRAS.items() if k != campo}
    assert api.post("/filters", json={"story_id": 1, "rules": regras}, headers=headers).status_code == 422


def test_corpo_sem_regras_responde_422(api, make_user):
    _, headers = make_user()
    assert api.post("/filters", json={"story_id": 1}, headers=headers).status_code == 422


# ---------- listar e ler ----------

def test_lista_so_os_filtros_do_proprio_usuario(api, make_user):
    _, ana = make_user(email="ana@teste.com")
    _, beto = make_user(email="beto@teste.com")
    do_ana = api.post("/filters", json=corpo(story_id=1), headers=ana).json()
    api.post("/filters", json=corpo(story_id=2), headers=beto)

    lista = api.get("/filters", headers=ana).json()
    assert [f["id"] for f in lista] == [do_ana["id"]]


def test_lista_vazia_quando_nao_ha_filtros(api, make_user):
    _, headers = make_user()
    assert api.get("/filters", headers=headers).json() == []


def test_le_um_filtro_pelo_id(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(story_id=3), headers=headers).json()
    lido = api.get(f"/filters/{criado['id']}", headers=headers)
    assert lido.status_code == 200 and lido.json() == criado


def test_filtro_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.get("/filters/999999", headers=headers).status_code == 404


# ---------- atualizar ----------

def test_put_substitui_o_filtro_inteiro(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(story_id=1), headers=headers).json()
    novo = {"story_id": 2, "rules": {**CENARIO_B, "density": "high"}}

    resposta = api.put(f"/filters/{criado['id']}", json=novo, headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["story_id"] == 2 and resposta.json()["rules"] == novo["rules"]
    # a alteração foi gravada de verdade
    assert api.get(f"/filters/{criado['id']}", headers=headers).json()["rules"] == novo["rules"]


def test_put_com_regras_invalidas_responde_422_e_nao_altera(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(story_id=1), headers=headers).json()
    assert api.put(f"/filters/{criado['id']}", json=corpo(segment_types=[]), headers=headers).status_code == 422
    assert api.get(f"/filters/{criado['id']}", headers=headers).json()["rules"] == REGRAS


def test_put_em_filtro_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.put("/filters/999999", json=corpo(), headers=headers).status_code == 404


# ---------- apagar ----------

def test_delete_responde_204_e_o_filtro_some(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(), headers=headers).json()
    assert api.delete(f"/filters/{criado['id']}", headers=headers).status_code == 204
    assert api.get(f"/filters/{criado['id']}", headers=headers).status_code == 404


def test_delete_em_filtro_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.delete("/filters/999999", headers=headers).status_code == 404


# ---------- posse: um usuário nunca mexe no filtro de outro ----------

def test_filtro_de_outro_usuario_responde_404_em_todas_as_operacoes(api, make_user):
    _, ana = make_user(email="ana@teste.com")
    _, beto = make_user(email="beto@teste.com")
    do_ana = api.post("/filters", json=corpo(story_id=1), headers=ana).json()
    url = f"/filters/{do_ana['id']}"

    assert api.get(url, headers=beto).status_code == 404
    assert api.put(url, json=corpo(density="high"), headers=beto).status_code == 404
    assert api.delete(url, headers=beto).status_code == 404
    # o filtro da Ana continua intacto
    assert api.get(url, headers=ana).json()["rules"] == REGRAS


# ---------- autenticação ----------

@pytest.mark.parametrize(
    "metodo, rota",
    [("get", "/filters"), ("post", "/filters"), ("get", "/filters/1"), ("put", "/filters/1"), ("delete", "/filters/1")],
)
def test_todas_as_rotas_exigem_token(api, metodo, rota):
    kwargs = {"json": corpo()} if metodo in ("post", "put") else {}
    assert getattr(api, metodo)(rota, **kwargs).status_code == 401
