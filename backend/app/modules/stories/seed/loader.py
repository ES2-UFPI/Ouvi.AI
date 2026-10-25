"""Grava no banco as histórias dos arquivos JSON. Pode ser repetido sem duplicar nada."""
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.stories.repository import (
    AnnotationRepository,
    SegmentRepository,
    StoryRepository,
)
from app.modules.stories.seed.validation import SEED_DIR, read_seed_files


@dataclass
class SeedReport:
    stories_created: int = 0
    stories_found: int = 0
    segments_created: int = 0
    segments_updated: int = 0
    segments_unchanged: int = 0
    segments_pruned: int = 0
    # Anotações apagadas porque o texto da frase mudou e as posições antigas deixaram de valer
    annotations_cleared: int = 0
    warnings: list[str] = field(default_factory=list)


def load_seed(
    db: Session,
    directory: Path = SEED_DIR,
    prune: bool = False,
    dry_run: bool = False,
) -> SeedReport:
    """Sincroniza as histórias do seed com o banco.

    - Histórias são encontradas pelo título. Se não existirem, são criadas.
    - Cada frase é identificada pela posição na história: nova é criada, igual é mantida,
      e com texto diferente é atualizada (as anotações dela são apagadas, pois as posições
      dos trechos ficaram desatualizadas e a frase precisa ser anotada de novo).
    - Frases do banco além do fim do JSON só são apagadas com `prune=True`; sem isso viram aviso.
    - Tudo acontece numa única transação: se algo falhar, nada é gravado.
    - Com `dry_run=True` o resultado é calculado, mas nada é gravado.
    """
    seed_stories = read_seed_files(directory)  # levanta SeedError antes de tocar no banco
    stories = StoryRepository(db)
    segments = SegmentRepository(db)
    annotations = AnnotationRepository(db)
    report = SeedReport()

    try:
        for item in seed_stories:
            story = stories.get_by_title(item.title)
            if story is None:
                story = stories.create(item.title, item.description, item.language, commit=False)
                report.stories_created += 1
            else:
                report.stories_found += 1
                if story.language != item.language:
                    story.language = item.language

            existing = {s.position: s for s in segments.list_by_story(story.id)}

            for position, seg in enumerate(item.segments):
                current = existing.get(position)
                if current is None:
                    segments.create(story.id, position, seg.en, seg.pt, commit=False)
                    report.segments_created += 1
                elif (current.text_en, current.text_pt) != (seg.en, seg.pt):
                    report.annotations_cleared += annotations.delete_by_segment(
                        current.id, commit=False
                    )
                    db.expire(current, ["annotations"])
                    segments.update_texts(current, seg.en, seg.pt, commit=False)
                    report.segments_updated += 1
                else:
                    report.segments_unchanged += 1

            extras = sorted(p for p in existing if p >= len(item.segments))
            if extras and prune:
                report.segments_pruned += segments.delete_from_position(
                    story.id, len(item.segments), commit=False
                )
            elif extras:
                report.warnings.append(
                    f"{item.title}: {len(extras)} frase(s) no banco além do fim do JSON "
                    f"(use --prune para removê-las)"
                )

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return report
