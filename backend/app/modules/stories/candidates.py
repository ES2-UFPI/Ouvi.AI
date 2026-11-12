"""Relatório de candidatos a palavra difícil, por história, a partir dos arquivos do seed (sem banco).

    python -m app.modules.stories.candidates [--level intermediate|advanced]

Serve para o time revisar quais palavras valem entrar no dicionário `nlp/data/pt_words.json`.
As palavras saem em ordem de aparição, com a frase, a frequência (Zipf), o nível e se já têm equivalente.
"""
import argparse
import sys
from dataclasses import dataclass

from app.modules.stories.nlp.alignment import DictionaryAligner
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.nlp.difficult_words import DifficultWordDetector, levels_for_filter
from app.modules.stories.seed.validation import SeedStory, read_seed_files


@dataclass(frozen=True)
class Candidate:
    position: int  # frase na história, começando em 0
    span: DetectedSpan
    aligned_pt: str | None  # o trecho em português, quando o dicionário já o encontra


def candidates_for(
    story: SeedStory, detector: DifficultWordDetector, aligner: DictionaryAligner, level: str = "intermediate"
) -> list[Candidate]:
    """Candidatos da história em ordem de aparição (frase, depois posição na frase)."""
    levels = levels_for_filter(level)
    result: list[Candidate] = []
    for position, segment in enumerate(story.segments):
        taken: list[tuple[int, int]] = []
        for span in detector.detect(segment.en):
            if span.extra["level"] not in levels:
                continue
            found = aligner.align(span, segment.en, segment.pt, taken)
            if found:
                taken.append(found)
            result.append(Candidate(position, span, segment.pt[found[0] : found[1]] if found else None))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.modules.stories.candidates", description=__doc__)
    parser.add_argument("--level", choices=["intermediate", "advanced"], default="intermediate")
    args = parser.parse_args(argv)

    detector = DifficultWordDetector()
    aligner = DictionaryAligner()
    for story in read_seed_files():
        found = candidates_for(story, detector, aligner, args.level)
        aligned = sum(1 for c in found if c.aligned_pt)
        print(f"\n== {story.title}: {len(found)} candidatas, {aligned} com equivalente em português")
        for c in found:
            pt = c.aligned_pt if c.aligned_pt else "(sem equivalente)"
            print(
                f"  frase {c.position + 1:>2}: {c.span.text:<14} lema={c.span.lemma:<12} "
                f"zipf={c.span.extra['zipf']:<5} {c.span.extra['level']:<12} -> {pt}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
