"""Testes do áudio único da história (GET /stories/{id}/audio/full): todas as frases num arquivo só, com a
linha do tempo de cada uma, para o player voltar a qualquer palavra.

Usam a API inteira com a autenticação real, o FakeTTSProvider (WAV) e o InMemoryStorage: sem rede e sem chave.
"""
import io
import wave
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.integrations.tts import get_tts_provider
from app.main import app
from app.modules.audio.full_track import UnsupportedAudioFormat, join_audio, track_key
from tests.test_audio_facade import TTSComFalhas
from tests.test_audio_generation_api import (  # noqa: F401
    ana,
    criar_filtro,
    gerar,
    historia,
    sessoes,
    status_de,
    storage,
    tts,
)


def completo(api, headers, story_id, filter_id):
    return api.get(f"/stories/{story_id}/audio/full", params={"filter_id": filter_id}, headers=headers)


def parametros(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def wav(frames: int, rate: int = 8000, canais: int = 1) -> bytes:
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * frames * canais)
    return saida.getvalue()


# ---------- juntar os arquivos ----------

def test_juntar_wav_soma_as_amostras_e_gera_um_cabecalho_valido():
    junto = join_audio([wav(800), wav(1600), wav(400)], "wav")

    with wave.open(io.BytesIO(junto)) as w:
        assert w.getnframes() == 2800
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 8000)


def test_juntar_mp3_cola_os_arquivos_na_ordem():
    assert join_audio([b"AAA", b"BB", b"C"], "mp3") == b"AAABBC"


def test_wav_com_parametros_diferentes_nao_e_juntado():
    with pytest.raises(UnsupportedAudioFormat):
        join_audio([wav(100, rate=8000), wav(100, rate=16000)], "wav")


def test_formato_desconhecido_nao_e_juntado():
    with pytest.raises(UnsupportedAudioFormat):
        join_audio([b"x"], "ogg")


def test_a_chave_do_arquivo_muda_quando_alguma_frase_muda():
    a, b, c = (SimpleNamespace(storage_key=k) for k in ("cache/a.wav", "cache/b.wav", "cache/c.wav"))
    assert track_key([a, b], "wav") == track_key([a, b], "wav")
    assert track_key([a, b], "wav") != track_key([a, c], "wav")
    assert track_key([a, b], "wav") != track_key([b, a], "wav")
    assert track_key([a, b], "wav").startswith("full/") and track_key([a, b], "wav").endswith(".wav")


# ---------- o endpoint ----------

def test_devolve_a_linha_do_tempo_das_frases_em_ordem(api, ana, historia, storage):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)
    duracoes = {s["segment_id"]: s["duration_ms"] for s in status_de(api, ana, historia.id, filtro).json()["segments"]}

    resposta = completo(api, ana, historia.id, filtro)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["format"] == "wav" and corpo["skipped"] == []
    assert [s["segment_id"] for s in corpo["segments"]] == [f.id for f in historia.segments]
    assert [s["position"] for s in corpo["segments"]] == [0, 1, 2]
    inicio = 0
    for segmento in corpo["segments"]:
        assert segmento["start_ms"] == inicio  # cada frase começa onde a anterior termina
        assert segmento["duration_ms"] == duracoes[segmento["segment_id"]]
        inicio += segmento["duration_ms"]
    assert corpo["duration_ms"] == inicio


def test_o_arquivo_tem_a_duracao_da_soma_das_frases_e_toca_com_range(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)
    corpo = completo(api, ana, historia.id, filtro).json()
    url = urlsplit(corpo["url"])
    assert url.path == "/audio/stream"
    params = parametros(corpo["url"])

    inteiro = api.get("/audio/stream", params=params)
    assert inteiro.status_code == 200
    with wave.open(io.BytesIO(inteiro.content)) as w:
        duracao_ms = round(1000 * w.getnframes() / w.getframerate())
    assert abs(duracao_ms - corpo["duration_ms"]) <= len(corpo["segments"])  # no máximo 1 ms por frase

    trecho = api.get("/audio/stream", params=params, headers={"Range": "bytes=0-3"})
    assert trecho.status_code == 206 and trecho.content == b"RIFF"
    meio = api.get("/audio/stream", params=params, headers={"Range": "bytes=1000-1999"})
    assert meio.status_code == 206 and meio.content == inteiro.content[1000:2000]  # pular para o meio


def test_o_arquivo_e_montado_uma_vez_e_reaproveitado(api, ana, historia, storage):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)

    primeira = completo(api, ana, historia.id, filtro).json()
    antes = {k for k in storage._objects if k.startswith("full/")}
    segunda = completo(api, ana, historia.id, filtro).json()
    depois = {k for k in storage._objects if k.startswith("full/")}

    assert len(antes) == 1 and antes == depois
    assert parametros(primeira["url"])["key"] == parametros(segunda["url"])["key"]


def test_antes_de_gerar_responde_409(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    resposta = completo(api, ana, historia.id, filtro)
    assert resposta.status_code == 409
    assert "ainda não está pronto" in resposta.json()["detail"]


def test_com_a_geracao_em_andamento_responde_409(api, ana, historia, db_session):
    from app.modules.audio.repository import AudioAssetRepository, compute_rules_hash
    from app.core.config import get_settings
    from tests.test_audio_generation_api import REGRAS

    filtro = criar_filtro(api, ana, historia.id)
    repo = AudioAssetRepository(db_session)
    for frase in historia.segments:
        repo.get_or_create(
            story_id=historia.id, segment_id=frase.id, rules_hash=compute_rules_hash(REGRAS),
            voice_id=get_settings().tts_voice_id,
        )  # `pending`: ninguém gerou ainda

    assert completo(api, ana, historia.id, filtro).status_code == 409


def test_frase_que_falhou_fica_de_fora_e_o_resto_toca(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    app.dependency_overrides[get_tts_provider] = lambda: TTSComFalhas("desligou", retryable=False)
    gerar(api, ana, historia.id, filtro)

    corpo = completo(api, ana, historia.id, filtro).json()

    falhou = historia.segments[1].id
    assert corpo["skipped"] == [falhou]
    assert [s["segment_id"] for s in corpo["segments"]] == [historia.segments[0].id, historia.segments[2].id]
    assert corpo["segments"][1]["start_ms"] == corpo["segments"][0]["duration_ms"]  # sem buraco no lugar da frase


def test_se_todas_as_frases_falharam_responde_409(api, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    app.dependency_overrides[get_tts_provider] = lambda: TTSComFalhas("", retryable=False)
    gerar(api, ana, historia.id, filtro)

    assert completo(api, ana, historia.id, filtro).status_code == 409


def test_sem_token_responde_401(api, historia, sessoes):
    assert api.get(f"/stories/{historia.id}/audio/full", params={"filter_id": 1}).status_code == 401


def test_filtro_de_outro_usuario_responde_404(api, make_user, ana, historia):
    filtro = criar_filtro(api, ana, historia.id)
    gerar(api, ana, historia.id, filtro)
    _, bruno = make_user("Bruno")
    assert completo(api, bruno, historia.id, filtro).status_code == 404


def test_historia_inexistente_responde_404(api, ana):
    assert completo(api, ana, 999_999, 1).status_code == 404


def test_filtro_sem_filter_id_responde_422(api, ana, historia):
    assert api.get(f"/stories/{historia.id}/audio/full", headers=ana).status_code == 422


def test_a_rota_esta_no_docs(api):
    assert "/stories/{story_id}/audio/full" in api.get("/openapi.json").json()["paths"]
