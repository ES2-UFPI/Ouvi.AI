"""Importação de histórias enviadas pelo usuário (US18).

Padrões Strategy + Factory, como planejado na wiki: cada formato de arquivo é um `ContentExtractor`
(estratégia) que transforma os bytes em frases bilíngues, e o `ExtractorFactory` escolhe a estratégia pela
extensão do arquivo. Um formato novo (PDF, link de site) é uma classe a mais e uma linha na fábrica.

Depois de extraídas, as frases passam pelo mesmo caminho das fábulas do catálogo: são gravadas e anotadas
pelo `TextAnnotator` (phrasal verbs, palavras difíceis e vocabulário avançado), e a história pode ser ouvida
nos Cenários A, B e C.
"""
import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePath

from sqlalchemy.orm import Session

from app.modules.stories.annotator import TextAnnotator
from app.modules.stories.nlp.alignment import DictionaryAligner, load_all_equivalents
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.nlp.factory import DetectorFactory
from app.modules.stories.models import Story
from app.modules.stories.repository import SegmentRepository, StoryRepository

MAX_FILE_BYTES = 100_000  # ~100 KB: um conto curto. Arquivos maiores custariam caro no TTS
MAX_SEGMENTS = 60
MAX_SENTENCE_CHARS = 500
MAX_TITLE_CHARS = 200


class StoryImportError(ValueError):
    """O arquivo não pode virar uma história. A mensagem é mostrada ao usuário."""


@dataclass
class ExtractedStory:
    title: str | None
    description: str | None = None
    segments: list[tuple[str, str]] = field(default_factory=list)  # (inglês, português)
    # Glossário do próprio arquivo: termo em inglês -> formas em português. Completa o dicionário do
    # catálogo, que só conhece as palavras das fábulas
    glossary: dict[str, list[str]] = field(default_factory=dict)


class ContentExtractor(ABC):
    """Estratégia: transforma o conteúdo de um tipo de arquivo em frases bilíngues."""

    @abstractmethod
    def extract(self, data: bytes) -> ExtractedStory: ...

    @staticmethod
    def _decode(data: bytes) -> str:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise StoryImportError("O arquivo precisa estar em UTF-8.") from None


def _add_glossary(glossary: dict[str, list[str]], term: str, forms: str) -> None:
    term = " ".join(term.lower().split())
    for form in forms.split("|"):
        form = " ".join(form.split())
        if term and form and form not in glossary.setdefault(term, []):
            glossary[term].append(form)


class BilingualTextExtractor(ContentExtractor):
    """`.txt`: a primeira linha começando com `#` é o título (opcional); depois, uma frase em inglês seguida
    da tradução em português, linha por linha. Linhas em branco entre os pares são ignoradas.

    Linhas `= inglês -> português` formam o glossário (opcional): dizem qual trecho do português corresponde
    a um termo do inglês, para a troca de idioma funcionar com palavras que o dicionário não conhece.
    Várias formas separadas por `|` (ex.: `= pick up -> apanhou | pegou`). Linhas `=` sem `->` são comentários."""

    def extract(self, data: bytes) -> ExtractedStory:
        lines = [line.strip() for line in self._decode(data).splitlines()]
        glossary: dict[str, list[str]] = {}
        for line in lines:
            if line.startswith("=") and "->" in line:
                term, forms = line[1:].split("->", 1)
                _add_glossary(glossary, term, forms)
        lines = [line for line in lines if line and not line.startswith("=")]
        title = None
        if lines and lines[0].startswith("#"):
            title = lines.pop(0).lstrip("#").strip() or None
        if len(lines) % 2:
            raise StoryImportError(
                f"O texto tem {len(lines)} linhas: cada frase em inglês precisa da tradução em português "
                f"na linha de baixo (a última frase ficou sem par)."
            )
        return ExtractedStory(title=title, segments=list(zip(lines[0::2], lines[1::2])), glossary=glossary)


class SeedJsonExtractor(ContentExtractor):
    """`.json` no mesmo formato das fábulas do catálogo: `title`, `description` e `segments: [{en, pt}]`."""

    def extract(self, data: bytes) -> ExtractedStory:
        try:
            raw = json.loads(self._decode(data))
        except json.JSONDecodeError as exc:
            raise StoryImportError(f"JSON inválido: {exc.msg} (linha {exc.lineno}).") from None
        if not isinstance(raw, dict) or not isinstance(raw.get("segments"), list):
            raise StoryImportError('O JSON precisa ter a lista "segments", com "en" e "pt" em cada frase.')
        segments = []
        glossary: dict[str, list[str]] = {}
        for index, item in enumerate(raw["segments"], start=1):
            if not isinstance(item, dict) or not isinstance(item.get("en"), str) or not isinstance(item.get("pt"), str):
                raise StoryImportError(f'A frase {index} do JSON precisa ter "en" e "pt" (textos).')
            segments.append((item["en"].strip(), item["pt"].strip()))
            # Os phrasal verbs do formato do seed já trazem o equivalente em português
            for pv in item.get("phrasal_verbs") or []:
                if isinstance(pv, dict) and isinstance(pv.get("pt"), str):
                    for term in (pv.get("lemma"), pv.get("en")):
                        if isinstance(term, str):
                            _add_glossary(glossary, term, pv["pt"])
        extra = raw.get("glossary")
        if isinstance(extra, dict):
            for term, forms in extra.items():
                values = [forms] if isinstance(forms, str) else forms if isinstance(forms, list) else []
                _add_glossary(glossary, str(term), "|".join(f for f in values if isinstance(f, str)))
        title = raw.get("title") if isinstance(raw.get("title"), str) else None
        description = raw.get("description") if isinstance(raw.get("description"), str) else None
        return ExtractedStory(title=title, description=description, segments=segments, glossary=glossary)


class ExtractorFactory:
    # Um formato novo entra aqui com uma linha (ex.: ".pdf": PdfExtractor)
    _registry: dict[str, type[ContentExtractor]] = {
        ".txt": BilingualTextExtractor,
        ".json": SeedJsonExtractor,
    }

    @classmethod
    def extensions(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def for_filename(cls, filename: str) -> ContentExtractor:
        suffix = PurePath(filename or "").suffix.lower()
        try:
            return cls._registry[suffix]()
        except KeyError:
            raise StoryImportError(
                f"Tipo de arquivo não suportado ({suffix or 'sem extensão'}). Envie: {', '.join(cls.extensions())}."
            ) from None


class GlossaryAligner:
    """Alinhador da história enviada: o dicionário do catálogo somado ao glossário do arquivo. O termo do
    glossário vale tanto na forma de dicionário (`pick up`) quanto como aparece no texto (`picked it up`)."""

    name = "glossary"

    def __init__(self, glossary: dict[str, list[str]]) -> None:
        self._by_lemma = DictionaryAligner({**load_all_equivalents(), **glossary})
        self._by_text = DictionaryAligner(glossary)

    def align(
        self, span: DetectedSpan, text_en: str, text_pt: str, taken: Sequence[tuple[int, int]] = ()
    ) -> tuple[int, int] | None:
        found = self._by_lemma.align(span, text_en, text_pt, taken)
        if found is None:
            surface = replace(span, lemma=" ".join(span.text.lower().split()))
            found = self._by_text.align(surface, text_en, text_pt, taken)
        return found


@dataclass(frozen=True)
class ImportResult:
    story: Story
    segments: int
    annotations: int
    aligned: int  # quantos trechos acharam o equivalente em português (só esses podem ser trocados)


class StoryImportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.stories = StoryRepository(db)
        self.segments = SegmentRepository(db)

    def import_file(self, owner_id: int, filename: str, data: bytes, title: str | None = None) -> ImportResult:
        """Valida, grava a história como particular do usuário e já a anota. Levanta StoryImportError."""
        if not data:
            raise StoryImportError("O arquivo está vazio.")
        if len(data) > MAX_FILE_BYTES:
            raise StoryImportError(f"Arquivo grande demais: o limite é {MAX_FILE_BYTES // 1000} KB.")
        extracted = ExtractorFactory.for_filename(filename).extract(data)
        self._validate(extracted)

        final_title = (title or "").strip() or extracted.title or PurePath(filename).stem.replace("_", " ")
        final_title = final_title[:MAX_TITLE_CHARS]
        try:
            story = self.stories.create(
                final_title,
                extracted.description or "História enviada por você.",
                "en",
                commit=False,
                owner_id=owner_id,
            )
            for position, (en, pt) in enumerate(extracted.segments):
                self.segments.create(story.id, position, en, pt, commit=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        detectors = [DetectorFactory.create(kind) for kind in DetectorFactory.kinds()]
        annotator = TextAnnotator(self.db, detectors, GlossaryAligner(extracted.glossary))
        report = annotator.annotate_story(story.id)
        return ImportResult(
            story=story, segments=len(extracted.segments), annotations=report.detected, aligned=report.aligned
        )

    @staticmethod
    def _validate(extracted: ExtractedStory) -> None:
        if not extracted.segments:
            raise StoryImportError("Nenhuma frase encontrada no arquivo.")
        if len(extracted.segments) > MAX_SEGMENTS:
            raise StoryImportError(f"Texto longo demais: o limite é {MAX_SEGMENTS} frases.")
        for index, (en, pt) in enumerate(extracted.segments, start=1):
            if not en or not pt:
                raise StoryImportError(f"A frase {index} está sem o texto em inglês ou sem a tradução.")
            if len(en) > MAX_SENTENCE_CHARS or len(pt) > MAX_SENTENCE_CHARS:
                raise StoryImportError(f"A frase {index} passa de {MAX_SENTENCE_CHARS} caracteres: divida-a.")
