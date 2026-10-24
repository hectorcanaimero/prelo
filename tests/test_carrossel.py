import struct

import pytest

from prelo.carrossel import html_laminas, renderizar

LAMINAS = [
    {"titulo": "Portada", "texto": "", "imagem_url": ""},
    {"titulo": "Punto <script>alert(1)</script>", "texto": "Texto & más", "imagem_url": ""},
    {"titulo": "Cierre", "texto": "Gracias", "imagem_url": ""},
]
BLOG = "https://blog.example/post"


def test_script_escapado():
    html = html_laminas(LAMINAS, BLOG)[1]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_n_total():
    assert "2/3" in html_laminas(LAMINAS, BLOG)[1]


def test_ultima_lleva_link_al_blog():
    htmls = html_laminas(LAMINAS, BLOG)
    assert BLOG in htmls[-1]
    assert BLOG not in htmls[0] and BLOG not in htmls[1]


def test_plantillas_sin_internet():
    for h in html_laminas(LAMINAS, BLOG):
        assert "http://" not in h and "https://" not in h.replace(BLOG, "")


def test_imagem_url_no_rompe_el_atributo():
    html = html_laminas([{"titulo": "x", "imagem_url": "https://i.example/a.png');\" onload=\"x"}], BLOG)[0]
    assert 'onload="x' not in html


def test_tres_png_1080x1350():
    try:
        pngs = renderizar(LAMINAS, BLOG)
    except Exception as e:  # Chromium no instalado
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium no instalado")
        raise
    assert len(pngs) == 3
    for p in pngs:
        assert p[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", p[16:24]) == (1080, 1350)
