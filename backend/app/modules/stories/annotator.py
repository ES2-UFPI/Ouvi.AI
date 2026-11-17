"""TextAnnotator: anota as frases de uma história com os trechos candidatos à troca de idioma."""
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB, Annotation, Segment
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


# Prioridade entre os tipos quando dois trechos se sobrepõem: quem vem antes vence. O phrasal verb vence a
# palavra difícil: em "gave up", "up" nunca vira uma palavra difícil separada.
KIND_PRIORITY: tuple[str, ...] = (KIND_PHRASAL_VERB, KIND_DIFFICULT_WORD)


def _priority(kind: str) -> int:
    return KIND_PRIORITY.index(kind) if kind in KIND_PRIORITY else len(KIND_PRIORITY)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


@dataclass
class KindStats:
    """Contagens de um tipo de trecho."""

    detected: int = 0
    aligned: int = 0
    # Detectados mas descartados porque se sobrepõem a um trecho de um tipo com prioridade maior
    discarded: int = 0

    @property
    def unaligned(self) -> int:
        return self.detected - self.aligned

    def add(self, other: "KindStats") -> None:
        self.detected += other.detected
        self.aligned += other.aligned
        self.discarded += other.discarded


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
    by_kind: dict[str, KindStats] = field(default_factory=dict)

    def stats(self, kind: str) -> KindStats:
        return self.by_kind.setdefault(kind, KindStats())

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

    @property
    def by_kind(self) -> dict[str, KindStats]:
        total: dict[str, KindStats] = {}
        for story in self.stories:
            for kind, stats in story.by_kind.items():
                total.setdefault(kind, KindStats()).add(stats)
        return dict(sorted(total.items()))


class TextAnnotator:
    """Para cada frase da história: roda os detectores no texto em inglês, acha o equivalente de
    cada trecho no texto em português e grava as anotações.

    Pode ser repetido sem duplicar nada: as anotações antigas da frase são apagadas e as novas gravadas
    na mesma transação. Só os tipos dos detectores recebidos são refeitos: anotar só as palavras difíceis
    não apaga nem altera os phrasal verbs (e o contrário também). Os trechos de outros tipos já gravados
    contam como ocupados, e na sobreposição vale a prioridade de `KIND_PRIORITY` (o phrasal verb vence). Cada história é uma transação: ou fica inteira com as anotações novas, ou
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
    def with_defaults(cls, db: Session, kinds: Sequence[str] | None = None) -> "TextAnnotator":
        """Os detectores dos tipos pedidos (padrão: todos os registrados) e o alinhador por dicionário."""
        detectors = [DetectorFactory.create(kind) for kind in (kinds or DetectorFactory.kinds())]
        return cls(db, detectors, DictionaryAligner())

    @property
    def kinds(self) -> list[str]:
        """Tipos que este anotador refaz, do de maior prioridade para o de menor."""
        return sorted({d.kind for d in self.detectors}, key=lambda k: (_priority(k), k))

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
        kinds = self.kinds
        for kind in kinds:
            report.stats(kind)
        try:
            for segment in self.segments.list_by_story(story_id):
                report.segments += 1
                report.replaced += self.annotations.delete_by_segment(segment.id, commit=False, kinds=kinds)
                # O apagamento foi direto no banco: a lista de anotações carregada ficou desatualizada
                self.db.expire(segment, ["annotations"])
                self._annotate_segment(segment, title, report)
            if dry_run:
                self.db.rollback()
            else:
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return report

    def _annotate_segment(self, segment: Segment, title: str, report: StoryReport) -> None:
        # Anotações de OUTROS tipos que continuam na frase (as dos tipos refeitos já foram apagadas)
        kept: list[Annotation] = list(segment.annotations)

        # Tipos de maior prioridade primeiro: o phrasal verb ocupa o lugar antes da palavra difícil
        spans = sorted(
            (span for detector in self.detectors for span in detector.detect(segment.text_en)),
            key=lambda s: (_priority(s.kind), s.start, s.end),
        )
        placed: list[tuple[int, int, int]] = []  # (início, fim, prioridade) dos trechos novos desta frase
        new_taken: list[tuple[int, int]] = []  # trechos do português usados pelas anotações novas
        for span in spans:
            mine, prio = (span.start, span.end), _priority(span.kind)
            stats = report.stats(span.kind)
            blockers = [(a.en_start, a.en_end, _priority(a.kind)) for a in kept] + placed
            if any(_overlaps(mine, (start, end)) and other <= prio for start, end, other in blockers):
                # Já existe aqui um trecho de prioridade igual ou maior: este é descartado
                stats.discarded += 1
                continue
            # Um trecho já gravado de prioridade MENOR (ex.: palavra difícil dentro de um phrasal verb novo)
            # perde o lugar
            for other in [a for a in kept if _overlaps(mine, (a.en_start, a.en_end))]:
                self.db.delete(other)
                kept.remove(other)
                report.stats(other.kind).discarded += 1
            placed.append((span.start, span.end, prio))
            stats.detected += 1
            report.detected += 1

            # Trechos do português já usados nesta frase (pelas anotações mantidas e pelas novas)
            taken = [(a.pt_start, a.pt_end) for a in kept if a.pt_start is not None and a.pt_end is not None]
            taken += new_taken
            equivalent = self.aligner.align(span, segment.text_en, segment.text_pt, taken)
            extra = dict(span.extra)
            pt_start = pt_end = None
            if equivalent is not None:
                pt_start, pt_end = equivalent
                new_taken.append(equivalent)
                extra["aligner"] = self.aligner.name
                report.aligned += 1
                stats.aligned += 1
            else:
                report.unaligned_items.append(UnalignedItem(title, segment.position, span.lemma, span.text))
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
