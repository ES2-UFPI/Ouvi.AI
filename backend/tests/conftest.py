"""Configuração compartilhada dos testes."""


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Mostra no fim de toda execução o relatório do corpus do detector, quando ele rodou."""
    report = getattr(config, "corpus_report", None)
    if not report:
        return
    terminalreporter.section("Detector de phrasal verbs: corpus de referência")
    for line in report:
        terminalreporter.write_line(line)
