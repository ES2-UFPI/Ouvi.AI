"""Testes da curva de densidade crescente (US11): poucas trocas no começo da história e muitas no final.

Funções puras (sem banco): a mesma conta é espelhada no front (frontend/src/features/player/swaps.ts).
"""
from dataclasses import dataclass, field

import pytest

from app.modules.audio.composer import AudioComposer
from app.modules.stories.models import KIND_PHRASAL_VERB
from app.modules.audio.composer.density import (
    PHASE_WEIGHTS,
    PROGRESSIONS,
    check_progression,
    phase_of,
    phase_percent,
    pick_evenly,
    pick_increasing,
)


def tercos(total):
    return [phase_of(i, total) for i in range(total)]


def por_terco(fases, escolhidos):
    return [sum(1 for i in escolhidos if fases[i] == terco) for terco in range(len(PHASE_WEIGHTS))]


def test_a_historia_e_dividida_em_tercos_pela_posicao():
    assert tercos(9) == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert tercos(10) == [0, 0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert tercos(1) == [0]


def test_pesos_dos_tercos_tem_media_de_100_por_cento():
    assert PHASE_WEIGHTS == (50, 100, 150)
    assert sum(PHASE_WEIGHTS) / len(PHASE_WEIGHTS) == 100


def test_fracao_de_cada_terco_em_centesimos_de_ponto_percentual():
    assert [phase_percent("medium", t) for t in range(3)] == [1750, 3500, 5250]


@pytest.mark.parametrize("densidade", ["low", "medium", "high"])
def test_a_curva_e_crescente_do_inicio_ao_fim(densidade):
    fases = tercos(60)
    inicio, meio, fim = por_terco(fases, pick_increasing(fases, densidade))
    assert inicio < meio < fim


@pytest.mark.parametrize("densidade", ["low", "medium", "high"])
def test_o_total_fica_perto_do_da_densidade_constante(densidade):
    fases = tercos(60)
    assert abs(len(pick_increasing(fases, densidade)) - len(pick_evenly(60, densidade))) <= 2


def test_valores_exatos_espelhados_no_front():
    fases = tercos(30)
    assert pick_increasing(fases, "low") == [5, 12, 17, 22, 27]
    assert por_terco(fases, pick_increasing(fases, "medium")) == [2, 4, 5]
    assert por_terco(fases, pick_increasing(fases, "high")) == [3, 6, 9]


def test_e_deterministica():
    fases = tercos(45)
    assert pick_increasing(fases, "high") == pick_increasing(list(fases), "high")


def test_troca_pelo_menos_um_quando_ha_candidatos():
    # poucos candidatos: nenhum terço chega a uma troca; vale o do meio do último terço com candidatos
    assert pick_increasing([0, 0, 1], "low") == [2]
    assert pick_increasing([2], "low") == [0]
    assert pick_increasing([], "high") == []


def test_densidade_invalida_falha_mesmo_sem_candidatos():
    with pytest.raises(ValueError, match="densidade desconhecida"):
        pick_increasing([], "extreme")


# ---------- integração com o AudioComposer (#112) ----------

@dataclass
class Anot:
    id: int
    kind: str = KIND_PHRASAL_VERB
    en_start: int = 0
    en_end: int = 1
    en_text: str = "x"
    pt_start: int | None = 0
    pt_end: int | None = 1
    pt_text: str | None = "y"
    extra: dict = field(default_factory=dict)


@dataclass
class Frase:
    id: int
    position: int
    annotations: list


def historia(n_frases=30):
    """Uma frase por anotação: o terço da anotação é o terço da sua frase."""
    return [Frase(i + 1, i, [Anot(i + 1)]) for i in range(n_frases)]


def test_composer_aplica_a_curva_por_terco_da_historia():
    frases = historia(30)
    selecionadas = AudioComposer().select_swaps(frases, ["phrasal_verbs"], "medium", progression="increasing")
    inicio, meio, fim = (len([i for i in selecionadas if t * 10 < i <= (t + 1) * 10]) for t in range(3))
    assert (inicio, meio, fim) == (2, 4, 5)


def test_composer_sem_progressao_ou_constante_e_igual_a_de_antes():
    frases = historia(30)
    composer = AudioComposer()
    antes = composer.select_swaps(frases, ["phrasal_verbs"], "medium")
    assert composer.select_swaps(frases, ["phrasal_verbs"], "medium", progression="constant") == antes
    assert composer.select_swaps(frases, ["phrasal_verbs"], "medium", progression="increasing") != antes


def test_o_terco_e_o_da_frase_mesmo_fora_de_ordem():
    frases = historia(9)
    composer = AudioComposer()
    esperado = composer.select_swaps(frases, ["phrasal_verbs"], "high", progression="increasing")
    assert composer.select_swaps(list(reversed(frases)), ["phrasal_verbs"], "high", progression="increasing") == esperado


def test_composer_recusa_progressao_desconhecida():
    with pytest.raises(ValueError, match="progressão desconhecida"):
        AudioComposer().select_swaps(historia(3), ["phrasal_verbs"], "high", progression="zigzag")


def test_progressao_ausente_e_constante_e_desconhecida_falha():
    assert check_progression(None) == "constant"
    assert set(PROGRESSIONS) == {"constant", "increasing"}
    with pytest.raises(ValueError, match="progressão desconhecida"):
        check_progression("decreasing")
