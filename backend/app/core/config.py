from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente (e do arquivo .env, se existir).

    Os valores padrão servem só para desenvolvimento local; em produção
    todos devem vir do ambiente.
    """

    database_url: str = "postgresql+psycopg2://ouveai:ouveai@localhost:5432/ouveai"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    # Access token curto: se vazar, vale por pouco tempo. O refresh token dura mais e só serve para renovar.
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "ouveai"
    minio_root_password: str = "ouveai123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def usar_driver_psycopg2(cls, url: str) -> str:
        """O SQLAlchemy 2 assume o driver psycopg (v3) para `postgresql://`.
        O projeto usa psycopg2, então o driver é fixado aqui."""
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Singleton: as configurações são lidas uma única vez e reaproveitadas."""
    return Settings()
