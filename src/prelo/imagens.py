"""Imagen de fondo del carrusel sobre gpt-image-1 (D14), con costo en `custos`."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from prelo.interfaces import Custo, Repositorio

MODELO_IMAGEN = "gpt-image-1"
# ponytail: precio fijo por imagen (1024x1024, calidad media); leer `usage` si se cambia calidad/tamaño.
USD_POR_IMAGEN = Decimal("0.042")
SIN_TEXTO = " Do not include any text, letters or numbers anywhere in the image."


def gerar_imagem(prompt: str, *, post_id: str, openai: Any, repo: Repositorio) -> bytes:
    try:
        resp = openai.images.generate(
            model=MODELO_IMAGEN, prompt=prompt + SIN_TEXTO, size="1024x1024", quality="medium"
        )
        dados = base64.b64decode(resp.data[0].b64_json)
    except Exception as e:
        raise RuntimeError(f"fallo la generación de imagen: post_id={post_id}: {type(e).__name__}") from e
    repo.registrar_custo(Custo(post_id, "imagem", MODELO_IMAGEN, 0, 0, USD_POR_IMAGEN, datetime.now(UTC)))
    return dados
