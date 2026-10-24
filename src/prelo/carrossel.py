"""Plantillas HTML del carrusel de Instagram → PNG 1080×1350 con Playwright (D5)."""

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

PLANTILLAS = Path(__file__).resolve().parents[2] / "templates" / "carrossel"
ANCHO, ALTO = 1080, 1350


def _rellenar(nombre: str, valores: dict[str, str]) -> str:
    valores = {"css": (PLANTILLAS / "_base.css").read_text(), **valores}
    # una sola pasada: un valor que contenga «{{x}}» no se vuelve a expandir
    return re.sub(r"\{\{(\w+)\}\}", lambda m: valores[m[1]], (PLANTILLAS / f"{nombre}.html").read_text())


def html_laminas(laminas: list[dict], blog_url: str) -> list[str]:
    """Una página HTML por lámina: la primera es portada, la última cierre (con el link al blog)."""
    total = len(laminas)
    htmls = []
    for i, lam in enumerate(laminas, 1):
        nombre = "portada" if i == 1 else "cierre" if i == total else "lamina"
        htmls.append(
            _rellenar(
                nombre,
                {
                    "titulo": escape(lam.get("titulo", "")),
                    "texto": escape(lam.get("texto", "")),
                    # va dentro de url('...') en un atributo style: las comillas se codifican
                    "imagem_url": escape(quote(lam.get("imagem_url", ""), safe=":/?&=%#@+,;~")),
                    "n": str(i),
                    "total": str(total),
                    "blog_url": escape(blog_url),
                },
            )
        )
    return htmls


def renderizar(laminas: list[dict], blog_url: str) -> list[bytes]:
    """PNG 1080×1350 por lámina. Lanza error de Playwright si Chromium no está instalado."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            pagina = navegador.new_page(viewport={"width": ANCHO, "height": ALTO})
            pngs = []
            for html in html_laminas(laminas, blog_url):
                pagina.set_content(html, wait_until="load")
                pngs.append(pagina.screenshot(type="png"))
            return pngs
        finally:
            navegador.close()
