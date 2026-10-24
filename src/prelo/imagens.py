"""Imagen de fondo del carrusel con cualquier modelo de imagen de FAL (D14), con costo en `custos`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from prelo.interfaces import Custo, Repositorio

FAL_URL = "https://fal.run/"
MODELO_IMAGEN = "fal-ai/flux/schnell"
# ponytail: precio fijo por imagen y configurable; FAL no lo devuelve en la respuesta, ajustar al cambiar de modelo.
USD_POR_IMAGEN = Decimal("0.003")
SIN_TEXTO = " Do not include any text, letters or numbers anywhere in the image."


def gerar_imagem(
    prompt: str,
    *,
    post_id: str,
    http: Any,
    fal_key: str,
    repo: Repositorio,
    modelo: str = MODELO_IMAGEN,
    usd: Decimal = USD_POR_IMAGEN,
) -> bytes:
    """`http` es un `httpx.Client`. Los modelos de imagen de FAL aceptan `prompt` y devuelven `images[0].url`."""
    try:
        resp = http.post(
            FAL_URL + modelo,
            headers={"Authorization": f"Key {fal_key}"},
            json={"prompt": prompt + SIN_TEXTO, "image_size": "square_hd", "num_images": 1},
            timeout=120,
        )
        resp.raise_for_status()
        imagen = http.get(resp.json()["images"][0]["url"], timeout=60)
        imagen.raise_for_status()
        dados = imagen.content
    except Exception as e:
        # Sin `str(e)`: un error de httpx puede incluir la petición, y con ella la cabecera con la clave.
        raise RuntimeError(
            f"fallo la generación de imagen: post_id={post_id} modelo={modelo}: {type(e).__name__}"
        ) from e
    repo.registrar_custo(Custo(post_id, "imagem", modelo, 0, 0, usd, datetime.now(UTC)))
    return dados
