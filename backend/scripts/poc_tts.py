"""Prova de conceito do TTS real (#81): a mesma frase com troca de idioma, em várias vozes multilíngues.

Para cada voz e cada frase, sintetiza algumas vezes pelo `AzureTTSAdapter`, mede a latência, salva o MP3
para o time ouvir e dar nota de naturalidade, e imprime uma tabela para o `docs/poc-tts.md`.

Precisa de TTS_API_KEY e TTS_REGION no backend/.env (TTS_PROVIDER pode continuar "fake": o script usa o Azure
de qualquer jeito). Cada execução padrão gasta uns 2 mil caracteres, bem abaixo dos 500 mil grátis por mês do F0.

Uso, a partir da pasta backend:
    python -m scripts.poc_tts                      # 3 vozes x 3 frases, 3 vezes cada
    python -m scripts.poc_tts --runs 1             # uma vez só (mais rápido e mais barato)
    python -m scripts.poc_tts --voice pt-BR-ThalitaMultilingualNeural --voice en-US-AvaMultilingualNeural
"""
import argparse
import statistics
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

from app.core.config import get_settings
from app.integrations.tts import AzureTTSAdapter, TTSError

VOICES = [
    "pt-BR-ThalitaMultilingualNeural",
    "en-US-AvaMultilingualNeural",
    "en-US-AndrewMultilingualNeural",
]

# Frases no formato que o compositor gera: idioma base no <speak> e o trecho trocado em <lang>
PHRASES = {
    "curta": (
        '<speak version="1.0" xml:lang="pt-BR">'
        'A raposa tentou de novo, mas no fim <lang xml:lang="en-US">gave up</lang> das uvas.'
        "</speak>"
    ),
    "varias-trocas": (
        '<speak version="1.0" xml:lang="pt-BR">'
        'Quando o despertador tocou, Ana <lang xml:lang="en-US">woke up</lang>, '
        '<lang xml:lang="en-US">turned off</lang> o alarme e foi <lang xml:lang="en-US">pick up</lang> '
        "o irmão na escola."
        "</speak>"
    ),
    "base-ingles": (
        '<speak version="1.0" xml:lang="en-US">'
        'The old fisherman was <lang xml:lang="pt-BR">teimoso</lang> and refused to '
        '<lang xml:lang="pt-BR">desistir</lang> before sunrise.'
        "</speak>"
    ),
}

OUT_DIR = Path(__file__).resolve().parents[1] / "poc-tts-audios"


def text_chars(ssml: str) -> int:
    """Caracteres de texto (sem as tags), que é o que o Azure cobra."""
    return len("".join(ElementTree.fromstring(ssml).itertext()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", action="append", help="voz a testar (pode repetir). Padrão: as 3 multilíngues")
    parser.add_argument("--runs", type=int, default=3, help="sínteses por voz e frase, para a latência (padrão 3)")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help=f"pasta dos MP3 (padrão {OUT_DIR.name}/)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.tts_api_key or not settings.tts_region:
        print("Faltam TTS_API_KEY e/ou TTS_REGION no backend/.env.", file=sys.stderr)
        return 1

    voices = args.voice or VOICES
    args.out.mkdir(parents=True, exist_ok=True)
    tts = AzureTTSAdapter(api_key=settings.tts_api_key, region=settings.tts_region)

    print(f"Região: {settings.tts_region} | {len(voices)} voz(es) x {len(PHRASES)} frases x {args.runs} execução(ões)\n")
    header = f"| {'Voz':<34} | {'Frase':<14} | {'Caract.':>7} | {'Duração':>8} | {'Latência mediana':>16} | {'Mín–máx':>13} |"
    print(header)
    print("".join("|" if ch == "|" else "-" for ch in header))  # linha de separação do Markdown

    all_latencies: dict[str, list[float]] = {}
    total_chars = 0
    failures = 0
    for voice in voices:
        for name, ssml in PHRASES.items():
            latencies: list[float] = []
            result = None
            for _ in range(args.runs):
                start = time.perf_counter()
                try:
                    result = tts.synthesize(ssml, voice)
                except TTSError as exc:
                    print(f"| {voice:<34} | {name:<14} | ERRO: {exc}")
                    failures += 1
                    break
                latencies.append((time.perf_counter() - start) * 1000)
                total_chars += text_chars(ssml)
            if not latencies or result is None:
                continue

            (args.out / f"{voice}__{name}.mp3").write_bytes(result.data)
            all_latencies.setdefault(voice, []).extend(latencies)
            print(
                f"| {voice:<34} | {name:<14} | {text_chars(ssml):>7} | {result.duration_ms / 1000:>7.1f}s"
                f" | {statistics.median(latencies):>13.0f} ms | {min(latencies):>5.0f}–{max(latencies):>4.0f} ms |"
            )

    print("\nLatência mediana por voz (todas as frases):")
    for voice, latencies in all_latencies.items():
        print(f"  {voice}: {statistics.median(latencies):.0f} ms")
    print(f"\nCaracteres cobrados nesta execução: {total_chars}")
    print(f"MP3 salvos em {args.out} (um por voz e frase). Ouçam e deem nota de 1 a 5 no docs/poc-tts.md.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
