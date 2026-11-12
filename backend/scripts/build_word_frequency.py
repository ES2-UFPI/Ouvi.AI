"""Gera nlp/data/en_word_frequency.txt a partir da biblioteca `wordfreq` (ferramenta de desenvolvimento).

A `wordfreq` NÃO entra no requirements.txt: o pacote tem cerca de 56 MB (dados de dezenas de idiomas) e a API
só precisa de uma fração do inglês. Por isso a lista é gerada uma vez, com este comando, e versionada no
repositório (cerca de 330 KB). Para regerar:

    pip install wordfreq
    python -m scripts.build_word_frequency

Licença: o código da wordfreq é Apache 2.0 e os dados são CC BY-SA 4.0 (Robyn Speer, Luminoso).
O arquivo gerado é derivado desses dados e mantém a mesma licença (veja o cabeçalho dele).
"""
import re
from importlib import metadata
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "app" / "modules" / "stories" / "nlp" / "data" / "en_word_frequency.txt"

# Palavras com frequência abaixo disto ficam fora do arquivo: o detector as trata como raras
MIN_ZIPF = 3.0
TOP_N = 100_000

HEADER = """\
# Frequência de palavras do inglês (escala Zipf: log10 de ocorrências por bilhão de palavras).
# 7 = muito comum ("the"), 3 = rara. Palavras ausentes têm Zipf < {min_zipf} e são tratadas como raras.
# Gerado por backend/scripts/build_word_frequency.py a partir da wordfreq {version}
# (https://github.com/rspeer/wordfreq). Dados: CC BY-SA 4.0, Robyn Speer / Luminoso. Não edite à mão.
"""


def main() -> int:
    try:
        import wordfreq
        from wordfreq import top_n_list, zipf_frequency
    except ImportError:
        print("Instale a wordfreq antes: pip install wordfreq", file=sys.stderr)
        return 1

    words = sorted(
        {w for w in top_n_list("en", TOP_N) if re.fullmatch(r"[a-z]+", w)},
    )
    lines = [HEADER.format(min_zipf=MIN_ZIPF, version=metadata.version("wordfreq")).rstrip("\n")]
    count = 0
    for word in words:
        zipf = zipf_frequency(word, "en")
        if zipf >= MIN_ZIPF:
            lines.append(f"{word} {zipf:.2f}")
            count += 1
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{count} palavras gravadas em {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
