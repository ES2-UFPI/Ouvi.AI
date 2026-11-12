"""Provedor de TTS falso: gera tons em vez de voz, sem rede, sem chave e sem custo.

Serve para construir e testar o pipeline de áudio inteiro, e também para demonstrar a troca de idioma
sem TTS real: o texto no idioma base soa como um tom grave, e o trecho em outro idioma (`<lang>`), como
um tom agudo. Cada caractere de texto dura 60 ms, então a duração é previsível e as tags SSML não contam.
"""
import io
import math
import wave
from array import array
from dataclasses import dataclass
from xml.etree import ElementTree

from app.integrations.tts.base import SynthesisResult, TTSError

SAMPLE_RATE = 8000  # baixo de propósito: arquivos pequenos
MS_PER_CHAR = 60
SAMPLES_PER_CHAR = SAMPLE_RATE * MS_PER_CHAR // 1000
BASE_TONE_HZ = 330  # idioma base do <speak>
SWAPPED_TONE_HZ = 660  # trecho em outro idioma
AMPLITUDE = 12000
FADE_SAMPLES = 40  # 5 ms de entrada e saída em cada trecho, para não estalar entre um tom e outro

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass(frozen=True)
class FakeCall:
    """Uma chamada recebida pelo provedor falso, para os testes conferirem o que foi enviado."""

    ssml: str
    voice_id: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # tira o namespace, se o SSML trouxer um


def _pieces(root: ElementTree.Element) -> list[tuple[str, str]]:
    """Pedaços de texto do SSML, cada um com o idioma em que é falado (o do `<lang>` mais próximo)."""
    pieces: list[tuple[str, str]] = []

    def walk(element: ElementTree.Element, parent_lang: str) -> None:
        lang = element.get(XML_LANG, parent_lang) if _local_name(element.tag) == "lang" else parent_lang
        if element.text:
            pieces.append((element.text, lang))
        for child in element:
            walk(child, lang)
            if child.tail:  # o texto depois de um filho é do idioma do pai
                pieces.append((child.tail, lang))

    walk(root, root.get(XML_LANG, ""))
    return pieces


def _normalize(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Junta espaços e quebras de linha repetidos num só (mesmo entre pedaços) e tira os das pontas."""
    out: list[list[str]] = []
    after_space = True  # o início conta como "depois de um espaço": não deixa espaço sobrando
    for text, lang in pieces:
        chars: list[str] = []
        for ch in text:
            if ch.isspace():
                if not after_space:
                    chars.append(" ")
                after_space = True
            else:
                chars.append(ch)
                after_space = False
        if chars:
            out.append(["".join(chars), lang])
    while out and out[-1][0].endswith(" "):
        out[-1][0] = out[-1][0][:-1]
        if not out[-1][0]:
            out.pop()
    return [(text, lang) for text, lang in out]


def _tone(frames: int, frequency: int) -> array:
    samples = array("h")
    for n in range(frames):
        fade = min(1.0, n / FADE_SAMPLES, (frames - n) / FADE_SAMPLES)
        samples.append(int(AMPLITUDE * fade * math.sin(2 * math.pi * frequency * n / SAMPLE_RATE)))
    return samples


class FakeTTSProvider:
    # Entram na chave do cache de áudio (US08): o mesmo SSML em outro fornecedor ou formato é outro áudio
    provider_name = "fake"
    audio_format = "wav"

    def __init__(self) -> None:
        self.calls: list[FakeCall] = []

    def synthesize(self, ssml: str, voice_id: str) -> SynthesisResult:
        self.calls.append(FakeCall(ssml, voice_id))

        try:
            root = ElementTree.fromstring(ssml)
        except ElementTree.ParseError as exc:
            # Como um fornecedor real, que responde 400: repetir o mesmo SSML não adianta
            raise TTSError(f"SSML inválido: {exc}", retryable=False) from exc

        base_lang = root.get(XML_LANG, "").lower()
        pieces = _normalize(_pieces(root))
        if not pieces:
            raise TTSError("O SSML não tem texto para sintetizar", retryable=False)

        samples = array("h")
        for text, lang in pieces:
            frequency = BASE_TONE_HZ if lang.lower() == base_lang else SWAPPED_TONE_HZ
            samples.extend(_tone(len(text) * SAMPLES_PER_CHAR, frequency))

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16 bits
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(samples.tobytes())

        return SynthesisResult(
            data=buffer.getvalue(),
            format="wav",
            duration_ms=len(samples) * 1000 // SAMPLE_RATE,
        )
