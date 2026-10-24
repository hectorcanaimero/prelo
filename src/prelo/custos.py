"""Tabla de precios y calculo de USD por llamada (FR-16)."""

from __future__ import annotations

from decimal import Decimal

# modelo -> (USD por millon de tokens de entrada, de salida). Ajustar al precio vigente.
PRECIOS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5-5": (Decimal(3), Decimal(15)),
    "claude-haiku-5-5": (Decimal(1), Decimal(5)),
}


def calcular_usd(modelo: str, tokens_entrada: int, tokens_saida: int) -> Decimal:
    pin, pout = PRECIOS[modelo]
    return (Decimal(tokens_entrada) * pin + Decimal(tokens_saida) * pout) / Decimal(1_000_000)
