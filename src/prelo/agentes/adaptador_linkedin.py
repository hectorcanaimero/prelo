"""Adaptador de LinkedIn: convierte la pieza madre en un post en pt-BR."""

from __future__ import annotations

import re
from typing import Any

from prelo.interfaces import Modelo, Texto

PROMPT = """Adapta esta pieza a un post de LinkedIn en português do Brasil (pt-BR), en primera persona, como Héctor.
{link}

Reglas del post:
- Una sola idea central, con opinión o experiencia propia: no resumas la pieza ni la documentación.
- Abre con la frase más fuerte de la idea y termina con una pregunta que invite a comentar.
- Texto plano: LinkedIn no muestra markdown (nada de **negritas**, # títulos ni listas con viñetas o emojis).
{reglas}
Título: {titulo}
Resumen: {resumo}
Cuerpo:
{corpo}
{feedback}
Responde solo con el texto del post."""


def _reglas(formato: dict[str, int]) -> str:
    linhas = []
    if "max_palavras" in formato:
        linhas.append(f"- Máximo {formato['max_palavras']} palabras, sin contar hashtags.")
    if "max_emojis" in formato:
        linhas.append(f"- Como mucho {formato['max_emojis']} emojis en todo el post.")
    if "hashtags" in formato:
        linhas.append(f"- Exactamente {formato['hashtags']} hashtags, al final.")
    return "\n".join(linhas) + "\n" if linhas else ""


def _sin_markdown(texto: str) -> str:
    # LinkedIn mostraría los asteriscos tal cual: negritas/cursivas y títulos fuera, conservando el texto.
    texto = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), texto)
    return re.sub(r"^#{1,6}\s+", "", texto, flags=re.MULTILINE)


def adaptador_linkedin(
    modelo: Modelo,
    texto: Texto,
    url_blog: str | None,
    feedback: str | None = None,
    *,
    post_id: str,
    formato: dict[str, int] | None = None,
) -> dict[str, Any]:
    link = f"Termina el post con este link: {url_blog}" if url_blog else "No incluyas ningún link ni URL."
    fb = f"\nCorrige según este feedback:\n{feedback}\n" if feedback else ""
    prompt = PROMPT.format(link=link, feedback=fb, reglas=_reglas(formato or {}), **texto)
    post = _sin_markdown(modelo.gerar(prompt, agente="adaptador_linkedin", post_id=post_id).strip())
    if url_blog and url_blog not in post:  # FR-11: el link siempre sale
        post += f"\n\n{url_blog}"
    return {"pt": Texto(titulo="", resumo="", corpo=post)}
