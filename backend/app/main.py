from fastapi import FastAPI

from app.modules.auth.router import router as auth_router
from app.modules.filters.router import router as filters_router
from app.modules.health.router import router as health_router
from app.modules.stories.router import router as stories_router
from app.modules.users.router import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(title="Ouve.AI")

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(filters_router)
    app.include_router(stories_router)

    return app


app = create_app()
