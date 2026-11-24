"""Grava no banco as histórias dos arquivos JSON. Pode ser repetido sem duplicar nada."""
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.stories.models import Segment, Story
from app.modules.stories.repository import (
    AnnotationRepository,
    SegmentRepository,
    StoryRepository,
)
from app.modules.stories.seed.validation import SEED_DIR, SeedSegment, SeedStory, read_seed_files


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


class _SeedSync:
    """Sincroniza uma história do seed por vez com o banco, somando o que fez no relatório.

    Cada passo (achar ou criar a história, sincronizar as frases, tratar as que sobraram) é um método com um
    só trabalho, em vez de tudo dentro de um laço de 60 linhas. Nenhum método grava: quem confirma ou desfaz
    a transação é `load_seed`.
    """

    def __init__(self, db: Session, report: SeedReport) -> None:
        self.db = db
        self.report = report
        self.stories = StoryRepository(db)
        self.segments = SegmentRepository(db)
        self.annotations = AnnotationRepository(db)

    def sync_story(self, item: SeedStory, prune: bool) -> None:
        story = self._find_or_create_story(item)
        existing = {s.position: s for s in self.segments.list_by_story(story.id)}
        for position, seg in enumerate(item.segments):
            self._sync_segment(story, position, seg, existing.get(position))
        self._handle_leftovers(story, item, existing, prune)

    def _find_or_create_story(self, item: SeedStory) -> Story:
        story = self.stories.get_by_title(item.title)
        if story is None:
            self.report.stories_created += 1
            return self.stories.create(item.title, item.description, item.language, commit=False)
        self.report.stories_found += 1
        if story.language != item.language:
            story.language = item.language
        return story

    def _sync_segment(self, story: Story, position: int, seg: SeedSegment, current: Segment | None) -> None:
        """Frase nova é criada, igual é mantida e com texto diferente é atualizada."""
        if current is None:
            self.segments.create(story.id, position, seg.en, seg.pt, commit=False)
            self.report.segments_created += 1
        elif (current.text_en, current.text_pt) != (seg.en, seg.pt):
            self._update_segment_text(current, seg)
        else:
            self.report.segments_unchanged += 1

    def _update_segment_text(self, current: Segment, seg: SeedSegment) -> None:
        # As anotações saem junto: as posições dos trechos ficaram desatualizadas e a frase precisa ser anotada de novo
        self.report.annotations_cleared += self.annotations.delete_by_segment(current.id, commit=False)
        self.db.expire(current, ["annotations"])
        self.segments.update_texts(current, seg.en, seg.pt, commit=False)
        self.report.segments_updated += 1

    def _handle_leftovers(self, story: Story, item: SeedStory, existing: dict[int, Segment], prune: bool) -> None:
        """Frases do banco além do fim do JSON: apagadas com `prune`, senão viram aviso."""
        leftovers = sorted(p for p in existing if p >= len(item.segments))
        if not leftovers:
            return
        if prune:
            self.report.segments_pruned += self.segments.delete_from_position(
                story.id, len(item.segments), commit=False
            )
        else:
            self.report.warnings.append(
                f"{item.title}: {len(leftovers)} frase(s) no banco além do fim do JSON "
                f"(use --prune para removê-las)"
            )


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
    report = SeedReport()
    sync = _SeedSync(db, report)

    try:
        for item in seed_stories:
            sync.sync_story(item, prune)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return report
