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

    # Origens do front-end autorizadas a chamar a API, separadas por vírgula
    cors_origins: str = "http://localhost:5173"

    # Segredo das URLs assinadas do áudio (HMAC). Separado do JWT: trocar um não invalida o outro
    audio_signing_secret: str = "change-me-audio"
    # Validade da URL do player. Curta, mas maior que uma história: o navegador continua pedindo
    # trechos com a mesma URL enquanto o usuário pula pelo áudio
    audio_url_ttl_seconds: int = 3600

    # "development" libera comodidades de dev, como criar o bucket sozinho na subida da API
    app_env: str = "development"

    # Armazenamento de objetos: "s3" (MinIO em dev, Cloudflare R2 em produção) ou "memory" (testes)
    storage_backend: str = "s3"
    storage_endpoint: str = "http://localhost:9000"
    # Endpoint que o NAVEGADOR enxerga, usado nas URLs assinadas. Vazio = o mesmo do storage_endpoint
    storage_public_endpoint: str | None = None
    storage_access_key: str = "ouveai"
    storage_secret_key: str = "ouveai123"
    storage_bucket: str = "ouveai-audio"
    # MinIO aceita qualquer região; o R2 usa "auto"
    storage_region: str = "us-east-1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
