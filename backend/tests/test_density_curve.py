"""Testes da curva de densidade crescente (US11, #111 e #115): poucas trocas no começo e muitas no final.

Além de casos fixos, há testes de PROPRIEDADES: em vez de conferir uma história, conferem as regras da curva
(não decresce, fica dentro dos limites, é determinística e o total bate com a soma da curva) em centenas de
histórias sintéticas, geradas com semente fixa (o resultado é sempre o mesmo, sem dependência nova).
Funções puras, sem banco; a mesma conta é espelhada no front (frontend/src/features/player/swaps.ts).
"""
import random
from dataclasses import dataclass, field

import pytest

from app.modules.audio.composer import AudioComposer, DensityCurve
from app.modules.audio.composer.density import (
    DENSITY_SHARE,
    PROGRESSIONS,
    check_progression,
    pick_evenly,
    sentence_target,
)
from app.modules.stories.models import KIND_PHRASAL_VERB

DENSIDADES = ["low", "medium", "high"]
SEMENTE = 2026


def historia_sintetica(rng: random.Random, frases: int, max_por_frase: int) -> list[int]:
    """Frase (0 a frases - 1) de cada candidato, em ordem de aparição: 0 a `max_por_frase` por frase."""
    return [i for i in range(frases) for _ in range(rng.randint(0, max_por_frase))]


def historias(quantidade: int, semente: int = SEMENTE):
    rng = random.Random(semente)
    for _ in range(quantidade):
        frases = rng.randint(1, 80)
        yield rng.choice(DENSIDADES), frases, historia_sintetica(rng, frases, rng.randint(0, 4))


def soma_da_curva(curva: DensityCurve, candidatos: list[int], frases: int) -> float:
    return sum(curva.sentence_target(i, frases) for i in candidatos)


def tercos(candidatos: list[int], escolhidos: list[int], frases: int) -> list[int]:
    contagem = [0, 0, 0]
    for k in escolhidos:
        contagem[3 * candidatos[k] // frases] += 1
    return contagem


# ---------- a curva (fração-alvo) ----------

@pytest.mark.parametrize("densidade", DENSIDADES)
def test_a_curva_nunca_decresce_e_respeita_os_extremos(densidade):
    curva = DensityCurve(densidade)
    final = DENSITY_SHARE[densidade]
    for frases in range(1, 120):
        alvos = [curva.sentence_target(i, frases) for i in range(frases)]
        assert alvos == sorted(alvos)  # não decrescente
        assert all(final / 5 <= alvo <= final for alvo in alvos)  # dentro dos limites
    assert curva.target(0) == pytest.approx(final / 5)
    assert curva.target(1) == pytest.approx(final)  # a densidade escolhida é a do FINAL da história


def test_a_curva_muda_com_a_densidade():
    assert DensityCurve("low").target(0.5) < DensityCurve("medium").target(0.5) < DensityCurve("high").target(0.5)


def test_fracao_alvo_da_frase_e_o_meio_dela_na_curva():
    curva = DensityCurve("medium")
    assert curva.sentence_target(0, 10) == pytest.approx(curva.target(0.05))
    assert curva.sentence_target(9, 10) == pytest.approx(curva.target(0.95))
    # densidade fixa: a mesma fração em toda a história
    assert sentence_target("medium", "fixed", 0, 10) == sentence_target("medium", None, 9, 10) == 0.35


# ---------- propriedades da seleção (pelo menos 100 histórias sintéticas) ----------

@pytest.mark.parametrize("densidade, frases, candidatos", list(historias(150)))
def test_propriedades_da_selecao(densidade, frases, candidatos):
    curva = DensityCurve(densidade)
    escolhidos = curva.select(candidatos, frases)

    # determinística: a mesma história e o mesmo filtro dão sempre a mesma seleção
    assert escolhidos == curva.select(list(candidatos), frases)
    # dentro dos limites: índices válidos, sem repetição, em ordem
    assert escolhidos == sorted(set(escolhidos)) and all(0 <= k < len(candidatos) for k in escolhidos)
    # o total bate com a soma da curva (diferença de no máximo 1; pelo acumulador, no máximo meia troca)
    assert abs(len(escolhidos) - soma_da_curva(curva, candidatos, frases)) <= 0.5 + 1e-9
    # e não só no total: até qualquer ponto da história, as trocas acompanham a curva
    escolhidos_set = set(escolhidos)
    acumulado = 0.0
    trocas = 0
    for k, frase in enumerate(candidatos):
        acumulado += curva.sentence_target(frase, frases)
        trocas += k in escolhidos_set
        assert abs(trocas - acumulado) <= 0.5 + 1e-9


def historias_uniformes(quantidade: int):
    """Histórias com o mesmo número de candidatos por frase e candidatos suficientes para a curva aparecer."""
    rng = random.Random(SEMENTE + 1)
    for _ in range(quantidade):
        por_frase = rng.randint(1, 3)
        frases = rng.randint(-(-80 // por_frase), 90)  # pelo menos 80 candidatos
        yield rng.choice(DENSIDADES), frases, [i for i in range(frases) for _ in range(por_frase)]


@pytest.mark.parametrize("densidade, frases, candidatos", list(historias_uniformes(100)))
def test_trocas_por_terco_nunca_decrescem_e_o_final_tem_mais_que_o_inicio(densidade, frases, candidatos):
    inicio, meio, fim = tercos(candidatos, DensityCurve(densidade).select(candidatos, frases), frases)
    assert inicio <= meio <= fim
    assert fim > inicio


def test_valores_exatos_espelhados_no_front():
    # 30 frases com um candidato cada: os mesmos números estão em swaps.test.ts
    candidatos = list(range(30))
    assert DensityCurve("low").select(candidatos, 30) == [9, 20, 28]
    assert DensityCurve("medium").select(candidatos, 30) == [5, 11, 16, 20, 24, 27]
    assert tercos(candidatos, DensityCurve("high").select(candidatos, 30), 30) == [2, 4, 5]


# ---------- casos-limite ----------

@pytest.mark.parametrize("frases", [1, 2, 3])
@pytest.mark.parametrize("densidade", DENSIDADES)
def test_historias_muito_curtas_nao_geram_erro(frases, densidade):
    curva = DensityCurve(densidade)
    for por_frase in range(0, 4):
        candidatos = [i for i in range(frases) for _ in range(por_frase)]
        escolhidos = curva.select(candidatos, frases)
        assert abs(len(escolhidos) - soma_da_curva(curva, candidatos, frases)) <= 0.5 + 1e-9


def test_sem_candidatos_nao_troca_nada():
    assert DensityCurve("high").select([], 10) == []


def test_densidade_invalida_falha():
    with pytest.raises(ValueError, match="densidade desconhecida"):
        DensityCurve("extreme")


def test_progressao_ausente_e_fixa_e_desconhecida_falha():
    assert check_progression(None) == "fixed"
    assert set(PROGRESSIONS) == {"fixed", "increasing"}
    with pytest.raises(ValueError, match="progressão desconhecida"):
        check_progression("decreasing")


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
    """Uma frase por anotação, com o mesmo id."""
    return [Frase(i + 1, i, [Anot(i + 1)]) for i in range(n_frases)]


def test_composer_aplica_a_curva_pela_posicao_das_frases():
    selecionadas = AudioComposer().select_swaps(historia(30), ["phrasal_verbs"], "medium", progression="increasing")
    assert sorted(selecionadas) == [i + 1 for i in DensityCurve("medium").select(list(range(30)), 30)]


def test_composer_sem_progressao_ou_fixa_e_igual_a_de_antes():
    composer = AudioComposer()
    antes = composer.select_swaps(historia(30), ["phrasal_verbs"], "medium")
    assert sorted(antes) == [i + 1 for i in pick_evenly(30, "medium")]
    assert composer.select_swaps(historia(30), ["phrasal_verbs"], "medium", progression="fixed") == antes
    assert composer.select_swaps(historia(30), ["phrasal_verbs"], "medium", progression="increasing") != antes


def test_a_posicao_e_a_da_frase_mesmo_recebendo_fora_de_ordem():
    composer = AudioComposer()
    esperado = composer.select_swaps(historia(9), ["phrasal_verbs"], "high", progression="increasing")
    assert composer.select_swaps(list(reversed(historia(9))), ["phrasal_verbs"], "high", progression="increasing") == esperado


def test_composer_recusa_progressao_desconhecida():
    with pytest.raises(ValueError, match="progressão desconhecida"):
        AudioComposer().select_swaps(historia(3), ["phrasal_verbs"], "high", progression="zigzag")


def test_perfil_de_densidade_por_frase():
    frases = historia(10)
    perfil = AudioComposer().density_profile(
        frases, {1: 0, 10: 1}, ["phrasal_verbs"], "high", progression="increasing"
    )
    assert [p.position for p in perfil] == list(range(10))
    assert all(p.candidates == 1 for p in perfil)
    assert [p.swapped for p in perfil] == [0] * 9 + [1]
    alvos = [p.target for p in perfil]
    assert alvos == sorted(alvos) and alvos[0] < alvos[-1] <= 0.60
