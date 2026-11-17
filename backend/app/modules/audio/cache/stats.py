"""Estatísticas do cache de áudio: quanto o cache economiza. Só lê o banco, nunca altera."""
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.modules.audio.cache.repository import AudioBlobRepository


@dataclass(frozen=True)
class CacheStats:
    files: int  # blobs no cache
    size_bytes: int  # soma do tamanho dos arquivos
    hits: int  # reaproveitamentos (o TTS não foi chamado)
    misses: int  # sínteses (a primeira de cada blob e as regenerações de arquivo sumido)
    hit_rate: float  # acertos / (acertos + erros), de 0 a 1
    chars_saved: int  # caracteres que deixaram de ir ao TTS
    cost_per_1k_chars: float  # TTS_COST_PER_1K_CHARS usado na estimativa
    cost_saved: float  # custo estimado evitado: chars_saved / 1000 * cost_per_1k_chars

    def as_dict(self) -> dict:
        return asdict(self)


def compute_stats(db: Session, *, cost_per_1k_chars: float = 0.0) -> CacheStats:
    """Calcula as estatísticas a partir dos contadores dos blobs. Com o cache vazio, tudo é zero.

    Os blobs apagados pela limpeza levam junto os seus contadores: os números são do cache atual.
    """
    totals = AudioBlobRepository(db).totals()
    requests = totals["hits"] + totals["misses"]
    return CacheStats(
        files=totals["files"],
        size_bytes=totals["size_bytes"],
        hits=totals["hits"],
        misses=totals["misses"],
        hit_rate=round(totals["hits"] / requests, 4) if requests else 0.0,
        chars_saved=totals["chars_saved"],
        cost_per_1k_chars=cost_per_1k_chars,
        cost_saved=round(totals["chars_saved"] / 1000 * cost_per_1k_chars, 4),
    )


def format_size(size_bytes: int) -> str:
    """Tamanho legível: 512 B, 1.5 KB, 3.2 MB..."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("inalcançável")  # pragma: no cover


def format_stats(stats: CacheStats) -> str:
    """Relatório em texto, para o terminal."""
    return "\n".join(
        [
            "Cache de áudio",
            f"  Arquivos:                 {stats.files}",
            f"  Tamanho:                  {format_size(stats.size_bytes)}",
            f"  Acertos:                  {stats.hits}",
            f"  Erros:                    {stats.misses}",
            f"  Taxa de acerto:           {stats.hit_rate:.1%}",
            f"  Caracteres economizados:  {stats.chars_saved}",
            f"  Custo evitado (estimado): {stats.cost_saved:.4f}"
            f" (TTS_COST_PER_1K_CHARS = {stats.cost_per_1k_chars})",
        ]
    )
