"""`EstadoPost`: el estado de trabajo que viaja por el grafo.

Vive aparte de `prelo.interfaces` segun docs/arch/001-prelo.md -> Interfaces.
Las tablas de Postgres son el registro persistente; `EstadoPost` es solo
el estado del nodo actual del `StateGraph`.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from prelo.interfaces import Decisao, Fonte, Texto, Violacao


def _unir(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class EstadoPost(TypedDict):
    """Estado del grafo. `thread_id == post_id`, asi un post puede esperar dias (FR-8)."""

    post_id: str
    tema: str
    fontes: list[Fonte]
    # Idiomas de la pieza madre: "es" en F1, "es" | "pt" | "en" desde F2.
    rascunho: dict[str, Texto]
    # canal -> contenido del canal (shape libre por canal).
    # Con reducer: linkedin e instagram corren en paralelo y cada uno escribe su canal.
    derivados: Annotated[dict[str, dict[str, Any]], _unir]
    violacoes: list[Violacao]
    tentativas: int
    decisao: Decisao | None
    comentario: str | None
    url_blog: str | None


__all__ = ["EstadoPost"]
