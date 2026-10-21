"""Schemas Pydantic de entrada e saída da API deste módulo."""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # max_length evita enviar senhas gigantes só para pesar o custo do hash
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    # No login não se valida o tamanho mínimo: só se confere a senha, sem revelar as regras de cadastro
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
