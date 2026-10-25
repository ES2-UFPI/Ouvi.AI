"""Configuração compartilhada dos testes."""
import pytest


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Mostra no fim de toda execução o relatório do corpus do detector, quando ele rodou."""
    report = getattr(config, "corpus_report", None)
    if not report:
        return
    terminalreporter.section("Detector de phrasal verbs: corpus de referência")
    for line in report:
        terminalreporter.write_line(line)


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

    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("banco de dados indisponível (suba com: docker compose up -d)")

    tem_tabelas = inspect(connection).has_table("annotations")
    connection.rollback()  # o inspect() abre uma transação sozinha; ela precisa acabar antes do begin()
    if not tem_tabelas:
        connection.close()
        pytest.skip("tabelas não encontradas (rode: docker compose exec api alembic upgrade head)")

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
