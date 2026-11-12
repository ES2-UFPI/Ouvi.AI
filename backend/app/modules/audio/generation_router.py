"""Camada Router da geração de áudio: valida a entrada e delega ao Service e à Facade.

Gerar o áudio leva de segundos a minutos, então o POST responde `202` na hora e a Facade roda em segundo
plano (BackgroundTasks), com uma sessão de banco própria. O front acompanha pelo GET de status (polling).
"""
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.integrations.storage import ObjectStorage, StorageError, StorageObjectNotFound, get_storage
from app.integrations.tts import TTSProvider, get_tts_provider
from app.modules.audio.facade import run_generation
from app.modules.audio.generation_service import (
    AudioGenerationService,
    FilterOfOtherStoryError,
    GenerationStatus,
    InvalidFilterRulesError,
    SegmentAudioFailedError,
    SegmentAudioNotReadyError,
    jobs,
)
from app.modules.audio.repository import AudioAssetRepository
from app.modules.audio.router import get_audio_service
from app.modules.audio.schemas import (
    AudioGenerationCreate,
    AudioGenerationStatusRead,
    SegmentAudioRead,
)
from app.modules.audio.service import AudioService
from app.modules.auth.dependencies import get_current_user
from app.modules.filters.router import get_filter_service
from app.modules.filters.service import FilterNotFoundError
from app.modules.stories.service import StoryService
from app.modules.users.models import User

router = APIRouter(tags=["audio"])

_ERRORS = {
    401: {"description": "Sem token ou token inválido"},
    404: {"description": "História/frase inexistente, ou filtro inexistente ou de outro usuário"},
    422: {"description": "Filtro de outra história, regras do filtro inválidas ou `filter_id` ausente"},
}


def get_session_factory() -> Callable[[], Session]:
    """Fábrica da sessão da tarefa em segundo plano. Nos testes, troque por uma ligada à conexão de teste."""
    return SessionLocal


def get_generation_service(
    db: Session = Depends(get_db),
) -> AudioGenerationService:
    return AudioGenerationService(
        StoryService.from_session(db),
        get_filter_service(db),
        AudioAssetRepository(db),
        voice_id=get_settings().tts_voice_id,
    )


def _status_read(generation_status: GenerationStatus) -> AudioGenerationStatusRead:
    return AudioGenerationStatusRead.model_validate(asdict(generation_status))


def _call(action: Callable[[], Any]) -> Any:
    """Traduz as exceções do Service em respostas HTTP (as mesmas para as três rotas)."""
    try:
        return action()
    except FilterNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filtro não encontrado")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except FilterOfOtherStoryError:
        raise HTTPException(status_code=422, detail="O filtro é de outra história")
    except InvalidFilterRulesError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"As regras do filtro não podem ser usadas: {exc}",
        )


def _generate_in_background(
    job_key: tuple[int, str, str],
    session_factory: Callable[[], Session],
    tts: TTSProvider,
    storage: ObjectStorage,
    **kwargs: Any,
) -> None:
    try:
        run_generation(session_factory, tts, storage, **kwargs)
    finally:
        jobs.finish(job_key)  # libera um novo pedido para a mesma história e filtro


@router.post(
    "/stories/{story_id}/audio",
    response_model=AudioGenerationStatusRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Gera o áudio bilíngue da história com o filtro (em segundo plano)",
    responses={
        200: {"description": "Todas as frases já estavam prontas: nada foi disparado", "model": AudioGenerationStatusRead},
        202: {"description": "Geração disparada agora, ou já em andamento (não dispara outra)"},
        **_ERRORS,
    },
)
def request_story_audio(
    story_id: int,
    data: AudioGenerationCreate,
    response: Response,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: AudioGenerationService = Depends(get_generation_service),
    tts: TTSProvider = Depends(get_tts_provider),
    storage: ObjectStorage = Depends(get_storage),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> AudioGenerationStatusRead:
    """Dispara a geração e responde `202` na hora, com o status atual. Pedir de novo durante a geração não
    dispara outra; pedir depois de tudo pronto responde `200`. Frases que falharam são tentadas de novo."""
    request = _call(lambda: service.request_generation(user, story_id, data.filter_id))
    if request.status.state == "ready":
        response.status_code = status.HTTP_200_OK
    elif request.start:
        background_tasks.add_task(
            _generate_in_background,
            request.job_key,
            session_factory,
            tts,
            storage,
            voice_id=service.voice_id,
            story_id=story_id,
            rules=request.rules,
            user_id=user.id,
        )
    return _status_read(request.status)


@router.get(
    "/stories/{story_id}/audio/status",
    response_model=AudioGenerationStatusRead,
    summary="Progresso da geração do áudio da história com o filtro",
    responses=_ERRORS,
)
def get_story_audio_status(
    story_id: int,
    filter_id: int = Query(..., description="Filtro de audição, do usuário logado"),
    user: User = Depends(get_current_user),
    service: AudioGenerationService = Depends(get_generation_service),
) -> AudioGenerationStatusRead:
    """Total de frases, quantas estão prontas e quantas falharam, o estado geral e o de cada frase
    (com o `segment_id`, para pedir o áudio em `GET /audio/segments/{segment_id}`)."""
    return _status_read(_call(lambda: service.status(user, story_id, filter_id)))


@router.get(
    "/audio/segments/{segment_id}",
    response_model=SegmentAudioRead,
    summary="URL assinada do áudio de uma frase",
    responses={
        **_ERRORS,
        409: {"description": "O áudio da frase ainda não está pronto, ou a geração dele falhou"},
        503: {"description": "Armazenamento indisponível"},
    },
)
def get_segment_audio(
    segment_id: int,
    request: Request,
    filter_id: int = Query(..., description="Filtro de audição, do usuário logado"),
    user: User = Depends(get_current_user),
    service: AudioGenerationService = Depends(get_generation_service),
    audio: AudioService = Depends(get_audio_service),
) -> SegmentAudioRead:
    """Devolve a URL que o player põe no `src` do `<audio>`. Ela aponta para `GET /audio/stream`, que
    aceita o header `Range` (o navegador pula para o meio do áudio pedindo só um trecho)."""

    def ready_asset():
        try:
            return service.segment_audio(user, segment_id, filter_id)
        except SegmentAudioNotReadyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="O áudio desta frase ainda não está pronto"
            )
        except SegmentAudioFailedError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A geração do áudio desta frase falhou"
            )

    asset = _call(ready_asset)
    try:
        params = audio.sign(asset.storage_key)
    except StorageObjectNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não encontrado")
    except StorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Armazenamento indisponível")

    url = request.url_for("stream_audio").include_query_params(**params)
    return SegmentAudioRead(
        url=str(url),
        expires_at=datetime.fromtimestamp(int(params["expires"]), tz=timezone.utc),
        segment_id=segment_id,
        duration_ms=asset.duration_ms,
        format=asset.format,
    )
