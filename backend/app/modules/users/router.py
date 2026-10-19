"""Camada Router: recebe a requisição HTTP e delega ao Service."""
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])
