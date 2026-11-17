"""Testes das migrações do Alembic: valem para todas as tabelas do projeto.

Uma migração nova não pode criar um segundo head (duas branches acabando em revisões diferentes), e os
modelos SQLAlchemy precisam bater com o banco depois do `alembic upgrade head` (o mesmo que o `alembic check`).
"""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _todos_os_modelos():
    """Importa os modelos de todos os módulos, como o alembic/env.py, e devolve o metadata completo.

    Sem isso, uma tabela de um módulo não importado pareceria sobrando no banco.
    """
    from app.core.database import Base
    from app.modules.audio import models as _audio  # noqa: F401
    from app.modules.filters import models as _filtros  # noqa: F401
    from app.modules.progress import models as _progresso  # noqa: F401
    from app.modules.stories import models as _historias  # noqa: F401
    from app.modules.users import models as _usuarios  # noqa: F401

    return Base.metadata


def test_as_migracoes_tem_um_unico_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_o_alembic_env_importa_os_modelos_de_todos_os_modulos():
    """Um módulo novo com models.py precisa entrar no alembic/env.py, senão o autogenerate não o enxerga."""
    env = (BACKEND / "alembic" / "env.py").read_text(encoding="utf-8")
    modulos = sorted(p.parent.name for p in (BACKEND / "app" / "modules").glob("*/models.py"))
    faltando = [m for m in modulos if f"from app.modules.{m} import models" not in env]
    assert faltando == []


def test_os_modelos_e_as_migracoes_estao_iguais(db_session):
    """Equivale ao `alembic check`: o autogenerate não acharia nada para mudar."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    contexto = MigrationContext.configure(db_session.connection())
    assert compare_metadata(contexto, _todos_os_modelos()) == []
