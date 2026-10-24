"""`EstadoPost`: el estado de trabajo que viaja por el grafo.

Vive aparte de `prelo.interfaces` segun docs/arch/001-prelo.md -> Interfaces.
Las tablas de Postgres son el registro persistente; `EstadoPost` es solo
el estado del nodo actual del `StateGraph`.
"""

from __future__ import annotations

from typing import Any, TypedDict

from prelo.interfaces import Decisao, Fonte, Texto, Violacao


class EstadoPost(TypedDict):
    """Estado del grafo. `thread_id == post_id`, asi un post puede esperar dias (FR-8)."""

    post_id: str
    tema: str
    fontes: list[Fonte]
    # Idiomas de la pieza madre: "es" en F1, "es" | "pt" | "en" desde F2.
    rascunho: dict[str, Texto]
    # canal -> contenido del canal (shape libre por canal).
    derivados: dict[str, dict[str, Any]]
    violacoes: list[Violacao]
    tentativas: int
    decisao: Decisao | None
    comentario: str | None
    url_blog: str | None


__all__ = ["EstadoPost"]
