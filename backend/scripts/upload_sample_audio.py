"""Envia um áudio de exemplo ao bucket, para testar o player antes de existir TTS.

Uso, a partir da pasta backend:
    python -m scripts.upload_sample_audio                 # gera um tom de 30 s e envia
    python -m scripts.upload_sample_audio caminho/do.mp3  # envia o arquivo informado
    python -m scripts.upload_sample_audio --story 1 --story 2   # grava como o áudio das histórias 1 e 2

No Docker: docker compose exec api python -m scripts.upload_sample_audio
"""
import argparse
import io
import math
import mimetypes
import struct
import wave
from pathlib import Path

from app.core.config import get_settings
from app.integrations.storage import create_storage

SAMPLE_RATE = 8000  # baixo de propósito: 30 s de áudio ficam com ~480 KB


def generate_tone(seconds: int = 30) -> bytes:
    """WAV mono que alterna 440 Hz e 660 Hz a cada segundo, para ouvir quando o player pula."""
    frames = bytearray()
    for i in range(seconds * SAMPLE_RATE):
        freq = 440 if (i // SAMPLE_RATE) % 2 == 0 else 660
        sample = int(12000 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        frames += struct.pack("<h", sample)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16 bits
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arquivo", nargs="?", type=Path, help="áudio a enviar (padrão: gera um tom)")
    parser.add_argument(
        "--story", type=int, action="append", metavar="ID",
        help="grava o áudio como o da história ID (stories/ID/audio.wav), a chave que o player usa; pode repetir",
    )
    args = parser.parse_args()

    if args.arquivo:
        data = args.arquivo.read_bytes()
        key = f"samples/{args.arquivo.name}"
        content_type = mimetypes.guess_type(args.arquivo.name)[0] or "application/octet-stream"
    else:
        data = generate_tone()
        key = "samples/tom-440-660hz.wav"
        content_type = "audio/wav"

    if args.story and args.arquivo and args.arquivo.suffix.lower() != ".wav":
        parser.error("com --story o arquivo precisa ser .wav (a chave usada pelo player termina em .wav)")

    # Enquanto não há TTS, o player procura o áudio da história na chave stories/<id>/audio.wav
    keys = [f"stories/{story_id}/audio.wav" for story_id in args.story] if args.story else [key]

    storage = create_storage(get_settings())
    storage.ensure_bucket()
    for k in keys:
        storage.put(k, data, content_type=content_type)
        print(f"Chave gravada: {k} ({len(data)} bytes)")
    print(f"URL assinada (1 h): {storage.presigned_url(keys[0])}")


if __name__ == "__main__":
    main()
