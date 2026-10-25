"""Camada Repository: único ponto de acesso aos dados deste módulo."""
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.modules.stories.models import Annotation, Segment, Story


class InvalidAnnotationError(ValueError):
    """O trecho da anotação não cabe no texto da frase ou tem posições incoerentes."""


class StoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Story]:
        # Ordem fixa por id: a lista não muda de posição entre uma chamada e outra
        return list(self.db.scalars(select(Story).order_by(Story.id)))

    def get_by_id(self, story_id: int) -> Story | None:
        return self.db.get(Story, story_id)

    def get_by_title(self, title: str) -> Story | None:
        return self.db.scalar(select(Story).where(Story.title == title))

    def create(
        self, title: str, description: str | None, language: str, commit: bool = True
    ) -> Story:
        story = Story(title=title, description=description, language=language)
        self.db.add(story)
        self.db.commit() if commit else self.db.flush()
        if commit:
            self.db.refresh(story)
        return story


class SegmentRepository:
    """Os métodos de escrita aceitam `commit=False` para o Service juntar várias
    operações numa única transação e confirmar (ou desfazer) tudo de uma vez."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, segment_id: int) -> Segment | None:
        return self.db.get(Segment, segment_id)

    def get_by_position(self, story_id: int, position: int) -> Segment | None:
        stmt = select(Segment).where(
            Segment.story_id == story_id, Segment.position == position
        )
        return self.db.scalar(stmt)

    def list_by_story(self, story_id: int, kind: str | None = None) -> list[Segment]:
        """Frases da história em ordem, já com as anotações carregadas.

        selectinload busca as anotações de todas as frases numa única consulta extra,
        então o número de consultas não cresce com o número de frases. O filtro por
        `kind` é aplicado nessa mesma consulta.
        """
        annotations = selectinload(Segment.annotations)
        if kind is not None:
            annotations = selectinload(Segment.annotations.and_(Annotation.kind == kind))
        stmt = (
            select(Segment)
            .where(Segment.story_id == story_id)
            .order_by(Segment.position)
            .options(annotations)
        )
        return list(self.db.scalars(stmt))

    def create(
        self, story_id: int, position: int, text_en: str, text_pt: str, commit: bool = True
    ) -> Segment:
        segment = Segment(
            story_id=story_id, position=position, text_en=text_en, text_pt=text_pt
        )
        self.db.add(segment)
        try:
            self.db.commit() if commit else self.db.flush()
        except IntegrityError:
            # Posição repetida na história (ou história inexistente). Sem o rollback a sessão fica inutilizável
            if commit:
                self.db.rollback()
            raise
        if commit:
            self.db.refresh(segment)
        return segment


    def update_texts(
        self, segment: Segment, text_en: str, text_pt: str, commit: bool = True
    ) -> Segment:
        segment.text_en = text_en
        segment.text_pt = text_pt
        self.db.commit() if commit else self.db.flush()
        return segment

    def delete_from_position(
        self, story_id: int, start_position: int, commit: bool = True
    ) -> int:
        """Apaga as frases da posição indicada em diante (as anotações saem junto, por cascata no banco)."""
        result = self.db.execute(
            delete(Segment).where(
                Segment.story_id == story_id, Segment.position >= start_position
            )
        )
        if commit:
            self.db.commit()
        return result.rowcount


class AnnotationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_segment(self, segment_id: int) -> list[Annotation]:
        stmt = (
            select(Annotation)
            .where(Annotation.segment_id == segment_id)
            .order_by(Annotation.en_start)
        )
        return list(self.db.scalars(stmt))

    def create(
        self,
        segment: Segment,
        kind: str,
        lemma: str,
        en_start: int,
        en_end: int,
        pt_start: int | None = None,
        pt_end: int | None = None,
        extra: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Annotation:
        """Cria a anotação a partir das posições. O texto do trecho (`en_text` e `pt_text`)
        é sempre cortado do texto da frase, então nunca fica diferente das posições."""
        en_text = _slice(segment.text_en, en_start, en_end, "inglês")

        if (pt_start is None) != (pt_end is None):
            raise InvalidAnnotationError("pt_start e pt_end devem vir juntos ou ficar nulos")
        pt_text = None
        if pt_start is not None and pt_end is not None:
            pt_text = _slice(segment.text_pt, pt_start, pt_end, "português")

        annotation = Annotation(
            segment_id=segment.id,
            kind=kind,
            lemma=lemma,
            en_start=en_start,
            en_end=en_end,
            en_text=en_text,
            pt_start=pt_start,
            pt_end=pt_end,
            pt_text=pt_text,
            extra=extra or {},
        )
        self.db.add(annotation)
        self.db.commit() if commit else self.db.flush()
        if commit:
            self.db.refresh(annotation)
        return annotation

    def delete_by_segment(self, segment_id: int, commit: bool = True) -> int:
        """Apaga as anotações de uma frase e devolve quantas eram. Base da reanotação idempotente."""
        result = self.db.execute(
            delete(Annotation).where(Annotation.segment_id == segment_id)
        )
        if commit:
            self.db.commit()
        return result.rowcount


def _slice(text: str, start: int, end: int, language: str) -> str:
    if not 0 <= start < end <= len(text):
        raise InvalidAnnotationError(
            f"posições {start}-{end} fora do texto em {language} (tamanho {len(text)})"
        )
    snippet = text[start:end]
    if len(snippet) > 200:
        raise InvalidAnnotationError(f"trecho em {language} maior que 200 caracteres")
    return snippet
