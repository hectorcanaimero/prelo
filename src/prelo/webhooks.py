"""Webhook de GitHub: el merge o cierre del PR del blog reanuda el post pausado en `pr_blog`."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response

PREFIJO = "prelo/"


def criar_router(secreto: str, *, retomar: Callable[[str, str], None]) -> APIRouter:
    """`retomar(post_id, decisao)` llega inyectado; `secreto` es `GITHUB_WEBHOOK_SECRET`."""
    router = APIRouter()
    # ponytail: en memoria, se pierde al reiniciar; un reenvío posterior llegaría al grafo, que ya no está pausado
    hechos: set[tuple[str, str]] = set()

    @router.post("/webhooks/github", status_code=204)
    async def github(request: Request) -> Response:
        cuerpo = await request.body()
        esperada = "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
        recibida = request.headers.get("X-Hub-Signature-256", "")
        # sin secreto configurado nada es válido; compare_digest evita filtrar la firma por tiempos
        if not secreto or not hmac.compare_digest(recibida.encode(), esperada.encode()):
            raise HTTPException(status_code=401, detail="firma inválida")
        if request.headers.get("X-GitHub-Event") != "pull_request":
            return Response(status_code=204)
        try:
            datos = json.loads(cuerpo)
            pr = datos["pull_request"]
            rama = pr["head"]["ref"]
            cerrado = datos["action"] == "closed"
        except (ValueError, KeyError, TypeError):
            return Response(status_code=204)
        if not cerrado or not isinstance(rama, str) or not rama.startswith(PREFIJO):
            return Response(status_code=204)
        clave = (rama.removeprefix(PREFIJO), "aprovado" if pr.get("merged") else "descartar")
        if clave not in hechos:
            retomar(*clave)  # si falla no se marca: el reintento de GitHub podrá reanudar
            hechos.add(clave)
        return Response(status_code=204)

    return router
