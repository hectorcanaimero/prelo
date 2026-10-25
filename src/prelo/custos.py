"""Tabla de precios y calculo de USD por llamada (FR-16)."""

from __future__ import annotations

import logging
from decimal import Decimal

log = logging.getLogger(__name__)

# modelo -> (USD por millon de tokens de entrada, de salida). Ajustar al precio vigente.
PRECIOS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5-5": (Decimal(3), Decimal(15)),
    "claude-haiku-5-5": (Decimal(1), Decimal(5)),
}


def calcular_usd(modelo: str, tokens_entrada: int, tokens_saida: int) -> Decimal:
    # ponytail: un modelo sin precio cuenta USD 0 (los de suscripción vía 9router no cobran por token);
    # sumarlo a PRECIOS cuando se pague por token.
    precio = PRECIOS.get(modelo.rsplit("/", 1)[-1])
    if precio is None:
        log.warning("modelo sin precio en PRECIOS, se cuenta USD 0: %s", modelo)
        return Decimal(0)
    pin, pout = precio
    return (Decimal(tokens_entrada) * pin + Decimal(tokens_saida) * pout) / Decimal(1_000_000)
