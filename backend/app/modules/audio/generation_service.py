"""Camada Service da geração de áudio pela API: posse do filtro, status da geração e áudio de cada frase.

Não sintetiza nada: quem gera é a AudioGenerationFacade, numa tarefa em segundo plano disparada pelo Router.
Aqui ficam as decisões que o Router não deve tomar: se o filtro é do usuário, se já há uma geração em
andamento e em que estado está cada frase.
"""
import threading
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.modules.audio.models import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    AudioAsset,
)
from app.modules.audio.repository import AudioAssetRepository, compute_rules_hash
from app.modules.filters.models import ListeningFilter
from app.modules.filters.schemas import FilterRules
from app.modules.filters.service import FilterService
from app.modules.stories.service import StoryService
from app.modules.users.models import User

# Estado geral da geração de uma história
STATE_PENDING = "pending"  # nada em andamento e ainda há frases sem áudio
STATE_GENERATING = "generating"  # há uma geração em andamento
STATE_READY = "ready"  # todas as frases prontas
STATE_FAILED = "failed"  # terminou, mas alguma frase falhou (pedir de novo tenta as que falharam)


class FilterOfOtherStoryError(Exception):
    """O filtro foi criado para outra história."""


class InvalidFilterRulesError(Exception):
    """As regras salvas no filtro não são válidas para gerar áudio."""


class SegmentAudioNotReadyError(Exception):
    """O áudio da frase ainda não foi gerado (pendente ou em geração)."""


class SegmentAudioFailedError(Exception):
    """A geração do áudio da frase falhou."""


class GenerationJobs:
    """Gerações em andamento NESTE processo, por (história, regras, voz).

    Evita disparar duas tarefas para a mesma história e filtro entre o 202 e o início da tarefa (quando as
    frases ainda nem estão em `generating`). Com vários processos, a transição `WHERE status = <atual>` do
    repositório ainda garante que uma frase só é sintetizada por um worker.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: set[tuple[int, str, str]] = set()

    def try_start(self, key: tuple[int, str, str]) -> bool:
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)
            return True

    def finish(self, key: tuple[int, str, str]) -> None:
        with self._lock:
            self._running.discard(key)

    def is_running(self, key: tuple[int, str, str]) -> bool:
        with self._lock:
            return key in self._running


jobs = GenerationJobs()


@dataclass(frozen=True)
class SegmentStatus:
    segment_id: int
    position: int
    status: str
    duration_ms: int | None
    error: str | None


@dataclass(frozen=True)
class GenerationStatus:
    story_id: int
    filter_id: int
    state: str
    total: int
    ready: int
    failed: int
    segments: list[SegmentStatus]


@dataclass(frozen=True)
class GenerationRequest:
    """O que o Router precisa para disparar a Facade em segundo plano."""

    status: GenerationStatus
    start: bool  # True: o Router deve disparar a tarefa (e chamar jobs.finish(job_key) no fim)
    job_key: tuple[int, str, str]
    rules: dict[str, Any]
    voice_id: str  # a voz escolhida para o idioma base do filtro


class AudioGenerationService:
    def __init__(
        self,
        stories: StoryService,
        filters: FilterService,
        assets: AudioAssetRepository,
        *,
        voice_id: str,
        voices: dict[str, str] | None = None,
        jobs: GenerationJobs = jobs,
    ) -> None:
        self.stories = stories
        self.filters = filters
        self.assets = assets
        self.voice_id = voice_id  # voz padrão, para os idiomas sem voz própria
        self.voices = voices or {}  # idioma base do filtro (`pt`/`en`) -> voz
        self.jobs = jobs

    def voice_for(self, rules: dict[str, Any]) -> str:
        """Voz da narração: a do idioma base do filtro, ou a padrão."""
        return self.voices.get(rules["base_language"], self.voice_id)

    def status(self, user: User, story_id: int, filter_id: int) -> GenerationStatus:
        """Estado da geração da história com o filtro. Levanta LookupError (história),
        FilterNotFoundError, FilterOfOtherStoryError ou InvalidFilterRulesError."""
        listening_filter = self._filter_for_story(user, story_id, filter_id)
        rules = self._rules(listening_filter)
        return self._status(story_id, filter_id, rules)

    def request_generation(self, user: User, story_id: int, filter_id: int) -> GenerationRequest:
        """Decide se uma nova geração deve começar. Não começa outra se já há uma em andamento, nem se
        tudo já está pronto. Levanta as mesmas exceções de `status`."""
        listening_filter = self._filter_for_story(user, story_id, filter_id)
        rules = self._rules(listening_filter)
        key = self._job_key(story_id, rules)
        current = self._status(story_id, filter_id, rules)

        if current.state == STATE_READY or not self.jobs.try_start(key):
            return GenerationRequest(status=current, start=False, job_key=key, rules=rules, voice_id=self.voice_for(rules))
        # A tarefa vai começar: para o front, a geração já está em andamento
        started = GenerationStatus(**{**current.__dict__, "state": STATE_GENERATING})
        return GenerationRequest(status=started, start=True, job_key=key, rules=rules, voice_id=self.voice_for(rules))

    def segment_audio(self, user: User, segment_id: int, filter_id: int) -> AudioAsset:
        """Áudio pronto da frase com o filtro. Levanta FilterNotFoundError, LookupError (frase),
        FilterOfOtherStoryError, InvalidFilterRulesError, SegmentAudioNotReadyError ou SegmentAudioFailedError."""
        listening_filter = self.filters.get(user, filter_id)
        segment = self.stories.get_segment(segment_id)
        if listening_filter.story_id is not None and listening_filter.story_id != segment.story_id:
            raise FilterOfOtherStoryError()
        rules = self._rules(listening_filter)

        asset = self.assets.get_by_segment(
            segment_id, rules_hash=compute_rules_hash(rules), voice_id=self.voice_for(rules)
        )
        if asset is None or asset.status in (STATUS_PENDING, STATUS_GENERATING):
            raise SegmentAudioNotReadyError()
        if asset.status == STATUS_FAILED:
            raise SegmentAudioFailedError(asset.error or "")
        return asset

    # ---------- auxiliares ----------

    def _filter_for_story(self, user: User, story_id: int, filter_id: int) -> ListeningFilter:
        listening_filter = self.filters.get(user, filter_id)  # filtro de outro usuário: FilterNotFoundError
        self.stories.get_segments(story_id)  # história inexistente: LookupError
        if listening_filter.story_id is not None and listening_filter.story_id != story_id:
            raise FilterOfOtherStoryError()
        return listening_filter

    @staticmethod
    def _rules(listening_filter: ListeningFilter) -> dict[str, Any]:
        """Regras validadas e normalizadas: o mesmo dicionário (e o mesmo hash) na geração e no status."""
        try:
            return FilterRules.model_validate(listening_filter.rules).model_dump()
        except ValidationError as exc:
            raise InvalidFilterRulesError(str(exc)) from exc

    def _job_key(self, story_id: int, rules: dict[str, Any]) -> tuple[int, str, str]:
        return (story_id, compute_rules_hash(rules), self.voice_for(rules))

    def _status(self, story_id: int, filter_id: int, rules: dict[str, Any]) -> GenerationStatus:
        _, segments = self.stories.get_segments(story_id)
        key = self._job_key(story_id, rules)
        by_segment = {a.segment_id: a for a in self.assets.list_by_story(story_id, rules_hash=key[1], voice_id=key[2])}

        items = []
        for segment in segments:
            asset = by_segment.get(segment.id)
            items.append(
                SegmentStatus(
                    segment_id=segment.id,
                    position=segment.position,
                    status=asset.status if asset else STATUS_PENDING,
                    duration_ms=asset.duration_ms if asset else None,
                    error=asset.error if asset and asset.status == STATUS_FAILED else None,
                )
            )

        counts = {s: sum(1 for i in items if i.status == s) for s in (STATUS_READY, STATUS_FAILED, STATUS_GENERATING)}
        if counts[STATUS_READY] == len(items):
            state = STATE_READY
        elif self.jobs.is_running(key) or counts[STATUS_GENERATING]:
            state = STATE_GENERATING
        elif counts[STATUS_FAILED] and counts[STATUS_READY] + counts[STATUS_FAILED] == len(items):
            state = STATE_FAILED
        else:
            state = STATE_PENDING

        return GenerationStatus(
            story_id=story_id,
            filter_id=filter_id,
            state=state,
            total=len(items),
            ready=counts[STATUS_READY],
            failed=counts[STATUS_FAILED],
            segments=items,
        )
