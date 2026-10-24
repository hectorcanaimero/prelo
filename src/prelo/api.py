"""API HTTP de Prelo: salud y entrada de Hermes (D15). No hay ningún endpoint que apruebe."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, StringConstraints

from prelo.config import Settings


class NuevoPost(BaseModel):
    tema: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def criar_api(settings: Settings, *, iniciar: Callable[[str], str], ping: Callable[[], object]) -> FastAPI:
    """`iniciar(tema) -> post_id` y `ping()` (levanta si la base no responde) llegan inyectados."""
    api = FastAPI(title="Prelo")
    token = settings.PRELO_API_TOKEN.get_secret_value().encode()

    @api.get("/saude")
    def saude(response: Response) -> dict[str, str]:
        try:
            ping()
        except Exception:  # noqa: BLE001 - cualquier fallo de la base es 503
            response.status_code = 503
            return {"status": "sin_base"}
        return {"status": "ok"}

    # Síncrono a propósito: FastAPI lo corre en un hilo y `iniciar` bloquea hasta la primera pausa del grafo.
    @api.post("/posts", status_code=202)
    def posts(body: NuevoPost, authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
        esquema, _, recibido = (authorization or "").partition(" ")
        # sin token configurado nada es válido; compare_digest evita filtrar el token por tiempos
        if not token or esquema.lower() != "bearer" or not hmac.compare_digest(recibido.encode(), token):
            raise HTTPException(status_code=401, detail="token inválido")
        return {"post_id": iniciar(body.tema)}

    return api
