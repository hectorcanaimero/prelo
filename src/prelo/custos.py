"""Tabla de precios y calculo de USD por llamada (FR-16)."""

from __future__ import annotations

import logging
from decimal import Decimal

log = logging.getLogger(__name__)

# modelo -> (USD por millon de tokens de entrada, de salida). PRELO_PRECIOS suma o pisa entradas sin tocar código.
PRECIOS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5-5": (Decimal(3), Decimal(15)),
    "claude-haiku-5-5": (Decimal(1), Decimal(5)),
}
_sin_precio: set[str] = set()


def cargar_precios(texto: str) -> None:
    """`"gpt-6-luna=1.25/10,gemini-4-argon-trial=2/12"` (USD por millón, entrada/salida) -> `PRECIOS`."""
    for item in texto.split(","):
        modelo, _, precio = item.partition("=")
        entrada, _, saida = precio.partition("/")
        if modelo.strip() and entrada.strip() and saida.strip():
            PRECIOS[modelo.strip()] = (Decimal(entrada.strip()), Decimal(saida.strip()))


def calcular_usd(modelo: str, tokens_entrada: int, tokens_saida: int) -> Decimal:
    # ponytail: un modelo sin precio cuenta USD 0 (por suscripción vía 9router no se paga por token);
    # para ver su equivalente API, sumarlo a PRELO_PRECIOS.
    precio = PRECIOS.get(modelo.rsplit("/", 1)[-1])
    if precio is None:
        if modelo not in _sin_precio:  # un aviso por modelo, no uno por llamada
            _sin_precio.add(modelo)
            log.warning("modelo sin precio (se cuenta USD 0; se agrega en PRELO_PRECIOS): %s", modelo)
        return Decimal(0)
    pin, pout = precio
    return (Decimal(tokens_entrada) * pin + Decimal(tokens_saida) * pout) / Decimal(1_000_000)
