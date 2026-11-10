"""Testes da interface de TTS (TTSProvider), do provedor falso e da fábrica por configuração (#80).

Escritos antes do código (TDD). Não usam rede, banco nem chave de API.
"""
import io
import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.integrations.tts import (
    FakeTTSProvider,
    SynthesisResult,
    TTSError,
    TTSProvider,
    create_tts_provider,
    get_tts_provider,
)

MS_POR_CARACTERE = 60  # regra do provedor falso: 60 ms de áudio por caractere de texto


def speak(corpo: str, idioma: str = "pt-BR") -> str:
    return f'<speak version="1.0" xml:lang="{idioma}">{corpo}</speak>'


def abrir_wav(resultado: SynthesisResult):
    return wave.open(io.BytesIO(resultado.data), "rb")


def amostras(resultado: SynthesisResult) -> list[int]:
    with abrir_wav(resultado) as wav:
        bruto = wav.readframes(wav.getnframes())
    return list(struct.unpack(f"<{len(bruto) // 2}h", bruto))


def potencia(trecho: list[int], taxa: int, frequencia: float) -> float:
    """Energia do trecho na frequência pedida (algoritmo de Goertzel): sem depender do numpy."""
    k = 2 * math.cos(2 * math.pi * frequencia / taxa)
    s1 = s2 = 0.0
    for x in trecho:
        s1, s2 = x + k * s1 - s2, s1
    return s1 * s1 + s2 * s2 - k * s1 * s2


def tom_dominante(trecho: list[int], taxa: int, candidatas=(330, 660)) -> int:
    return max(candidatas, key=lambda f: potencia(trecho, taxa, f))


# ---------- FakeTTSProvider: o áudio ----------

def test_devolve_um_wav_valido_mono_de_16_bits():
    resultado = FakeTTSProvider().synthesize(speak("Olá, mundo!"), "voz-qualquer")

    assert isinstance(resultado, SynthesisResult)
    assert resultado.format == "wav"
    assert resultado.data[:4] == b"RIFF" and resultado.data[8:12] == b"WAVE"
    with abrir_wav(resultado) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 8000


def test_duration_ms_e_igual_a_duracao_real_do_arquivo():
    resultado = FakeTTSProvider().synthesize(speak("A raposa desistiu das uvas."), "v")
    with abrir_wav(resultado) as wav:
        duracao_real = round(wav.getnframes() / wav.getframerate() * 1000)
    assert resultado.duration_ms == duracao_real


def test_duracao_e_de_60_ms_por_caractere():
    texto = "Olá, mundo!"  # 11 caracteres
    assert FakeTTSProvider().synthesize(speak(texto), "v").duration_ms == 11 * MS_POR_CARACTERE


def test_a_duracao_cresce_com_o_tamanho_do_texto():
    fake = FakeTTSProvider()
    curto = fake.synthesize(speak("Oi"), "v").duration_ms
    longo = fake.synthesize(speak("Oi, tudo bem com você hoje?"), "v").duration_ms
    assert longo > curto


def test_as_tags_ssml_nao_contam_na_duracao():
    fake = FakeTTSProvider()
    simples = fake.synthesize(speak("A raposa desistiu."), "v").duration_ms
    com_tags = fake.synthesize(
        speak('A raposa <lang xml:lang="pt-BR">desistiu</lang>.'), "v"
    ).duration_ms
    com_voz = fake.synthesize(
        '<speak version="1.0" xml:lang="pt-BR"><voice name="x">A raposa desistiu.</voice></speak>', "v"
    ).duration_ms
    assert simples == com_tags == com_voz


def test_espacos_repetidos_e_quebras_de_linha_contam_como_um():
    fake = FakeTTSProvider()
    assert fake.synthesize(speak("a  b\n c"), "v").duration_ms == fake.synthesize(speak("a b c"), "v").duration_ms


def test_espaco_sobrando_no_fim_do_texto_nao_conta_nem_vira_silencio():
    fake = FakeTTSProvider()
    sem_sobra = fake.synthesize(speak("Olá"), "v").duration_ms
    # o último pedaço é só um espaço, em outro idioma: some por inteiro
    com_sobra = fake.synthesize(speak('Olá<lang xml:lang="en-US"> </lang>'), "v").duration_ms
    assert sem_sobra == com_sobra == 3 * MS_POR_CARACTERE


def test_entidades_xml_contam_como_um_caractere():
    # "Tom &amp; Jerry" é o texto "Tom & Jerry": 11 caracteres
    assert FakeTTSProvider().synthesize(speak("Tom &amp; Jerry"), "v").duration_ms == 11 * MS_POR_CARACTERE


# ---------- FakeTTSProvider: tons diferentes por idioma ----------

def test_texto_so_no_idioma_base_tem_um_unico_tom_grave():
    resultado = FakeTTSProvider().synthesize(speak("A raposa desistiu das uvas."), "v")
    assert tom_dominante(amostras(resultado), 8000) == 330


def test_trecho_em_outro_idioma_soa_em_tom_agudo():
    # 10 caracteres em português, 10 em inglês ("turned off"), 10 em português
    ssml = speak('A raposa  <lang xml:lang="en-US">turned off</lang> a luz.', "pt-BR")
    resultado = FakeTTSProvider().synthesize(ssml, "v")
    sons = amostras(resultado)
    por_caractere = 8000 * MS_POR_CARACTERE // 1000  # amostras de cada caractere

    antes = sons[: 9 * por_caractere]  # "A raposa " (9 caracteres)
    trecho = sons[9 * por_caractere : 19 * por_caractere]  # "turned off"
    depois = sons[19 * por_caractere :]

    assert tom_dominante(antes, 8000) == 330
    assert tom_dominante(trecho, 8000) == 660
    assert tom_dominante(depois, 8000) == 330


def test_o_tom_agudo_depende_do_idioma_base_do_speak():
    # com o inglês como base, o trecho em português é que fica agudo
    ssml = speak('The fox was <lang xml:lang="pt-BR">relutante</lang> today', "en-US")
    sons = amostras(FakeTTSProvider().synthesize(ssml, "v"))
    por_caractere = 480
    antes = sons[: 12 * por_caractere]  # "The fox was " (12 caracteres)
    trecho = sons[12 * por_caractere : 21 * por_caractere]  # "relutante"
    assert tom_dominante(antes, 8000) == 330
    assert tom_dominante(trecho, 8000) == 660


def test_trecho_no_mesmo_idioma_do_base_continua_grave():
    ssml = speak('Olá <lang xml:lang="pt-BR">mundo</lang>', "pt-BR")
    assert tom_dominante(amostras(FakeTTSProvider().synthesize(ssml, "v")), 8000) == 330


def test_a_comparacao_de_idiomas_ignora_maiusculas():
    ssml = speak('Olá <lang xml:lang="PT-br">mundo</lang>', "pt-BR")
    assert tom_dominante(amostras(FakeTTSProvider().synthesize(ssml, "v")), 8000) == 330


# ---------- FakeTTSProvider: chamadas e erros ----------

def test_o_fake_guarda_as_chamadas_recebidas():
    fake = FakeTTSProvider()
    ssml_1, ssml_2 = speak("Primeira."), speak("Segunda.")
    fake.synthesize(ssml_1, "voz-a")
    fake.synthesize(ssml_2, "voz-b")

    assert [(c.ssml, c.voice_id) for c in fake.calls] == [(ssml_1, "voz-a"), (ssml_2, "voz-b")]


def test_cada_instancia_tem_a_sua_propria_lista_de_chamadas():
    um, outro = FakeTTSProvider(), FakeTTSProvider()
    um.synthesize(speak("Oi."), "v")
    assert len(um.calls) == 1 and outro.calls == []


def test_ssml_malformado_levanta_tts_error_sem_nova_tentativa():
    with pytest.raises(TTSError) as erro:
        FakeTTSProvider().synthesize("<speak><lang>sem fechar", "v")
    assert erro.value.retryable is False


def test_ssml_sem_texto_levanta_tts_error():
    with pytest.raises(TTSError) as erro:
        FakeTTSProvider().synthesize(speak("   "), "v")
    assert erro.value.retryable is False


def test_o_fake_cumpre_o_contrato_tts_provider():
    assert isinstance(FakeTTSProvider(), TTSProvider)


# ---------- TTSError ----------

def test_tts_error_carrega_se_vale_a_pena_tentar_de_novo():
    assert TTSError("fora do ar", retryable=True).retryable is True
    assert TTSError("chave inválida", retryable=False).retryable is False
    assert str(TTSError("fora do ar", retryable=True)) == "fora do ar"


def test_tts_error_nao_tenta_de_novo_por_padrao():
    assert TTSError("falhou").retryable is False


# ---------- fábrica por configuração ----------

def test_o_valor_padrao_e_o_provedor_falso():
    """Um clone novo, sem chave de API, sobe com o provedor falso."""
    settings = Settings()
    assert settings.tts_provider == "fake"
    assert settings.tts_api_key == ""
    assert isinstance(create_tts_provider(settings), FakeTTSProvider)


def test_a_fabrica_escolhe_a_implementacao_pela_configuracao():
    assert isinstance(create_tts_provider(Settings(tts_provider="fake")), FakeTTSProvider)


def test_a_fabrica_recusa_provedor_desconhecido_com_mensagem_clara():
    with pytest.raises(ValueError) as erro:
        create_tts_provider(Settings(tts_provider="inexistente"))
    mensagem = str(erro.value)
    assert "TTS_PROVIDER" in mensagem and "inexistente" in mensagem and "fake" in mensagem


@pytest.fixture
def sem_cache_do_tts():
    """get_tts_provider e as Settings são guardados em cache: limpa antes e depois do teste."""
    get_settings.cache_clear()
    get_tts_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_tts_provider.cache_clear()


def test_get_tts_provider_devolve_sempre_a_mesma_instancia(sem_cache_do_tts):
    assert get_tts_provider() is get_tts_provider()


def test_get_tts_provider_le_a_variavel_de_ambiente(sem_cache_do_tts, monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "fake")
    assert isinstance(get_tts_provider(), FakeTTSProvider)


def test_provedor_desconhecido_derruba_a_subida_da_api(sem_cache_do_tts, monkeypatch):
    """Erro de configuração aparece ao subir, e não na primeira requisição de um usuário."""
    from app.main import create_app  # importar o módulo já cria a app, o que enche o cache das Settings

    monkeypatch.setenv("TTS_PROVIDER", "inexistente")
    get_settings.cache_clear()  # depois do import e da variável: as Settings precisam ser lidas de novo
    get_tts_provider.cache_clear()
    with pytest.raises(ValueError, match="inexistente"):
        with TestClient(create_app()):
            pass


def test_get_tts_provider_funciona_como_dependencia_e_aceita_override():
    app = FastAPI()

    @app.get("/nome")
    def nome(tts: TTSProvider = Depends(get_tts_provider)) -> dict[str, str]:
        return {"classe": type(tts).__name__}

    cliente = TestClient(app)
    assert cliente.get("/nome").json() == {"classe": "FakeTTSProvider"}

    outro = FakeTTSProvider()
    app.dependency_overrides[get_tts_provider] = lambda: outro
    assert cliente.get("/nome").status_code == 200


# ---------- documentação ----------

BACKEND = Path(__file__).resolve().parents[1]  # a pasta backend (no container, /app)
README = BACKEND.parent / "README.md"


@pytest.mark.parametrize("variavel", ["TTS_PROVIDER", "TTS_API_KEY", "TTS_REGION", "TTS_VOICE_ID"])
def test_env_example_documenta_as_variaveis(variavel):
    assert variavel in (BACKEND / ".env.example").read_text(encoding="utf-8")


@pytest.mark.skipif(not README.exists(), reason="o container da API só enxerga a pasta backend")
@pytest.mark.parametrize("variavel", ["TTS_PROVIDER", "TTS_API_KEY", "TTS_REGION", "TTS_VOICE_ID"])
def test_readme_documenta_as_variaveis(variavel):
    assert variavel in README.read_text(encoding="utf-8")
