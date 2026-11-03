"""Configuração compartilhada dos testes."""
import os

import pytest


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Mostra no fim de toda execução o relatório do corpus do detector, quando ele rodou."""
    report = getattr(config, "corpus_report", None)
    if not report:
        return
    terminalreporter.section("Detector de phrasal verbs: corpus de referência")
    for line in report:
        terminalreporter.write_line(line)


PASSWORD = "Senha1234"


@pytest.fixture
def api(db_session):
    """Cliente HTTP da API inteira, usando a sessão de teste (desfeita no final) e a autenticação REAL.

    Diferente do `client` de test_story_segments.py, aqui o token é de verdade: o teste cadastra e
    entra pela própria API, como o front faz.
    """
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(api):
    """Cria um usuário pela API e devolve `(dados_do_usuário, headers_com_token)`."""
    contador = {"n": 0}

    def _make(name: str = "Ana", email: str | None = None):
        contador["n"] += 1
        email = email or f"ana{contador['n']}@teste.com"
        resposta = api.post("/auth/register", json={"name": name, "email": email, "password": PASSWORD})
        assert resposta.status_code == 201, resposta.text
        tokens = api.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
        return resposta.json(), {"Authorization": f"Bearer {tokens['access_token']}"}

    return _make


@pytest.fixture
def db_session():
    """Sessão do banco de dados cujas alterações são DESFEITAS no fim de cada teste.

    O teste pode gravar e confirmar (`commit`) à vontade: tudo acontece dentro de uma transação
    externa que nunca é confirmada, então os dados do ambiente de desenvolvimento não são tocados.
    Se o banco não estiver no ar ou não tiver as tabelas, o teste é pulado.
    """
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from app.core.database import engine

    # Na CI (a variável CI vale "true" no GitHub Actions) um teste de banco nunca pode ser pulado em
    # silêncio: sem banco ou sem tabelas, a suíte deve FALHAR, senão ela ficaria verde sem testar nada.
    sem_banco = pytest.fail if os.environ.get("CI") else pytest.skip

    try:
        connection = engine.connect()
    except OperationalError:
        sem_banco("banco de dados indisponível (suba com: docker compose up -d)")

    tem_tabelas = inspect(connection).has_table("annotations")
    connection.rollback()  # o inspect() abre uma transação sozinha; ela precisa acabar antes do begin()
    if not tem_tabelas:
        connection.close()
        sem_banco("tabelas não encontradas (rode: docker compose exec api alembic upgrade head)")

    outer = connection.begin()
    # create_savepoint: o commit() do código testado só libera um ponto de salvamento, e o
    # rollback() do código testado volta até o último commit, sem encerrar a transação externa
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
