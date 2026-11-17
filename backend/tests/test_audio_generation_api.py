"""Testes dos endpoints de geração, status e áudio por segmento (#86).

Usam a API inteira com a autenticação real, o banco de teste, o FakeTTSProvider e o InMemoryStorage.
No TestClient, a tarefa em segundo plano roda logo depois da resposta, antes de `api.post` voltar.
"""
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.storage import InMemoryStorage, get_storage
from app.integrations.tts import FakeTTSProvider, TTSError, get_tts_provider
from app.main import app
from app.modules.audio.generation_router import get_session_factory
from app.modules.audio.generation_service import jobs
from app.modules.audio.repository import compute_rules_hash
from tests.test_audio_facade import nova_historia

REGRAS = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"}


@pytest.fixture
def historia(db_session):
    story = nova_historia()
    db_session.add(story)
    db_session.commit()
    return story


@pytest.fixture
def tts():
    return FakeTTSProvider()


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def sessoes(api, db_session, tts, storage):
    """Troca as dependências externas e devolve a lista das sessões abertas pela tarefa em segundo plano."""
    abertas: list[Session] = []

    def nova_sessao() -> Session:
        session = Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")
        abertas.append(session)
        return session

    app.dependency_overrides[get_tts_provider] = lambda: tts
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_session_factory] = lambda: nova_sessao
    return abertas


@pytest.fixture
def ana(make_user, sessoes):
    return make_user("Ana")[1]


def criar_filtro(api, headers, story_id, regras=REGRAS) -> int:
    resposta = api.post("/filters", json={"story_id": story_id, "rules": regras}, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def gerar(api, headers, story_id, filter_id):
    return api.post(f"/stories/{story_id}/audio", json={"filter_id": filter_id}, headers=headers)


def status_de(api, headers, story_id, filter_id):
    return api.get(f"/stories/{story_id}/audio/status", params={"filter_id": filter_id}, headers=headers)


def audio_da_frase(api, headers, segment_id, filter_id):
    return api.get(f"/audio/segments/{segment_id}", params={"filter_id": filter_id}, headers=headers)


# ---------- POST /stories/{id}/audio ----------

def test_post_responde_202_e_gera_em_segundo_plano(api, ana, historia, tts, sessoes, db_session):
    filtro = criar_filtro(api, ana, historia.id)

    resposta = gerar(api, ana, historia.id, filtro)

    assert resposta.status_code == 202
    assert resposta.json()["state"] == "generating"
    assert resposta.json()["total"] == 3
    # A tarefa rodou com uma sessão própria, diferente da sessão da requisição, e a fechou
    assert len(sessoes) == 1 and sessoes[0] is not db_session
    assert len(tts.calls) == 3
    assert any('<lang xml:lang="en-US">' in c.ssml for c in tts.calls)


def test_post_depois_de_pronto_responde_200_sem_chamar_o_tts(api, ana, historia, tts):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)

    resposta = gerar(api, ana, historia.id, filtro)

    assert resposta.status_code == 200
    assert resposta.json()["state"] == "ready"
    assert resposta.json()["ready"] == 3
    assert len(tts.calls) == 3


def test_post_durante_a_geracao_nao_dispara_outra(api, ana, historia, tts, sessoes):
    filtro = criar_filtro(api, ana, historia.id)
    chave = (historia.id, compute_rules_hash(REGRAS), get_settings().tts_voice_id)
    assert jobs.try_start(chave)  # uma geração já em andamento
    try:
        resposta = gerar(api, ana, historia.id, filtro)
        assert resposta.status_code == 202
        assert resposta.json()["state"] == "generating"
        assert status_de(api, ana, historia.id, filtro).json()["state"] == "generating"
    finally:
        jobs.finish(chave)

    assert tts.calls == [] and sessoes == []


def test_post_sem_token_responde_401(api, historia, sessoes):
    assert api.post(f"/stories/{historia.id}/audio", json={"filter_id": 1}).status_code == 401


def test_post_com_filtro_de_outro_usuario_responde_404(api, make_user, ana, historia, tts):
    filtro_da_ana = criar_filtro(api, ana, historia.id)
    _, bruno = make_user("Bruno")

    resposta = gerar(api, bruno, historia.id, filtro_da_ana)

    assert resposta.status_code == 404
    assert tts.calls == []


def test_post_com_historia_inexistente_responde_404(api, ana):
    filtro = criar_filtro(api, ana, None)
    assert gerar(api, ana, 999_999_999, filtro).status_code == 404


def test_post_com_filtro_de_outra_historia_responde_422(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id + 1)
    assert gerar(api, ana, historia.id, filtro).status_code == 422


def test_post_sem_filter_id_responde_422(api, ana, historia):
    assert api.post(f"/stories/{historia.id}/audio", json={}, headers=ana).status_code == 422


# ---------- GET /stories/{id}/audio/status ----------

def test_status_antes_de_gerar_mostra_tudo_pendente(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)

    corpo = status_de(api, ana, historia.id, filtro).json()

    assert corpo["state"] == "pending"
    assert (corpo["total"], corpo["ready"], corpo["failed"]) == (3, 0, 0)
    assert [s["segment_id"] for s in corpo["segments"]] == [s.id for s in historia.segments]
    assert all(s["status"] == "pending" for s in corpo["segments"])


def test_status_depois_de_gerar_mostra_tudo_pronto(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)

    corpo = status_de(api, ana, historia.id, filtro).json()

    assert corpo["state"] == "ready"
    assert (corpo["total"], corpo["ready"], corpo["failed"]) == (3, 3, 0)
    assert [s["position"] for s in corpo["segments"]] == [0, 1, 2]
    assert all(s["status"] == "ready" and s["duration_ms"] > 0 for s in corpo["segments"])


def test_status_com_frase_que_falhou(api, ana, historia, tts):
    def falha_na_segunda(ssml, voice_id, original=tts.synthesize):
        if "desligou" in ssml:
            raise TTSError("SSML recusado", retryable=False)
        return original(ssml, voice_id)

    tts.synthesize = falha_na_segunda
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)

    corpo = status_de(api, ana, historia.id, filtro).json()

    assert corpo["state"] == "failed"
    assert (corpo["ready"], corpo["failed"]) == (2, 1)
    assert [s["status"] for s in corpo["segments"]] == ["ready", "failed", "ready"]
    assert corpo["segments"][1]["error"] == "SSML recusado"


def test_status_sem_token_responde_401(api, historia, sessoes):
    assert api.get(f"/stories/{historia.id}/audio/status", params={"filter_id": 1}).status_code == 401


def test_status_com_filtro_de_outro_usuario_responde_404(api, make_user, ana, historia):
    filtro_da_ana = criar_filtro(api, ana, historia.id)
    _, bruno = make_user("Bruno")
    assert status_de(api, bruno, historia.id, filtro_da_ana).status_code == 404


# ---------- GET /audio/segments/{id} ----------

def test_audio_da_frase_devolve_url_assinada_que_toca_com_range(api, ana, historia, storage):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)
    frase = historia.segments[0]

    resposta = audio_da_frase(api, ana, frase.id, filtro)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["segment_id"] == frase.id
    assert corpo["format"] == "wav" and corpo["duration_ms"] > 0
    url = urlsplit(corpo["url"])
    assert url.path == "/audio/stream"

    # O <audio> pede sem token, com Range
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    trecho = api.get("/audio/stream", params=params, headers={"Range": "bytes=0-3"})
    assert trecho.status_code == 206
    assert trecho.content == b"RIFF"
    assert trecho.headers["content-type"] == "audio/x-wav" or trecho.headers["content-type"].startswith("audio/")
    inteiro = api.get("/audio/stream", params=params)
    assert inteiro.status_code == 200
    assert inteiro.content == storage.get(params["key"])


def test_audio_da_frase_ainda_nao_pronta_responde_409(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)

    resposta = audio_da_frase(api, ana, historia.segments[0].id, filtro)

    assert resposta.status_code == 409
    assert "ainda não está pronto" in resposta.json()["detail"]


def test_audio_da_frase_que_falhou_responde_409(api, ana, historia, tts):
    def sempre_falha(ssml, voice_id):
        raise TTSError("SSML recusado", retryable=False)

    tts.synthesize = sempre_falha
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)

    resposta = audio_da_frase(api, ana, historia.segments[0].id, filtro)

    assert resposta.status_code == 409
    assert "falhou" in resposta.json()["detail"]


def test_audio_da_frase_com_filtro_de_outro_usuario_responde_404(api, make_user, ana, historia):
    filtro_da_ana = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro_da_ana)
    _, bruno = make_user("Bruno")

    assert audio_da_frase(api, bruno, historia.segments[0].id, filtro_da_ana).status_code == 404


def test_audio_de_frase_inexistente_responde_404(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    assert audio_da_frase(api, ana, 999_999_999, filtro).status_code == 404


def test_audio_da_frase_sem_token_responde_401(api, historia, sessoes):
    assert api.get(f"/audio/segments/{historia.segments[0].id}", params={"filter_id": 1}).status_code == 401


def test_audio_da_frase_com_outro_filtro_nao_reaproveita_regras_diferentes(api, ana, historia):
    """O áudio depende das regras: um filtro com outra densidade ainda não tem áudio pronto."""
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)
    outro = criar_filtro(api, ana, historia.id, {**REGRAS, "density": "low"})

    assert audio_da_frase(api, ana, historia.segments[0].id, outro).status_code == 409


# ---------- GET /audio/url (só em desenvolvimento) ----------

def test_audio_url_generico_responde_404_fora_de_desenvolvimento(api, ana, storage):
    storage.put("samples/teste.wav", b"RIFF")
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="production")

    resposta = api.get("/audio/url", params={"key": "samples/teste.wav"}, headers=ana)

    assert resposta.status_code == 404


def test_audio_url_generico_continua_em_desenvolvimento(api, ana, storage):
    storage.put("samples/teste.wav", b"RIFF")
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="development")

    assert api.get("/audio/url", params={"key": "samples/teste.wav"}, headers=ana).status_code == 200


def test_os_tres_endpoints_estao_no_docs(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert "post" in paths["/stories/{story_id}/audio"]
    assert "get" in paths["/stories/{story_id}/audio/status"]
    assert "get" in paths["/audio/segments/{segment_id}"]
