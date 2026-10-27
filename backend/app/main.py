import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.integrations.storage import StorageError, get_storage
from app.modules.auth.router import router as auth_router
from app.modules.filters.router import router as filters_router
from app.modules.health.router import router as health_router
from app.modules.stories.router import router as stories_router
from app.modules.users.router import router as users_router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Só em desenvolvimento: em produção o bucket é criado uma vez, à mão, com as permissões certas
    if get_settings().app_env == "development":
        try:
            get_storage().ensure_bucket()
        except StorageError as exc:
            # Sem MinIO a API sobe mesmo assim; só as rotas de áudio vão falhar
            logger.warning("Não foi possível preparar o bucket: %s", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Ouve.AI", lifespan=lifespan)

    # Sem CORS o navegador bloqueia as chamadas do front (outra origem/porta) à API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(filters_router)
    app.include_router(stories_router)

    return app


app = create_app()
