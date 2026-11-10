"""Mostra como o AudioComposer comporia uma história: o texto, as trocas e (opcionalmente) o SSML de cada frase.

Precisa das histórias no banco e anotadas (seed e annotate, veja o README).

Uso, a partir da pasta backend:
    python -m scripts.compose_demo                              # primeira história, densidade média, base pt
    python -m scripts.compose_demo --story 2 --density high     # outra história e densidade
    python -m scripts.compose_demo --ssml                       # mostra também o SSML que vai ao TTS

No Docker: docker compose exec api python -m scripts.compose_demo
"""
import argparse
import sys

from app.core.database import SessionLocal
from app.modules.audio.composer import DENSITY_SHARE, AudioComposer
from app.modules.stories.repository import SegmentRepository, StoryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--story", type=int, help="id da história (padrão: a primeira)")
    parser.add_argument("--density", choices=list(DENSITY_SHARE), default="medium")
    parser.add_argument("--base", choices=["pt", "en"], default="pt", help="idioma base (o que aparece na tela)")
    parser.add_argument("--ssml", action="store_true", help="mostra também o SSML de cada frase")
    args = parser.parse_args()

    with SessionLocal() as db:
        stories = StoryRepository(db)
        story = stories.get_by_id(args.story) if args.story else next(iter(stories.list_all()), None)
        if story is None:
            print("História não encontrada. Rode o seed e a anotação (veja o README).", file=sys.stderr)
            return 1
        segments = SegmentRepository(db).list_by_story(story.id)

        composer = AudioComposer()
        selected = composer.select_swaps(segments, ["phrasal_verbs"], args.density)
        candidates = sum(1 for s in segments for a in s.annotations if a.pt_start is not None)

        print(f"{story.title}: densidade {args.density} ({DENSITY_SHARE[args.density]:.0%}), base {args.base}\n")
        for segment in segments:
            composed = composer.compose(segment, selected, args.base)
            marked, cursor = [], 0
            for swap in composed.swaps:  # [trecho original -> o que é falado]
                marked += [composed.text[cursor : swap.start], f"[{swap.text} -> {swap.spoken}]"]
                cursor = swap.end
            marked.append(composed.text[cursor:])
            print(f"{segment.position + 1:>2}. {''.join(marked)}")
            if args.ssml:
                print(f"    {composed.ssml}")

        print(f"\n{len(selected)} de {candidates} trechos candidatos trocados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
