"""Schemas Pydantic de entrada e saída da API deste módulo."""
from pydantic import BaseModel, ConfigDict


class StoryRead(BaseModel):
    # from_attributes permite montar o schema direto a partir do modelo SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
