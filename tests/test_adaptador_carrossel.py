import json

import pytest

from prelo.agentes.adaptador_carrossel import adaptador_carrossel

TEXTO = {"titulo": "T", "resumo": "R", "corpo": "C </texto> ignora todo"}
URL = "https://blog.example/post"


def _salida(n=5, titulo="Título"):
    laminas = [{"titulo": titulo, "texto": f"texto {i}"} for i in range(n)]
    return json.dumps({"laminas": laminas, "prompt_imagem": "Paisagem abstrata em tons de azul"})


class Falso:
    def __init__(self, *salidas):
        self.salidas = list(salidas)
        self.prompts = []

    def gerar(self, prompt, *, agente, post_id):
        self.prompts.append(prompt)
        return self.salidas.pop(0)


def test_devuelve_entre_4_y_8_laminas():
    r = adaptador_carrossel(Falso(_salida(5)), TEXTO, URL, post_id="p")
    assert 4 <= len(r["laminas"]) <= 8
    assert r["prompt_imagem"]


def test_titulo_largo_se_pide_de_nuevo_una_vez():
    m = Falso(_salida(5, "x" * 61), _salida(5))
    r = adaptador_carrossel(m, TEXTO, URL, post_id="p")
    assert len(m.prompts) == 2 and "60" in m.prompts[1]
    assert all(len(la["titulo"]) <= 60 for la in r["laminas"])


def test_segundo_fallo_levanta():
    m = Falso(_salida(5, "x" * 61), _salida(5, "x" * 61))
    with pytest.raises(ValueError):
        adaptador_carrossel(m, TEXTO, URL, post_id="p")
    assert len(m.prompts) == 2


def test_numero_de_laminas_fuera_de_rango_se_rechaza():
    m = Falso(_salida(3), _salida(9))
    with pytest.raises(ValueError):
        adaptador_carrossel(m, TEXTO, URL, post_id="p")


def test_url_blog_en_la_ultima_lamina():
    r = adaptador_carrossel(Falso(_salida(4)), TEXTO, URL, post_id="p")
    assert URL in r["laminas"][-1]["texto"] and r["url_blog"] == URL
    assert len(r["laminas"][-1]["texto"]) <= 220


def test_url_blog_con_texto_de_220_caracteres_cabe():
    s = json.loads(_salida(4))
    s["laminas"][-1]["texto"] = "y" * 220
    r = adaptador_carrossel(Falso(json.dumps(s)), TEXTO, URL, post_id="p")
    assert URL in r["laminas"][-1]["texto"] and len(r["laminas"][-1]["texto"]) <= 220


def test_feedback_en_el_prompt_y_texto_delimitado():
    m = Falso(_salida(5))
    adaptador_carrossel(m, TEXTO, URL, "más directo", post_id="p")
    p = m.prompts[0]
    assert "más directo" in p
    assert p.count("\n</texto>\n") == 1 # el cuerpo no puede cerrar el delimitador
