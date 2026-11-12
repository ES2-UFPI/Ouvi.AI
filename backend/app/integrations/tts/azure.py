"""Adaptador do Azure Speech (TTS real), pela API REST e com `httpx`, sem o SDK da Microsoft.

A troca de idioma vem do SSML: o compositor marca os trechos em outro idioma com `<lang xml:lang="...">`,
e uma voz *multilíngue* (as que têm "Multilingual" no nome) fala os dois idiomas com o mesmo timbre.
Este adaptador só põe a voz pedida no SSML, envia e devolve o MP3.

A chave nunca sai daqui: ela vai só no cabeçalho da requisição e não aparece em mensagens de erro,
em logs nem no `repr` do adaptador.
"""
import logging
import re
import time
from collections.abc import Callable
from xml.etree import ElementTree

import httpx

from app.integrations.tts.base import SynthesisResult, TTSError

logger = logging.getLogger(__name__)

# MP3 com taxa fixa (CBR): a duração sai direto do tamanho do arquivo. 24 kHz é o suficiente para voz
DEFAULT_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 0.5  # espera 0,5 s, 1 s, 2 s... entre as tentativas
MAX_WAIT_SECONDS = 10.0  # teto da espera, mesmo se o Azure pedir mais no Retry-After

SSML_NS = "http://www.w3.org/2001/10/synthesis"
USER_AGENT = "Ouvi.AI"

# Vale a pena tentar de novo: limite de uso (429) e falhas do lado do Azure (5xx)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _bitrate_bps(output_format: str) -> int:
    """Bits por segundo do formato, lidos do nome ("audio-24khz-48kbitrate-mono-mp3" -> 48.000)."""
    match = re.search(r"(\d+)kbitrate", output_format)
    if not match or "mp3" not in output_format:
        raise ValueError(f"Formato de saída sem taxa fixa em MP3: {output_format!r}")
    return int(match.group(1)) * 1000


def _prepare_ssml(ssml: str, voice_id: str) -> bytes:
    """Deixa o SSML como o Azure exige: namespace no `<speak>` e o conteúdo dentro de `<voice>`."""
    try:
        root = ElementTree.fromstring(ssml)
    except ElementTree.ParseError as exc:
        raise TTSError(f"SSML inválido: {exc}", retryable=False) from None

    # Trabalha com as tags sem namespace (<speak>, <lang>...) e declara o namespace do SSML no fim, com um
    # xmlns no <speak>. Assim a saída fica sem prefixos (ns0:speak), e tanto faz se o SSML recebido já
    # trazia o xmlns ou não
    ssml_prefix = f"{{{SSML_NS}}}"
    for element in root.iter():
        if element.tag.startswith(ssml_prefix):
            element.tag = element.tag[len(ssml_prefix):]

    if root.tag != "speak":
        raise TTSError("O SSML precisa começar com <speak>", retryable=False)
    root.set("xmlns", SSML_NS)
    root.set("version", root.get("version", "1.0"))

    if root.find(".//voice") is None:
        voice = ElementTree.Element("voice", name=voice_id)
        voice.text, root.text = root.text, None
        children = list(root)
        for child in children:
            root.remove(child)
        voice.extend(children)  # o texto depois de cada filho (tail) vai junto com ele
        root.append(voice)

    return ElementTree.tostring(root, encoding="utf-8")


class AzureTTSAdapter:
    # Entram na chave do cache de áudio (US08): o Azure devolve MP3, não o WAV do provedor falso
    provider_name = "azure"
    audio_format = "mp3"

    def __init__(
        self,
        api_key: str,
        region: str,
        *,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._region = region
        self._output_format = output_format
        self._bitrate_bps = _bitrate_bps(output_format)
        self._max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep
        self._url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def __repr__(self) -> str:  # sem a chave
        return f"AzureTTSAdapter(region={self._region!r}, output_format={self._output_format!r})"

    def synthesize(self, ssml: str, voice_id: str) -> SynthesisResult:
        body = _prepare_ssml(ssml, voice_id)
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": "application/ssml+xml; charset=utf-8",
            "X-Microsoft-OutputFormat": self._output_format,
            "User-Agent": USER_AGENT,
        }

        attempt = 0
        while True:
            outcome, retry_after = self._attempt(body, headers)
            if isinstance(outcome, SynthesisResult):
                return outcome
            error = outcome
            if not error.retryable or attempt >= self._max_retries:
                raise error
            wait = min(max(BACKOFF_BASE_SECONDS * 2**attempt, retry_after), MAX_WAIT_SECONDS)
            attempt += 1
            logger.warning("Azure TTS: %s. Nova tentativa %d de %d em %.1f s", error, attempt, self._max_retries, wait)
            self._sleep(wait)

    def _attempt(self, body: bytes, headers: dict[str, str]) -> tuple[SynthesisResult | TTSError, float]:
        """Uma chamada ao Azure. Devolve o áudio ou o erro (sem levantar), e a espera pedida pelo Azure.

        As mensagens dos erros só têm o status ou o tipo da falha: nunca o corpo da resposta nem o texto
        da exceção do httpx, que poderiam trazer a chave.
        """
        try:
            response = self._client.post(self._url, content=body, headers=headers)
        except httpx.TimeoutException as exc:
            return TTSError(f"Azure TTS: tempo esgotado ({type(exc).__name__})", retryable=True), 0.0
        except httpx.TransportError as exc:
            return TTSError(f"Azure TTS: falha de rede ({type(exc).__name__})", retryable=True), 0.0

        status = response.status_code
        if status == 200:
            if not response.content:
                return TTSError("Azure TTS respondeu 200 sem áudio", retryable=True), 0.0
            return SynthesisResult(
                data=response.content,
                format="mp3",
                duration_ms=len(response.content) * 8 * 1000 // self._bitrate_bps,
            ), 0.0

        retryable = status in _RETRYABLE_STATUS
        hint = {400: " (SSML recusado)", 401: " (chave inválida)", 403: " (acesso negado)"}.get(status, "")
        error = TTSError(f"Azure TTS respondeu {status}{hint}", retryable=retryable)
        return error, _retry_after_seconds(response)


def _retry_after_seconds(response: httpx.Response) -> float:
    """Espera pedida pelo Azure no cabeçalho Retry-After (em segundos), ou 0 se não houver."""
    try:
        return max(0.0, float(response.headers.get("Retry-After", "0")))
    except ValueError:
        return 0.0
