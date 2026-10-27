"""Testes do parser do header Range, com um arquivo de 1000 bytes."""
import pytest

from app.modules.audio.ranges import ByteRange, RangeNotSatisfiable, parse_range

SIZE = 1000


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [
        ("bytes=0-99", 0, 99),  # faixa fechada: exatamente 100 bytes
        ("bytes=0-0", 0, 0),  # um byte só
        ("bytes=500-", 500, 999),  # faixa aberta: até o fim
        ("bytes=0-", 0, 999),  # o que o navegador pede ao abrir o áudio
        ("bytes=-200", 800, 999),  # faixa final: os últimos 200 bytes
        ("bytes=-5000", 0, 999),  # mais bytes do que o arquivo tem: o arquivo inteiro
        ("bytes=900-5000", 900, 999),  # fim além do arquivo é cortado no último byte
        ("bytes=999-999", 999, 999),  # o último byte
        (" bytes=10-19 ", 10, 19),  # espaços em volta são ignorados
    ],
)
def test_valid_ranges(header, start, end):
    assert parse_range(header, SIZE) == ByteRange(start, end)


@pytest.mark.parametrize(
    "header",
    [
        "bytes=1000-",  # começa depois do último byte
        "bytes=1000-1999",
        "bytes=100-50",  # fim antes do início
        "bytes=-0",  # zero bytes do fim
        "bytes=-",  # sem nenhum número
        "bytes=abc-def",
        "bytes=0-99,200-299",  # várias faixas: sem suporte
        "items=0-99",  # unidade diferente de bytes
        "bytes 0-99",  # sem o sinal de igual
        "",
    ],
)
def test_invalid_ranges(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, SIZE)


def test_no_header_means_whole_file():
    assert parse_range(None, SIZE) is None


@pytest.mark.parametrize("header", ["bytes=0-", "bytes=-10"])
def test_empty_file_has_no_satisfiable_range(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 0)


def test_length_and_content_range():
    byte_range = parse_range("bytes=0-99", SIZE)
    assert byte_range.length == 100
    assert byte_range.content_range(SIZE) == "bytes 0-99/1000"
