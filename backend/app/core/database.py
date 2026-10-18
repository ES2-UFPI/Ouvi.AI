from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# pool_pre_ping testa a conexão antes de usá-la e evita erro com conexões que o banco já fechou
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Classe base de todos os modelos. O Alembic lê o `Base.metadata` para gerar migrações."""


def get_db() -> Iterator[Session]:
    """Dependência do FastAPI: abre uma sessão por requisição e sempre a fecha no final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
