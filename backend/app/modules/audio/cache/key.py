"""Chave de cache do áudio: a identidade de um arquivo depende SÓ do que vai ao TTS.

Não entram usuário, filtro nem história: a mesma frase com as mesmas trocas tem o mesmo SSML para qualquer
um, então gera a mesma chave e reaproveita o mesmo arquivo (cache global).
"""
import hashlib
import json
import re

# Mude este número quando o significado da chave mudar (outra normalização, por exemplo): todas as chaves
# antigas deixam de bater e o áudio é gerado de novo, sem misturar arquivos de versões diferentes
CACHE_KEY_VERSION = 1

_TAG = re.compile(r"(<[^>]*>)")
_SPACES = re.compile(r"\s+")


def normalize_ssml(ssml: str) -> str:
    """Normaliza os espaços FORA das tags: sequências de espaços e quebras de linha viram um espaço só, e
    os espaços logo depois da abertura do `<speak>`, logo antes do fechamento e nas pontas saem.

    O conteúdo das tags fica como está. Dois SSML que só diferem por espaços fora das tags soam igual (o TTS
    também junta os espaços), então devem dar a mesma chave.
    """
    pieces = _TAG.split(ssml)
    text = "".join(piece if _TAG.fullmatch(piece) else _SPACES.sub(" ", piece) for piece in pieces).strip()
    text = re.sub(r"(<speak\b[^>]*>) ", r"\1", text)
    return re.sub(r" (</speak>)", r"\1", text)


def build_cache_key(ssml: str, voice_id: str, provider: str, audio_format: str) -> str:
    """SHA-256 (hexadecimal, 64 caracteres) do SSML normalizado, da voz, do fornecedor e do formato.

    Função pura: o mesmo conteúdo dá sempre a mesma chave, em qualquer execução. Mudar qualquer um dos
    quatro campos (ou a CACHE_KEY_VERSION) dá outra chave. O idioma está dentro do SSML (`xml:lang`), então
    mudar o idioma também muda a chave.
    """
    payload = json.dumps(
        {
            "v": CACHE_KEY_VERSION,
            "ssml": normalize_ssml(ssml),
            "voice": voice_id,
            "provider": provider,
            "format": audio_format.lower(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
