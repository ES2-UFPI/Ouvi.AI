"""Regra de densidade: quantos dos trechos candidatos da história são trocados de idioma.

A densidade vale para a HISTÓRIA INTEIRA (e não por frase) e a escolha é determinística: o mesmo pedido
gera sempre a mesma seleção. Isso é exigência do cache de áudio (US08): sem determinismo o SSML mudaria
a cada geração e nenhum áudio seria reaproveitado.
"""
from collections.abc import Sequence
from decimal import Decimal

# Fração dos candidatos da história que é trocada. Constantes nomeadas e fáceis de ajustar.
DENSITY_SHARE: dict[str, float] = {
    "low": 0.15,
    "medium": 0.35,
    "high": 0.60,
}


def share_of(density: str) -> float:
    try:
        return DENSITY_SHARE[density]
    except KeyError:
        valid = ", ".join(DENSITY_SHARE)
        raise ValueError(f"densidade desconhecida: {density!r}. Valores válidos: {valid}") from None


def pick_evenly(total: int, density: str) -> list[int]:
    """Índices (de 0 a total - 1) dos candidatos que serão trocados, espaçados de forma regular.

    A quantidade é a fração da densidade arredondada para cima na metade (no mínimo 1, se houver candidatos).
    Os escolhidos ficam no meio de `quantidade` faixas iguais da história: o 1º, o 4º, o 7º... e nunca
    todos colados no começo.
    """
    share = share_of(density)  # valida a densidade mesmo quando não há candidatos
    if total == 0:
        return []
    # Decimal: 0,15 x 10 dá exatamente 1,5 (e arredonda para 2), sem erro de ponto flutuante
    quantity = int(Decimal(str(share)) * total + Decimal("0.5"))
    quantity = min(total, max(1, quantity))
    return [(2 * i + 1) * total // (2 * quantity) for i in range(quantity)]


def percent_of(density: str) -> int:
    """A densidade em pontos percentuais inteiros (0,35 -> 35): as contas da curva usam só inteiros."""
    return int(Decimal(str(share_of(density))) * 100)


# ---------- curva de densidade crescente (US11, Cenário C) ----------
# `fixed`: a mesma fração do começo ao fim (Cenários A e B, regra acima).
# `increasing`: a fração SOBE ao longo da história. A densidade do filtro passa a ser a densidade FINAL.
PROGRESSION_FIXED = "fixed"
PROGRESSION_INCREASING = "increasing"
PROGRESSIONS = (PROGRESSION_FIXED, PROGRESSION_INCREASING)

# A curva é uma reta: começa em 1/5 da densidade final e chega a ela no fim da história
CURVE_START_FIFTHS = 1


def check_progression(progression: str | None) -> str:
    """A progressão do filtro (ausente = fixa). Levanta ValueError se for desconhecida."""
    progression = progression or PROGRESSION_FIXED
    if progression not in PROGRESSIONS:
        valid = ", ".join(PROGRESSIONS)
        raise ValueError(f"progressão desconhecida: {progression!r}. Valores válidos: {valid}")
    return progression


class DensityCurve:
    """Fração-alvo de trocas pela posição na história, e a seleção que segue essa curva.

    A frase `i` de uma história com `n` frases fica na posição relativa `x = (i + 0,5) / n` (o meio dela,
    entre 0 e 1) e tem fração-alvo `final * (1 + 4x) / 5`: 20% da densidade final no começo, subindo em
    linha reta até a densidade final. A curva nunca decresce e nunca passa da densidade escolhida.

    Toda a conta é feita com inteiros (numerador sobre `1000 * n`), para o front chegar exatamente ao
    mesmo resultado (frontend/src/features/player/swaps.ts).
    """

    def __init__(self, density: str) -> None:
        self.density = density
        self.percent = percent_of(density)

    def target(self, position: float) -> float:
        """Fração-alvo (0 a 1) na posição relativa `position` (0 = começo, 1 = fim)."""
        start = CURVE_START_FIFTHS / 5
        return self.percent / 100 * (start + (1 - start) * position)

    @staticmethod
    def denominator(total: int) -> int:
        return 1000 * total

    def numerator(self, index: int, total: int) -> int:
        """Fração-alvo da frase `index` (de `total`) = numerator / denominator(total)."""
        # percent/100 * (1 + 4 * (2i + 1) / 2n) / 5  =  percent * (2n + 8i + 4) / (1000n)
        return self.percent * (2 * total + 8 * index + 4)

    def sentence_target(self, index: int, total: int) -> float:
        return self.numerator(index, total) / self.denominator(total)

    def select(self, sentence_indices: Sequence[int], total: int) -> list[int]:
        """Índices dos candidatos trocados. `sentence_indices[k]` é a frase (0 a total - 1) do candidato k,
        em ordem de aparição.

        Método do acumulador: cada candidato soma a fração-alvo da sua frase; sempre que o acumulado passa
        de uma troca inteira, o candidato é trocado. O acumulador começa em meia troca, então o número de
        trocas até qualquer ponto da história é a soma da curva até ali, ARREDONDADA (diferença de no máximo
        meia troca). É exato e determinístico, e espalha as trocas sem amontoar.
        """
        if not sentence_indices:
            return []
        whole = self.denominator(total)
        accumulator = whole // 2
        chosen: list[int] = []
        for k, index in enumerate(sentence_indices):
            accumulator += self.numerator(index, total)
            if accumulator >= whole:  # a fração-alvo é sempre < 1: no máximo uma troca por candidato
                chosen.append(k)
                accumulator -= whole
        return chosen


def sentence_target(density: str, progression: str | None, index: int, total: int) -> float:
    """Fração-alvo de trocas da frase `index` (de `total`): a da curva, ou a densidade fixa."""
    if check_progression(progression) == PROGRESSION_INCREASING:
        return DensityCurve(density).sentence_target(index, total)
    return share_of(density)


