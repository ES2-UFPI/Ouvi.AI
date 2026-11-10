"""Testes do adaptador de TTS real, o Azure Speech (#81).

Escritos antes do código (TDD). O Azure é simulado com `httpx.MockTransport`: os testes rodam sem rede,
sem chave e sem custo. O único teste que fala com o Azure de verdade é o `tts_real`, no fim do arquivo,
e ele é pulado quando não há chave configurada.
"""
import logging
from xml.etree import ElementTree

import httpx
import pytest

from app.core.config import Settings
from app.integrations.tts import TTSError, TTSProvider, create_tts_provider
from app.integrations.tts.azure import DEFAULT_OUTPUT_FORMAT, AzureTTSAdapter

CHAVE = "chave-super-secreta-123"
REGIAO = "brazilsouth"
VOZ = "pt-BR-ThalitaMultilingualNeural"

SSML_NS = "{http://www.w3.org/2001/10/synthesis}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# 48 kbit/s (o formato padrão) = 6.000 bytes por segundo de áudio
UM_SEGUNDO_DE_MP3 = b"\xff\xf3" + b"\x00" * 5998


def speak(corpo: str, idioma: str = "pt-BR") -> str:
    return f'<speak version="1.0" xml:lang="{idioma}">{corpo}</speak>'


SSML_BILINGUE = speak('A raposa <lang xml:lang="en-US">gave up</lang> das uvas.')


class AzureFalso:
    """Faz o papel do Azure: devolve as respostas da fila, na ordem, e guarda as requisições recebidas.

    Cada item da fila é uma `httpx.Response` ou uma exceção do httpx (levantada como erro de rede).
    """

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.requisicoes: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def ok(audio: bytes = UM_SEGUNDO_DE_MP3) -> httpx.Response:
    return httpx.Response(200, content=audio, headers={"Content-Type": "audio/mpeg"})


def erro(status: int, corpo: str = "") -> httpx.Response:
    return httpx.Response(status, text=corpo)


def adaptador(azure: AzureFalso, esperas: list[float] | None = None, **kwargs) -> AzureTTSAdapter:
    """Adaptador ligado ao Azure falso. As esperas entre tentativas vão para a lista, sem dormir de verdade."""
    esperas = esperas if esperas is not None else []
    return AzureTTSAdapter(
        api_key=CHAVE,
        region=REGIAO,
        client=httpx.Client(transport=httpx.MockTransport(azure)),
        sleep=esperas.append,
        **kwargs,
    )


def ssml_enviado(azure: AzureFalso, indice: int = 0) -> ElementTree.Element:
    return ElementTree.fromstring(azure.requisicoes[indice].content)


# ---------- a requisição ----------

def test_faz_post_no_endpoint_da_regiao():
    azure = AzureFalso(ok())
    adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    requisicao = azure.requisicoes[0]
    assert requisicao.method == "POST"
    assert str(requisicao.url) == f"https://{REGIAO}.tts.speech.microsoft.com/cognitiveservices/v1"


def test_envia_a_chave_o_tipo_ssml_e_o_formato_mp3_nos_cabecalhos():
    azure = AzureFalso(ok())
    adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    cabecalhos = azure.requisicoes[0].headers
    assert cabecalhos["Ocp-Apim-Subscription-Key"] == CHAVE
    assert cabecalhos["Content-Type"].startswith("application/ssml+xml")
    assert cabecalhos["X-Microsoft-OutputFormat"] == DEFAULT_OUTPUT_FORMAT
    assert "mp3" in DEFAULT_OUTPUT_FORMAT
    assert cabecalhos["User-Agent"]  # o Azure exige um User-Agent


# ---------- a voz e o SSML ----------

def test_coloca_a_voz_pedida_em_volta_do_texto():
    azure = AzureFalso(ok())
    adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    raiz = ssml_enviado(azure)
    assert raiz.tag == f"{SSML_NS}speak"  # o Azure exige o namespace do SSML no <speak>
    vozes = raiz.findall(f"{SSML_NS}voice")
    assert len(vozes) == 1 and vozes[0].get("name") == VOZ
    assert vozes[0].text.startswith("A raposa")


def test_mantem_o_idioma_base_e_os_trechos_em_outro_idioma():
    azure = AzureFalso(ok())
    adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    raiz = ssml_enviado(azure)
    assert raiz.get(XML_LANG) == "pt-BR"
    trecho = raiz.find(f".//{SSML_NS}lang")
    assert trecho.get(XML_LANG) == "en-US"
    assert trecho.text == "gave up"
    assert trecho.tail == " das uvas."


def test_nao_duplica_a_voz_se_o_ssml_ja_tiver_uma():
    azure = AzureFalso(ok())
    ssml = speak(f'<voice name="{VOZ}">Olá, mundo!</voice>')
    adaptador(azure).synthesize(ssml, VOZ)

    assert len(ssml_enviado(azure).findall(f".//{SSML_NS}voice")) == 1


def test_ssml_malformado_levanta_tts_error_sem_chamar_o_azure():
    azure = AzureFalso()
    with pytest.raises(TTSError) as falha:
        adaptador(azure).synthesize("<speak><lang>sem fechar", VOZ)
    assert falha.value.retryable is False
    assert azure.requisicoes == []


# ---------- o resultado ----------

def test_devolve_o_mp3_recebido():
    azure = AzureFalso(ok())
    resultado = adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    assert resultado.format == "mp3"
    assert resultado.data == UM_SEGUNDO_DE_MP3


def test_duration_ms_vem_do_tamanho_do_arquivo_e_do_bitrate():
    azure = AzureFalso(ok(UM_SEGUNDO_DE_MP3 * 3))  # 3 segundos a 48 kbit/s
    assert adaptador(azure).synthesize(SSML_BILINGUE, VOZ).duration_ms == 3000


def test_resposta_200_sem_audio_levanta_tts_error():
    azure = AzureFalso(ok(b""))
    with pytest.raises(TTSError):
        adaptador(azure, max_retries=0).synthesize(SSML_BILINGUE, VOZ)


# ---------- novas tentativas ----------

@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_erro_temporario_tenta_mais_3_vezes_e_depois_desiste(status):
    azure = AzureFalso(*[erro(status) for _ in range(4)])
    esperas: list[float] = []

    with pytest.raises(TTSError) as falha:
        adaptador(azure, esperas).synthesize(SSML_BILINGUE, VOZ)

    assert falha.value.retryable is True
    assert len(azure.requisicoes) == 4  # a primeira tentativa e mais 3
    assert len(esperas) == 3


def test_a_espera_entre_tentativas_cresce():
    azure = AzureFalso(*[erro(503) for _ in range(4)])
    esperas: list[float] = []
    with pytest.raises(TTSError):
        adaptador(azure, esperas).synthesize(SSML_BILINGUE, VOZ)
    assert esperas == sorted(esperas) and esperas[0] < esperas[-1]


def test_se_uma_nova_tentativa_der_certo_devolve_o_audio():
    azure = AzureFalso(erro(429), erro(503), ok())
    resultado = adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    assert resultado.data == UM_SEGUNDO_DE_MP3
    assert len(azure.requisicoes) == 3


@pytest.mark.parametrize(
    "falha_de_rede",
    [httpx.ConnectTimeout("tempo esgotado"), httpx.ReadTimeout("tempo esgotado"), httpx.ConnectError("sem rede")],
)
def test_tempo_esgotado_e_falha_de_rede_tambem_tentam_de_novo(falha_de_rede):
    azure = AzureFalso(*[falha_de_rede for _ in range(4)])
    with pytest.raises(TTSError) as falha:
        adaptador(azure).synthesize(SSML_BILINGUE, VOZ)
    assert falha.value.retryable is True
    assert len(azure.requisicoes) == 4


def test_o_numero_de_tentativas_e_configuravel():
    azure = AzureFalso(*[erro(503) for _ in range(2)])
    with pytest.raises(TTSError):
        adaptador(azure, max_retries=1).synthesize(SSML_BILINGUE, VOZ)
    assert len(azure.requisicoes) == 2


@pytest.mark.parametrize("status", [400, 401, 403])
def test_erro_do_pedido_ou_da_chave_nao_tenta_de_novo(status):
    azure = AzureFalso(erro(status))
    esperas: list[float] = []

    with pytest.raises(TTSError) as falha:
        adaptador(azure, esperas).synthesize(SSML_BILINGUE, VOZ)

    assert falha.value.retryable is False
    assert len(azure.requisicoes) == 1
    assert esperas == []


def test_a_mensagem_de_erro_diz_o_status_do_azure():
    azure = AzureFalso(erro(401))
    with pytest.raises(TTSError, match="401"):
        adaptador(azure).synthesize(SSML_BILINGUE, VOZ)


# ---------- a chave não vaza ----------

@pytest.mark.parametrize(
    "respostas",
    [
        [erro(401, f"chave {CHAVE} recusada")],  # mesmo se o fornecedor devolver a chave no corpo
        [erro(400, CHAVE)],
        [erro(503, CHAVE) for _ in range(4)],
        [httpx.ConnectError(f"falha ao enviar {CHAVE}") for _ in range(4)],
    ],
    ids=["401", "400", "503", "rede"],
)
def test_a_chave_nao_aparece_no_erro_nem_nos_logs(respostas, caplog):
    caplog.set_level(logging.DEBUG)  # pega os logs de todo mundo, inclusive os do httpx
    azure = AzureFalso(*respostas)

    with pytest.raises(TTSError) as falha:
        adaptador(azure).synthesize(SSML_BILINGUE, VOZ)

    erro_levantado = falha.value
    assert CHAVE not in str(erro_levantado)
    assert CHAVE not in repr(erro_levantado)
    assert erro_levantado.__cause__ is None or CHAVE not in str(erro_levantado.__cause__)
    assert CHAVE not in caplog.text


def test_a_chave_nao_aparece_no_repr_do_adaptador():
    assert CHAVE not in repr(adaptador(AzureFalso()))


# ---------- contrato e fábrica ----------

def test_o_adaptador_cumpre_o_contrato_tts_provider():
    assert isinstance(adaptador(AzureFalso()), TTSProvider)


def settings_azure(**kwargs) -> Settings:
    valores = {"tts_provider": "azure", "tts_api_key": CHAVE, "tts_region": REGIAO, "tts_voice_id": VOZ}
    return Settings(**{**valores, **kwargs})


def test_tts_provider_azure_cria_o_adaptador_sem_mudar_codigo():
    assert isinstance(create_tts_provider(settings_azure()), AzureTTSAdapter)


@pytest.mark.parametrize(
    ("faltando", "settings"),
    [
        ("TTS_API_KEY", settings_azure(tts_api_key="")),
        ("TTS_REGION", settings_azure(tts_region="")),
        ("TTS_VOICE_ID", settings_azure(tts_voice_id="")),
        ("TTS_VOICE_ID", settings_azure(tts_voice_id="fake-voice")),  # a voz padrão, do provedor falso
    ],
    ids=["sem-chave", "sem-regiao", "sem-voz", "voz-do-fake"],
)
def test_azure_mal_configurado_falha_com_mensagem_clara(faltando, settings):
    with pytest.raises(ValueError, match=faltando) as falha:
        create_tts_provider(settings)
    assert CHAVE not in str(falha.value)


def test_trocar_a_voz_e_so_mudar_a_variavel_de_ambiente(monkeypatch):
    """O pipeline passa `settings.tts_voice_id` ao adaptador: a voz vem do ambiente, sem mudar código."""
    monkeypatch.setenv("TTS_VOICE_ID", "en-US-AvaMultilingualNeural")
    settings = Settings()
    azure = AzureFalso(ok())
    adaptador(azure).synthesize(SSML_BILINGUE, settings.tts_voice_id)
    assert ssml_enviado(azure).find(f"{SSML_NS}voice").get("name") == "en-US-AvaMultilingualNeural"


# ---------- teste manual, com o Azure de verdade ----------

def _duracao_real_mp3_ms(dados: bytes) -> int:
    """Duração do MP3 contando os quadros (frames), para comparar com o `duration_ms` calculado."""
    bitrates = {  # kbit/s por índice: MPEG-1 e MPEG-2/2.5, camada III
        1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
        2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    }
    taxas = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
    if dados[:3] == b"ID3":  # pula a etiqueta ID3, se houver
        dados = dados[10 + int.from_bytes(bytes(b & 0x7F for b in dados[6:10]), "big"):]
    posicao, amostras, taxa = 0, 0, 0
    while posicao + 4 <= len(dados):
        b1, b2, b3 = dados[posicao + 1], dados[posicao + 2], dados[posicao + 3]
        if dados[posicao] != 0xFF or (b1 & 0xE0) != 0xE0:
            posicao += 1
            continue
        versao = (b1 >> 3) & 0x03
        bitrate = bitrates[1 if versao == 3 else 2][b2 >> 4] * 1000
        taxa = taxas[versao][(b2 >> 2) & 0x03]
        por_quadro = 1152 if versao == 3 else 576
        tamanho = por_quadro // 8 * bitrate // taxa + ((b2 >> 1) & 0x01)
        amostras += por_quadro
        posicao += max(tamanho, 1)
    return amostras * 1000 // taxa if taxa else 0


_settings_reais = Settings()
_tem_chave = _settings_reais.tts_provider == "azure" and bool(_settings_reais.tts_api_key)


@pytest.mark.tts_real
@pytest.mark.skipif(not _tem_chave, reason="precisa de TTS_PROVIDER=azure e TTS_API_KEY no backend/.env")
def test_manual_sintetiza_uma_frase_com_troca_de_idioma(tmp_path):
    tts = create_tts_provider(_settings_reais)
    resultado = tts.synthesize(SSML_BILINGUE, _settings_reais.tts_voice_id)

    assert resultado.format == "mp3"
    assert len(resultado.data) > 1000
    duracao_real = _duracao_real_mp3_ms(resultado.data)
    assert duracao_real > 0
    assert abs(resultado.duration_ms - duracao_real) <= max(200, duracao_real * 0.05)

    arquivo = tmp_path / "frase_bilingue.mp3"
    arquivo.write_bytes(resultado.data)
    print(f"\nÁudio salvo em {arquivo} ({resultado.duration_ms} ms). Abra para ouvir.")
