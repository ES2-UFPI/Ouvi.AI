"""Comandos do cache de áudio. Rode dentro de backend/:

    python -m app.modules.audio.cache stats [--json]
    python -m app.modules.audio.cache purge [--older-than DIAS] [--max-size 500MB] [--dry-run] [--json]
"""
import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from sqlalchemy.orm import Session

from app.integrations.storage import ObjectStorage
from app.modules.audio.cache.purge import format_report, parse_size, purge
from app.modules.audio.cache.stats import compute_stats, format_stats


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.modules.audio.cache", description="Cache de áudio (US08)")
    sub = parser.add_subparsers(dest="command", required=True)

    stats = sub.add_parser("stats", help="mostra acertos, erros, taxa de acerto e caracteres economizados")
    stats.add_argument("--json", action="store_true", help="saída em JSON")

    clean = sub.add_parser("purge", help="apaga o cache antigo (sem opções, não apaga nada)")
    clean.add_argument("--older-than", type=int, metavar="DIAS", help="remove o que não é usado há mais de DIAS dias")
    clean.add_argument(
        "--max-size", type=parse_size, metavar="TAMANHO",
        help="remove os menos usados recentemente até o cache caber no limite (ex.: 500MB)",
    )
    clean.add_argument("--dry-run", action="store_true", help="só mostra o que seria removido")
    clean.add_argument("--json", action="store_true", help="saída em JSON")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    storage: ObjectStorage | None = None,
    cost_per_1k_chars: float | None = None,
    out: TextIO | None = None,
) -> int:
    """Ponto de entrada. Os parâmetros com padrão servem para os testes trocarem o banco e o armazenamento."""
    args = _parser().parse_args(argv)
    out = out or sys.stdout
    if session_factory is None:  # pragma: no cover - nos testes a sessão é injetada
        from app.core.database import SessionLocal

        session_factory = SessionLocal

    db = session_factory()
    try:
        if args.command == "stats":
            if cost_per_1k_chars is None:
                from app.core.config import get_settings

                cost_per_1k_chars = get_settings().tts_cost_per_1k_chars
            result = compute_stats(db, cost_per_1k_chars=cost_per_1k_chars)
            print(json.dumps(result.as_dict()) if args.json else format_stats(result), file=out)
            return 0

        if args.older_than is None and args.max_size is None:
            print("Nada a fazer: use --older-than e/ou --max-size (e --dry-run para simular).", file=out)
            return 0
        if storage is None:  # pragma: no cover - nos testes o armazenamento é injetado
            from app.integrations.storage import get_storage

            storage = get_storage()
        try:
            report = purge(
                db, storage, older_than_days=args.older_than, max_size_bytes=args.max_size, dry_run=args.dry_run
            )
        except ValueError as exc:
            print(f"Erro: {exc}", file=out)
            return 2
        print(json.dumps(report.as_dict()) if args.json else format_report(report), file=out)
        return 0
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
