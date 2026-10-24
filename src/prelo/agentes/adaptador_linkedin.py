"""Adaptador de LinkedIn: convierte la pieza madre en un post en pt-BR."""

from __future__ import annotations

from typing import Any

from prelo.interfaces import Modelo, Texto

PROMPT = """Adapta esta pieza a un post de LinkedIn en português do Brasil (pt-BR), tono profesional y breve.
{link}

Título: {titulo}
Resumen: {resumo}
Cuerpo:
{corpo}
{feedback}
Responde solo con el texto del post."""


def adaptador_linkedin(
    modelo: Modelo, texto: Texto, url_blog: str | None, feedback: str | None = None, *, post_id: str
) -> dict[str, Any]:
    link = f"Termina el post con este link: {url_blog}" if url_blog else "No incluyas ningún link ni URL."
    fb = f"\nCorrige según este feedback:\n{feedback}\n" if feedback else ""
    prompt = PROMPT.format(link=link, feedback=fb, **texto)
    post = modelo.gerar(prompt, agente="adaptador_linkedin", post_id=post_id).strip()
    if url_blog and url_blog not in post:  # FR-11: el link siempre sale
        post += f"\n\n{url_blog}"
    return {"pt": Texto(titulo="", resumo="", corpo=post)}
