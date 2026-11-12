"""Regra de densidade: quantos dos trechos candidatos da história são trocados de idioma.

A densidade vale para a HISTÓRIA INTEIRA (e não por frase) e a escolha é determinística: o mesmo pedido
gera sempre a mesma seleção. Isso é exigência do cache de áudio (US08): sem determinismo o SSML mudaria
a cada geração e nenhum áudio seria reaproveitado.
"""
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
