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


# ---------- curva de densidade crescente (US11) ----------
# Com a progressão `increasing`, a história é dividida em terços (pela posição das frases) e cada terço
# troca uma fração diferente dos seus candidatos: metade da densidade no início, a densidade escolhida no
# meio e uma vez e meia no fim. A média dos pesos é 100%, então o total de trocas fica perto do da
# densidade constante; o que muda é ONDE elas caem: poucas no começo, muitas no final.
PROGRESSION_CONSTANT = "constant"
PROGRESSION_INCREASING = "increasing"
PROGRESSIONS = (PROGRESSION_CONSTANT, PROGRESSION_INCREASING)

# Peso de cada terço da história, em porcentagem da densidade: início, meio e fim
PHASE_WEIGHTS: tuple[int, ...] = (50, 100, 150)
PHASES = len(PHASE_WEIGHTS)


def check_progression(progression: str | None) -> str:
    """A progressão do filtro (ausente = constante). Levanta ValueError se for desconhecida."""
    progression = progression or PROGRESSION_CONSTANT
    if progression not in PROGRESSIONS:
        valid = ", ".join(PROGRESSIONS)
        raise ValueError(f"progressão desconhecida: {progression!r}. Valores válidos: {valid}")
    return progression


def phase_of(index: int, total: int) -> int:
    """Terço da história (0 = início, 1 = meio, 2 = fim) da frase de índice `index` entre `total` frases."""
    return PHASES * index // total


def phase_percent(density: str, phase: int) -> int:
    """Fração trocada no terço, em centésimos de ponto percentual (ex.: média no fim = 5250 = 52,5%)."""
    return int(Decimal(str(share_of(density))) * 100) * PHASE_WEIGHTS[phase]


def pick_increasing(phases: Sequence[int], density: str) -> list[int]:
    """Índices dos candidatos trocados com a densidade crescente. `phases[i]` é o terço do candidato i.

    Em cada terço, a quantidade é `densidade x peso do terço` (arredondada para cima na metade) e os
    escolhidos ficam espaçados de forma regular dentro do terço, com a mesma conta de `pick_evenly`. Como
    na densidade constante, há pelo menos uma troca se houver candidatos: a do meio do último terço.
    Só usa inteiros, para o front (player) chegar exatamente ao mesmo resultado.
    """
    share_of(density)  # valida a densidade mesmo quando não há candidatos
    chosen: list[int] = []
    for phase in range(PHASES):
        indices = [i for i, p in enumerate(phases) if p == phase]
        total = len(indices)
        quantity = min(total, (phase_percent(density, phase) * total + 5000) // 10000)
        chosen.extend(indices[(2 * i + 1) * total // (2 * quantity)] for i in range(quantity))
    if not chosen and phases:
        last = [i for i, p in enumerate(phases) if p == max(phases)]
        chosen = [last[len(last) // 2]]
    return sorted(chosen)
