"""Schemas Pydantic de entrada e saída da API deste módulo."""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # max_length evita enviar senhas gigantes só para pesar o custo do hash
    password: str = Field(min_length=8, max_length=128)
