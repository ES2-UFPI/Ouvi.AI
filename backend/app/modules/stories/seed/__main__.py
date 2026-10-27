"""Comando do seed: python -m app.modules.stories.seed [--check] [--dry-run] [--prune]"""
import argparse
import sys

from app.core.database import SessionLocal
from app.modules.stories.seed.loader import load_seed
from app.modules.stories.seed.validation import SeedError, check_quality, read_seed_files


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.stories.seed",
        description="Carrega no banco as histórias bilíngues dos arquivos JSON. Pode ser repetido sem duplicar nada.",
    )
    parser.add_argument(
        "--check", action="store_true", help="só valida os arquivos e as metas de conteúdo, sem acessar o banco"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra o que seria feito, sem gravar nada"
    )
    parser.add_argument(
        "--prune", action="store_true", help="apaga do banco as frases além do fim de cada JSON"
    )
    args = parser.parse_args()

    try:
        stories = read_seed_files()
    except SeedError as exc:
        print(f"Arquivos do seed inválidos:\n{exc}", file=sys.stderr)
        return 1

    if args.check:
        problems = check_quality(stories)
        for s in stories:
            verbs = [pv for seg in s.segments for pv in seg.phrasal_verbs]
            print(
                f"{s.title}: {len(s.segments)} frases, {len({pv.lemma for pv in verbs})} phrasal verbs, "
                f"{sum(pv.separable for pv in verbs)} separáveis"
            )
        if problems:
            print("\nMetas de conteúdo não atendidas:", file=sys.stderr)
            print("\n".join(f"- {p}" for p in problems), file=sys.stderr)
            return 1
        print("\nArquivos válidos e metas de conteúdo atendidas.")
        return 0

    with SessionLocal() as db:
        report = load_seed(db, prune=args.prune, dry_run=args.dry_run)

    prefixo = "[simulação, nada foi gravado] " if args.dry_run else ""
    print(f"{prefixo}Histórias: {report.stories_created} criadas, {report.stories_found} já existiam")
    print(
        f"{prefixo}Frases: {report.segments_created} criadas, {report.segments_updated} atualizadas, "
        f"{report.segments_unchanged} sem mudança, {report.segments_pruned} removidas"
    )
    if report.annotations_cleared:
        print(f"{prefixo}Anotações apagadas por mudança de texto (reanotar): {report.annotations_cleared}")
    for warning in report.warnings:
        print(f"Aviso: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
