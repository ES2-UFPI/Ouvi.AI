"""Schemas Pydantic de entrada e saída da API deste módulo."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """Dados públicos do usuário. Não tem password_hash de propósito: o hash nunca sai da API."""

    # from_attributes permite montar o schema direto a partir do modelo SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    created_at: datetime
