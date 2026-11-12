"""Testes de ponta a ponta do pipeline NLP -> TTS e da API de áudio (#88).

Cobrem o caminho completo como o front o percorre: cadastro, login, filtro, prévia, geração, status e
download de cada frase com `Range`. Complementam os testes por camada (`test_audio_facade.py`,
`test_audio_generation_api.py`, `test_audio_cache_generation.py`, `test_story_preview.py`): aqui o foco é
a COERÊNCIA entre as etapas (a prévia mostra o que o áudio fala; o arquivo tem os tons certos).

Sem rede, sem chave e sem MinIO: FakeTTSProvider + InMemoryStorage + banco de teste (transação desfeita).
"""
import io
import math
import re
import struct
import wave
from urllib.parse import parse_qs, urlsplit

# Fixtures e auxiliares reaproveitados dos testes por camada (o pytest as encontra neste módulo)
from tests.test_audio_facade import FRASES, TTSComFalhas  # noqa: F401
from tests.test_audio_generation_api import (  # noqa: F401
    ana,
    audio_da_frase,
    criar_filtro,
    gerar,
    historia,
    sessoes,
    status_de,
    storage,
    tts,
)

BASE_HZ, TROCA_HZ = 330, 660


def previa(api, headers, story_id, filter_id) -> dict:
    resposta = api.get(f"/stories/{story_id}/preview", params={"filter_id": filter_id}, headers=headers)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def baixar(api, headers, segment_id, filter_id, intervalo: str | None = None):
    """Pede a URL assinada da frase e baixa o arquivo como o <audio> faz: sem token, com Range opcional."""
    corpo = audio_da_frase(api, headers, segment_id, filter_id).json()
    params = {k: v[0] for k, v in parse_qs(urlsplit(corpo["url"]).query).items()}
    extra = {"Range": intervalo} if intervalo else {}
    return corpo, api.get("/audio/stream", params=params, headers=extra)


def energia(wav: bytes, hz: int) -> float:
    """Energia do sinal na frequência `hz` (algoritmo de Goertzel), normalizada pelo tamanho."""
    with wave.open(io.BytesIO(wav)) as f:
        taxa, bruto = f.getframerate(), f.readframes(f.getnframes())
    amostras = struct.unpack(f"<{len(bruto) // 2}h", bruto)
    coef = 2 * math.cos(2 * math.pi * hz / taxa)
    s1 = s2 = 0.0
    for x in amostras:
        s1, s2 = x + coef * s1 - s2, s1
    return (s1 * s1 + s2 * s2 - coef * s1 * s2) / len(amostras) ** 2


def test_fluxo_completo_cadastro_filtro_geracao_status_e_download(api, make_user, sessoes, historia, tts):
    _, headers = make_user("Ana")
    filtro = criar_filtro(api, headers, historia.id)

    resposta = gerar(api, headers, historia.id, filtro)
    assert resposta.status_code == 202

    estado = status_de(api, headers, historia.id, filtro).json()
    assert (estado["state"], estado["total"], estado["ready"], estado["failed"]) == ("ready", 3, 3, 0)
    assert len(tts.calls) == 3

    for frase in historia.segments:
        corpo, inteiro = baixar(api, headers, frase.id, filtro)
        assert inteiro.status_code == 200
        with wave.open(io.BytesIO(inteiro.content)) as f:
            duracao_ms = round(1000 * f.getnframes() / f.getframerate())
        assert abs(duracao_ms - corpo["duration_ms"]) <= 1  # o metadado confere com o arquivo

        pedaco = baixar(api, headers, frase.id, filtro, "bytes=0-43")[1]
        assert pedaco.status_code == 206
        assert pedaco.content == inteiro.content[:44]
        assert pedaco.headers["content-range"] == f"bytes 0-43/{len(inteiro.content)}"


def test_a_previa_mostra_exatamente_o_que_o_tts_recebe(api, make_user, sessoes, historia, tts):
    _, headers = make_user()
    filtro = criar_filtro(api, headers, historia.id)
    trocas = [s["swaps"] for s in previa(api, headers, historia.id, filtro)["segments"]]
    gerar(api, headers, historia.id, filtro)

    assert len(tts.calls) == len(trocas) == 3
    for chamada, da_previa in zip(tts.calls, trocas):
        no_ssml = re.findall(r'<lang xml:lang="([a-zA-Z-]+)">(.*?)</lang>', chamada.ssml)
        assert no_ssml == [(t["lang"], t["spoken"]) for t in da_previa]
    assert sum(len(t) for t in trocas) == 2  # densidade alta: 60% de 3 candidatos


def test_o_audio_tem_o_tom_do_idioma_base_e_o_da_troca_so_onde_a_previa_manda(
    api, make_user, sessoes, historia
):
    _, headers = make_user()
    filtro = criar_filtro(api, headers, historia.id)
    segmentos = previa(api, headers, historia.id, filtro)["segments"]
    gerar(api, headers, historia.id, filtro)

    for frase, da_previa in zip(historia.segments, segmentos):
        wav = baixar(api, headers, frase.id, filtro)[1].content
        assert energia(wav, BASE_HZ) > 0  # o idioma base está sempre presente
        com_troca = energia(wav, TROCA_HZ) > 1e-3 * energia(wav, BASE_HZ)
        assert com_troca == bool(da_previa["swaps"])


def test_falha_definitiva_so_derruba_a_propria_frase_e_o_novo_pedido_a_recupera(
    api, make_user, sessoes, historia, tts, storage
):
    from app.integrations.tts import get_tts_provider
    from app.main import app

    _, headers = make_user()
    filtro = criar_filtro(api, headers, historia.id)
    quebrado = TTSComFalhas("desligou", retryable=False)  # só a frase 2 (pt: "Ele desligou a luz.")
    app.dependency_overrides[get_tts_provider] = lambda: quebrado

    gerar(api, headers, historia.id, filtro)
    estado = status_de(api, headers, historia.id, filtro).json()
    assert (estado["state"], estado["ready"], estado["failed"]) == ("failed", 2, 1)
    estados = [s["status"] for s in estado["segments"]]
    assert estados == ["ready", "failed", "ready"]

    # as boas tocam; a que falhou responde 409, nunca um áudio parcial
    assert baixar(api, headers, historia.segments[0].id, filtro)[1].status_code == 200
    assert audio_da_frase(api, headers, historia.segments[1].id, filtro).status_code == 409

    # o fornecedor volta: um novo pedido tenta só a que falhou
    quebrado.restantes = 0
    chamadas_antes = len(quebrado.calls)
    gerar(api, headers, historia.id, filtro)
    estado = status_de(api, headers, historia.id, filtro).json()
    assert (estado["state"], estado["ready"], estado["failed"]) == ("ready", 3, 0)
    assert len(quebrado.calls) == chamadas_antes + 1
    assert baixar(api, headers, historia.segments[1].id, filtro)[1].status_code == 200


def test_falha_recuperavel_do_fornecedor_termina_pronta_na_mesma_geracao(
    api, make_user, sessoes, historia, monkeypatch
):
    import time

    from app.integrations.tts import get_tts_provider
    from app.main import app

    monkeypatch.setattr(time, "sleep", lambda _: None)  # sem espera real entre as tentativas
    _, headers = make_user()
    filtro = criar_filtro(api, headers, historia.id)
    instavel = TTSComFalhas("desligou", retryable=True, vezes=1)
    app.dependency_overrides[get_tts_provider] = lambda: instavel

    gerar(api, headers, historia.id, filtro)

    estado = status_de(api, headers, historia.id, filtro).json()
    assert (estado["state"], estado["ready"], estado["failed"]) == ("ready", 3, 0)
    assert len(instavel.calls) == 4  # 3 frases + 1 nova tentativa


def test_outro_usuario_com_as_mesmas_regras_reaproveita_o_audio_sem_chamar_o_tts(
    api, make_user, sessoes, historia, tts
):
    _, ana_h = make_user("Ana")
    _, bruno_h = make_user("Bruno")
    gerar(api, ana_h, historia.id, criar_filtro(api, ana_h, historia.id))
    assert len(tts.calls) == 3

    filtro_bruno = criar_filtro(api, bruno_h, historia.id)
    gerar(api, bruno_h, historia.id, filtro_bruno)

    assert len(tts.calls) == 3  # tudo veio do cache global
    estado = status_de(api, bruno_h, historia.id, filtro_bruno).json()
    assert (estado["state"], estado["ready"]) == ("ready", 3)
    assert baixar(api, bruno_h, historia.segments[0].id, filtro_bruno)[1].status_code == 200


def test_cada_usuario_so_baixa_o_audio_pelo_proprio_filtro(api, make_user, sessoes, historia):
    _, ana_h = make_user("Ana")
    _, bruno_h = make_user("Bruno")
    filtro = criar_filtro(api, ana_h, historia.id)
    gerar(api, ana_h, historia.id, filtro)

    assert audio_da_frase(api, bruno_h, historia.segments[0].id, filtro).status_code == 404
    assert status_de(api, bruno_h, historia.id, filtro).status_code == 404


def test_url_assinada_adulterada_e_recusada(api, make_user, sessoes, historia):
    _, headers = make_user()
    filtro = criar_filtro(api, headers, historia.id)
    gerar(api, headers, historia.id, filtro)
    corpo = audio_da_frase(api, headers, historia.segments[0].id, filtro).json()
    params = {k: v[0] for k, v in parse_qs(urlsplit(corpo["url"]).query).items()}
    assert api.get("/audio/stream", params=params).status_code == 200

    adulterada = {**params, "key": params["key"] + "x"}
    assert api.get("/audio/stream", params=adulterada).status_code == 403
