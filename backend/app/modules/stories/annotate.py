"""Comando de anotação: python -m app.modules.stories.annotate [--story-id N] [--dry-run]"""
import argparse
import sys

from app.core.database import SessionLocal
from app.modules.stories.annotator import AnnotationReport, StoryReport, TextAnnotator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.stories.annotate",
        description=(
            "Anota as histórias com os trechos candidatos à troca de idioma (phrasal verbs) e o equivalente "
            "em português. Pode ser repetido: as anotações antigas são substituídas, sem duplicar nada."
        ),
    )
    parser.add_argument("--story-id", type=int, help="anota só esta história (padrão: todas)")
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra o que seria feito, sem gravar nada no banco"
    )
    return parser


def format_story(story: StoryReport, prefix: str) -> str:
    if story.error:
        return f"{prefix}{story.title}: FALHOU e não foi alterada ({story.error})"
    return (
        f"{prefix}{story.title}: {story.segments} frases, {story.detected} trechos detectados, "
        f"{story.aligned} alinhados, {story.unaligned} sem alinhamento"
    )


def print_report(report: AnnotationReport, dry_run: bool) -> None:
    prefix = "[simulação, nada foi gravado] " if dry_run else ""
    for story in report.stories:
        print(format_story(story, prefix))

    print(f"\n{prefix}Total: {len(report.stories)} histórias, {report.segments} segmentos processados")
    rate = f" ({report.aligned / report.detected:.0%})" if report.detected else ""
    print(
        f"{prefix}Trechos: {report.detected} detectados, {report.aligned} alinhados{rate}, "
        f"{report.unaligned} sem alinhamento"
    )
    print(f"{prefix}Anotações substituídas: {report.replaced}")

    if report.unaligned_items:
        print("\nSem equivalente em português (gravados com os campos pt_* nulos):")
        for item in report.unaligned_items:
            print(f"  - {item.story}, frase {item.position + 1}: {item.lemma!r} ({item.en_text!r})")
        print("  Para alinhar, acrescente as formas em português em nlp/data/pt_equivalents.json e rode de novo.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    with SessionLocal() as db:
        annotator = TextAnnotator.with_defaults(db)
        if args.story_id is not None:
            try:
                report = AnnotationReport([annotator.annotate_story(args.story_id, args.dry_run)])
            except LookupError as exc:
                print(exc, file=sys.stderr)
                return 2
            except Exception as exc:
                print(f"Falha ao anotar a história {args.story_id}; nada foi alterado: {exc}", file=sys.stderr)
                return 1
        else:
            report = annotator.annotate_all(args.dry_run)

    print_report(report, args.dry_run)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
