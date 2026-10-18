"""Rota de health check, usada pelo Docker, pelo deploy e pelo desenvolvedor."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
