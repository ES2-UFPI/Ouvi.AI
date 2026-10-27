"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.core.config import get_settings
from app.integrations.storage import (
    ObjectStorage,
    StorageError,
    StorageObjectNotFound,
    get_storage,
)
from app.modules.audio.ranges import RangeNotSatisfiable
from app.modules.audio.schemas import AudioUrlRead
from app.modules.audio.service import AudioService
from app.modules.audio.signing import AudioSignatureError, AudioUrlSigner
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User

router = APIRouter(prefix="/audio", tags=["audio"])


@lru_cache
def get_audio_signer() -> AudioUrlSigner:
    settings = get_settings()
    return AudioUrlSigner(settings.audio_signing_secret, ttl_seconds=settings.audio_url_ttl_seconds)


def get_audio_service(
    storage: ObjectStorage = Depends(get_storage),
    signer: AudioUrlSigner = Depends(get_audio_signer),
) -> AudioService:
    return AudioService(storage, signer)


@router.get("/url", response_model=AudioUrlRead)
def get_audio_url(
    request: Request,
    key: str = Query(..., description="Chave do áudio no armazenamento, ex.: samples/tom-440-660hz.wav"),
    _: User = Depends(get_current_user),
    service: AudioService = Depends(get_audio_service),
) -> AudioUrlRead:
    """Gera a URL assinada do áudio. O front chama esta rota com o token e põe a URL no `<audio>`."""
    try:
        params = service.sign(key)
    except StorageObjectNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não encontrado")
    except StorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Armazenamento indisponível")

    url = request.url_for("stream_audio").include_query_params(**params)
    expires_at = datetime.fromtimestamp(int(params["expires"]), tz=timezone.utc)
    return AudioUrlRead(url=str(url), expires_at=expires_at)


@router.get(
    "/stream",
    response_class=Response,
    responses={
        200: {"description": "Arquivo inteiro (requisição sem `Range`)", "content": {"audio/*": {}}},
        206: {"description": "Trecho pedido no header `Range`", "content": {"audio/*": {}}},
        403: {"description": "Assinatura adulterada ou URL expirada"},
        404: {"description": "Áudio não encontrado"},
        416: {"description": "Faixa inválida ou fora do arquivo"},
    },
)
def stream_audio(
    key: str = Query(..., description="Chave do áudio no armazenamento"),
    expires: int = Query(..., description="Expiração da URL (timestamp Unix)"),
    signature: str = Query(..., description="Assinatura HMAC-SHA256 da chave e da expiração"),
    range_header: str | None = Header(None, alias="Range"),
    service: AudioService = Depends(get_audio_service),
) -> Response:
    """Entrega o áudio para a tag `<audio>`, com suporte ao header `Range`.

    Sem token: o `<audio>` do navegador não envia o header `Authorization`. O acesso é garantido
    pela URL assinada, gerada em `GET /audio/url`.
    """
    try:
        chunk = service.stream(key, expires, signature, range_header)
    except AudioSignatureError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="URL inválida ou expirada")
    except StorageObjectNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não encontrado")
    except RangeNotSatisfiable as exc:
        # A RFC pede o tamanho do arquivo no 416, para o cliente refazer o pedido
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Faixa inválida",
            headers={"Content-Range": f"bytes */{exc.size}"},
        )
    except StorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Armazenamento indisponível")

    # Accept-Ranges avisa o navegador de que ele pode pular para o meio pedindo só um trecho
    headers = {"Accept-Ranges": "bytes"}
    if chunk.byte_range is None:
        return Response(content=chunk.data, media_type=chunk.content_type, headers=headers)

    headers["Content-Range"] = chunk.byte_range.content_range(chunk.size)
    return Response(
        content=chunk.data,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=chunk.content_type,
        headers=headers,
    )
