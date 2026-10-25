"""TextAnnotator: anota as frases de uma história com os trechos candidatos à troca de idioma."""
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.modules.stories.models import Story
from app.modules.stories.nlp.alignment import AnnotationAligner, DictionaryAligner
from app.modules.stories.nlp.base import AnnotationDetector
from app.modules.stories.nlp.factory import DetectorFactory
from app.modules.stories.repository import (
    AnnotationRepository,
    SegmentRepository,
    StoryRepository,
)


@dataclass(frozen=True)
class UnalignedItem:
    """Trecho detectado em inglês que ainda não tem equivalente em português."""

    story: str
    position: int  # posição da frase na história, começando em 0
    lemma: str
    en_text: str


@dataclass
class StoryReport:
    story_id: int
    title: str
    segments: int = 0
    detected: int = 0
    aligned: int = 0
    # Anotações antigas apagadas para dar lugar às novas
    replaced: int = 0
    unaligned_items: list[UnalignedItem] = field(default_factory=list)
    error: str | None = None

    @property
    def unaligned(self) -> int:
        return self.detected - self.aligned


@dataclass
class AnnotationReport:
    stories: list[StoryReport] = field(default_factory=list)

    @property
    def segments(self) -> int:
        return sum(s.segments for s in self.stories)

    @property
    def detected(self) -> int:
        return sum(s.detected for s in self.stories)

    @property
    def aligned(self) -> int:
        return sum(s.aligned for s in self.stories)

    @property
    def unaligned(self) -> int:
        return self.detected - self.aligned

    @property
    def replaced(self) -> int:
        return sum(s.replaced for s in self.stories)

    @property
    def unaligned_items(self) -> list[UnalignedItem]:
        return [item for s in self.stories for item in s.unaligned_items]

    @property
    def failed(self) -> list[StoryReport]:
        return [s for s in self.stories if s.error]


class TextAnnotator:
    """Para cada frase da história: roda os detectores no texto em inglês, acha o equivalente de
    cada trecho no texto em português e grava as anotações.

    Pode ser repetido sem duplicar nada: as anotações antigas da frase são apagadas e as novas gravadas
    na mesma transação. Cada história é uma transação: ou fica inteira com as anotações novas, ou
    continua exatamente como estava (se algo falhar, o banco volta ao estado anterior).
    """

    def __init__(
        self,
        db: Session,
        detectors: Sequence[AnnotationDetector],
        aligner: AnnotationAligner,
    ) -> None:
        self.db = db
        self.detectors = list(detectors)
        self.aligner = aligner
        self.stories = StoryRepository(db)
        self.segments = SegmentRepository(db)
        self.annotations = AnnotationRepository(db)

    @classmethod
    def with_defaults(cls, db: Session) -> "TextAnnotator":
        """Todos os detectores disponíveis e o alinhador por dicionário."""
        detectors = [DetectorFactory.create(kind) for kind in DetectorFactory.kinds()]
        return cls(db, detectors, DictionaryAligner())

    def annotate_all(self, dry_run: bool = False) -> AnnotationReport:
        """Anota todas as histórias. Se uma falhar, as outras continuam, e a falha entra no relatório."""
        # Guarda id e título antes: depois de um rollback os objetos do banco ficam expirados
        stories = [(s.id, s.title) for s in self.stories.list_all()]
        report = AnnotationReport()
        for story_id, title in stories:
            report.stories.append(self._annotate_safely(story_id, title, dry_run))
        return report

    def annotate_story(self, story_id: int, dry_run: bool = False) -> StoryReport:
        """Anota uma história. Se algo falhar, a história não muda e o erro é levantado."""
        story = self.stories.get_by_id(story_id)
        if story is None:
            raise LookupError(f"História {story_id} não encontrada")
        return self._annotate(story.id, story.title, dry_run)

    def _annotate_safely(self, story_id: int, title: str, dry_run: bool) -> StoryReport:
        try:
            return self._annotate(story_id, title, dry_run)
        except Exception as exc:  # a falha de uma história não pode impedir as outras
            return StoryReport(story_id, title, error=f"{type(exc).__name__}: {exc}")

    def _annotate(self, story_id: int, title: str, dry_run: bool) -> StoryReport:
        report = StoryReport(story_id, title)
        try:
            for segment in self.segments.list_by_story(story_id):
                report.segments += 1
                report.replaced += self.annotations.delete_by_segment(segment.id, commit=False)
                # O apagamento foi direto no banco: a lista de anotações carregada ficou desatualizada
                self.db.expire(segment, ["annotations"])

                spans = sorted(
                    (span for detector in self.detectors for span in detector.detect(segment.text_en)),
                    key=lambda s: (s.start, s.end),
                )
                taken: list[tuple[int, int]] = []  # trechos do português já usados nesta frase
                for span in spans:
                    equivalent = self.aligner.align(span, segment.text_en, segment.text_pt, taken)
                    extra = dict(span.extra)
                    pt_start = pt_end = None
                    if equivalent is not None:
                        pt_start, pt_end = equivalent
                        taken.append(equivalent)
                        extra["aligner"] = self.aligner.name
                    self.annotations.create(
                        segment,
                        kind=span.kind,
                        lemma=span.lemma,
                        en_start=span.start,
                        en_end=span.end,
                        pt_start=pt_start,
                        pt_end=pt_end,
                        extra=extra,
                        commit=False,
                    )
                    report.detected += 1
                    if equivalent is not None:
                        report.aligned += 1
                    else:
                        report.unaligned_items.append(
                            UnalignedItem(title, segment.position, span.lemma, span.text)
                        )
            if dry_run:
                self.db.rollback()
            else:
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return report
