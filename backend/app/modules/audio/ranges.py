"""Interpretação do header HTTP `Range` (RFC 9110, seção 14).

O navegador pede só um trecho do áudio quando o usuário pula para o meio:
    Range: bytes=0-99     os bytes 0 a 99 (100 bytes; o fim é inclusivo)
    Range: bytes=500-     do byte 500 até o fim
    Range: bytes=-200     os últimos 200 bytes
"""
import re
from dataclasses import dataclass

# Uma faixa só: navegadores não pedem várias de uma vez (bytes=0-1,5-6), então não há suporte a isso
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiable(ValueError):
    """Faixa mal escrita ou fora do arquivo. O router responde 416."""

    def __init__(self, message: str, size: int) -> None:
        super().__init__(message)
        self.size = size  # vai no header `Content-Range: bytes */size` do 416


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int  # inclusivo, como no HTTP

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    def content_range(self, size: int) -> str:
        """Valor do header `Content-Range` da resposta 206, ex.: "bytes 0-99/1024"."""
        return f"bytes {self.start}-{self.end}/{size}"


def parse_range(header: str | None, size: int) -> ByteRange | None:
    """Converte o header numa faixa absoluta dentro de um arquivo de `size` bytes.

    Sem header devolve `None`: a resposta é o arquivo inteiro, com status 200.
    Levanta `RangeNotSatisfiable` se a faixa for inválida ou não couber no arquivo.
    """
    if header is None:
        return None

    match = _RANGE_RE.match(header.strip())
    if not match:
        raise RangeNotSatisfiable(f"Range não suportado: {header!r}", size)
    first, last = match.groups()

    if not first and not last:  # "bytes=-"
        raise RangeNotSatisfiable(f"Range vazio: {header!r}", size)

    if not first:  # "bytes=-200": os últimos N bytes
        suffix = int(last)
        if suffix == 0 or size == 0:
            raise RangeNotSatisfiable(f"Range fora do arquivo: {header!r}", size)
        # Pedir mais bytes do que o arquivo tem devolve o arquivo inteiro
        return ByteRange(max(size - suffix, 0), size - 1)

    start = int(first)
    # Sem fim, ou com fim além do arquivo: vai até o último byte
    end = size - 1 if not last else min(int(last), size - 1)
    if start >= size or (last and int(last) < start):
        raise RangeNotSatisfiable(f"Range fora do arquivo: {header!r}", size)
    return ByteRange(start, end)
