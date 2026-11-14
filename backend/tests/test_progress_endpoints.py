"""Testes dos endpoints de progresso (#96): GET/PUT/DELETE /stories/{id}/progress e GET /progress/recent."""
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.stories.models import Segment, Story

AGORA = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
REGRAS = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "medium"}


def quando(minutos: int = 0) -> str:
    return (AGORA + timedelta(minutes=minutos)).isoformat()


def corpo(frase=2, offset=1500, minutos=0, **extra):
    return {"segment_position": frase, "offset_ms": offset, "client_time": quando(minutos), **extra}


@pytest.fixture
def nova_historia(db_session):
    def _nova(titulo: str = "A raposa e as uvas", n_frases: int = 5) -> int:
        story = Story(
            title=titulo,
            segments=[Segment(position=i, text_en=f"Sentence {i}.", text_pt=f"Frase {i}.") for i in range(n_frases)],
        )
        db_session.add(story)
        db_session.commit()
        return story.id

    return _nova


@pytest.fixture
def historia(nova_historia) -> int:
    return nova_historia()


def url(story_id: int) -> str:
    return f"/stories/{story_id}/progress"


# ---------- GET ----------

def test_get_sem_progresso_responde_204(api, make_user, historia):
    _, headers = make_user()
    resposta = api.get(url(historia), headers=headers)
    assert resposta.status_code == 204
    assert resposta.content == b""


def test_get_devolve_o_progresso_salvo(api, make_user, historia):
    _, headers = make_user()
    api.put(url(historia), json=corpo(frase=3, offset=250), headers=headers)

    resposta = api.get(url(historia), headers=headers)
    assert resposta.status_code == 200
    progresso = resposta.json()
    assert progresso["story_id"] == historia
    assert progresso["segment_position"] == 3 and progresso["offset_ms"] == 250
    assert progresso["completed"] is False and progresso["filter_id"] is None
    assert datetime.fromisoformat(progresso["client_time"]) == AGORA
    assert progresso["updated_at"]


def test_get_de_historia_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.get(url(999_999), headers=headers).status_code == 404


# ---------- PUT ----------

def test_put_cria_na_primeira_vez(api, make_user, historia):
    _, headers = make_user()
    resposta = api.put(url(historia), json=corpo(frase=1, offset=10), headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["segment_position"] == 1 and resposta.json()["offset_ms"] == 10


def test_put_atualiza_sem_duplicar(api, make_user, historia):
    _, headers = make_user()
    api.put(url(historia), json=corpo(frase=1, minutos=0), headers=headers)
    resposta = api.put(url(historia), json=corpo(frase=4, offset=99, minutos=1, completed=True), headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["segment_position"] == 4 and resposta.json()["completed"] is True

    # Um único registro: o recent (com concluídas fora) fica vazio, e o GET traz a versão nova
    assert api.get(url(historia), headers=headers).json()["segment_position"] == 4


def test_put_com_client_time_mais_antigo_nao_sobrescreve(api, make_user, historia):
    _, headers = make_user()
    api.put(url(historia), json=corpo(frase=4, minutos=10), headers=headers)

    atrasada = api.put(url(historia), json=corpo(frase=1, minutos=5), headers=headers)
    assert atrasada.status_code == 200
    assert atrasada.json()["segment_position"] == 4  # devolve o que está no banco
    assert api.get(url(historia), headers=headers).json()["segment_position"] == 4


def test_put_com_filtro_do_proprio_usuario(api, make_user, historia):
    _, headers = make_user()
    filtro = api.post("/filters", json={"story_id": historia, "rules": REGRAS}, headers=headers).json()
    resposta = api.put(url(historia), json=corpo(filter_id=filtro["id"]), headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["filter_id"] == filtro["id"]


def test_put_com_filtro_de_outro_usuario_responde_404(api, make_user, historia):
    _, ana = make_user(email="ana@teste.com")
    _, beto = make_user(email="beto@teste.com")
    filtro_do_beto = api.post("/filters", json={"story_id": historia, "rules": REGRAS}, headers=beto).json()

    resposta = api.put(url(historia), json=corpo(filter_id=filtro_do_beto["id"]), headers=ana)
    assert resposta.status_code == 404
    assert api.get(url(historia), headers=ana).status_code == 204  # nada foi gravado


def test_put_com_filtro_inexistente_responde_404(api, make_user, historia):
    _, headers = make_user()
    assert api.put(url(historia), json=corpo(filter_id=999_999), headers=headers).status_code == 404


def test_put_em_historia_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.put(url(999_999), json=corpo(), headers=headers).status_code == 404


def test_put_aceita_a_ultima_frase(api, make_user, historia):
    _, headers = make_user()
    assert api.put(url(historia), json=corpo(frase=4), headers=headers).status_code == 200


@pytest.mark.parametrize("frase", [5, 100])
def test_put_com_frase_alem_do_fim_da_historia_responde_422(api, make_user, historia, frase):
    _, headers = make_user()
    assert api.put(url(historia), json=corpo(frase=frase), headers=headers).status_code == 422
    assert api.get(url(historia), headers=headers).status_code == 204


@pytest.mark.parametrize(
    "mudanca",
    [
        {"segment_position": -1},
        {"offset_ms": -1},
        {"client_time": "ontem"},
        {"client_time": "2026-11-12T12:00:00"},  # sem fuso horário
        {"segment_position": None},
    ],
)
def test_put_com_corpo_invalido_responde_422(api, make_user, historia, mudanca):
    _, headers = make_user()
    assert api.put(url(historia), json={**corpo(), **mudanca}, headers=headers).status_code == 422


@pytest.mark.parametrize("campo", ["segment_position", "offset_ms", "client_time"])
def test_put_sem_campo_obrigatorio_responde_422(api, make_user, historia, campo):
    _, headers = make_user()
    dados = {k: v for k, v in corpo().items() if k != campo}
    assert api.put(url(historia), json=dados, headers=headers).status_code == 422


# ---------- DELETE ----------

def test_delete_apaga_o_progresso(api, make_user, historia):
    _, headers = make_user()
    api.put(url(historia), json=corpo(), headers=headers)

    assert api.delete(url(historia), headers=headers).status_code == 204
    assert api.get(url(historia), headers=headers).status_code == 204


def test_delete_sem_progresso_tambem_responde_204(api, make_user, historia):
    _, headers = make_user()
    assert api.delete(url(historia), headers=headers).status_code == 204


def test_delete_em_historia_inexistente_responde_404(api, make_user):
    _, headers = make_user()
    assert api.delete(url(999_999), headers=headers).status_code == 404


# ---------- GET /progress/recent ----------

def test_recent_do_mais_recente_para_o_mais_antigo(api, make_user, nova_historia):
    _, headers = make_user()
    h1, h2, h3 = nova_historia("Um"), nova_historia("Dois"), nova_historia("Três")
    api.put(url(h1), json=corpo(minutos=1), headers=headers)
    api.put(url(h2), json=corpo(minutos=3), headers=headers)
    api.put(url(h3), json=corpo(minutos=2), headers=headers)

    resposta = api.get("/progress/recent", headers=headers)
    assert resposta.status_code == 200
    assert [p["story_id"] for p in resposta.json()] == [h2, h3, h1]


def test_recent_respeita_o_limit(api, make_user, nova_historia):
    _, headers = make_user()
    for i in range(3):
        api.put(url(nova_historia(f"H{i}")), json=corpo(minutos=i), headers=headers)
    assert len(api.get("/progress/recent", params={"limit": 2}, headers=headers).json()) == 2


def test_recent_deixa_de_fora_as_concluidas(api, make_user, nova_historia):
    _, headers = make_user()
    em_andamento, concluida = nova_historia("A"), nova_historia("B")
    api.put(url(em_andamento), json=corpo(), headers=headers)
    api.put(url(concluida), json=corpo(minutos=1, completed=True), headers=headers)
    assert [p["story_id"] for p in api.get("/progress/recent", headers=headers).json()] == [em_andamento]


def test_recent_vazio_sem_progresso(api, make_user):
    _, headers = make_user()
    assert api.get("/progress/recent", headers=headers).json() == []


@pytest.mark.parametrize("limit", [0, -1, 51, "abc"])
def test_recent_com_limit_invalido_responde_422(api, make_user, limit):
    _, headers = make_user()
    assert api.get("/progress/recent", params={"limit": limit}, headers=headers).status_code == 422


# ---------- posse por usuário ----------

def test_um_usuario_nao_ve_nem_altera_o_progresso_de_outro(api, make_user, historia):
    _, ana = make_user(email="ana@teste.com")
    _, beto = make_user(email="beto@teste.com")
    api.put(url(historia), json=corpo(frase=3), headers=ana)

    # Beto não vê o progresso da Ana
    assert api.get(url(historia), headers=beto).status_code == 204
    assert api.get("/progress/recent", headers=beto).json() == []

    # O PUT do Beto cria o progresso DELE, sem tocar no da Ana
    api.put(url(historia), json=corpo(frase=1, minutos=5), headers=beto)
    assert api.get(url(historia), headers=ana).json()["segment_position"] == 3

    # O DELETE do Beto apaga só o progresso dele
    api.delete(url(historia), headers=beto)
    assert api.get(url(historia), headers=ana).json()["segment_position"] == 3
    assert [p["story_id"] for p in api.get("/progress/recent", headers=ana).json()] == [historia]


# ---------- autenticação ----------

@pytest.mark.parametrize(
    ("metodo", "caminho", "dados"),
    [
        ("get", "/stories/1/progress", None),
        ("put", "/stories/1/progress", corpo()),
        ("delete", "/stories/1/progress", None),
        ("get", "/progress/recent", None),
    ],
)
def test_sem_token_responde_401(api, metodo, caminho, dados):
    kwargs = {"json": dados} if dados is not None else {}
    assert api.request(metodo.upper(), caminho, **kwargs).status_code == 401


def test_token_invalido_responde_401(api):
    assert api.get("/progress/recent", headers={"Authorization": "Bearer lixo"}).status_code == 401
