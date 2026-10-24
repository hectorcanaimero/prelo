"""Tests del tramo de blog (F2): traduzir → pr_blog ⏸ merge → esperar_deploy ⏸ URL → derivados."""

from __future__ import annotations

from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_grafo import Dobles, _pausado_en, _pecas

from prelo import grafo

URL_PR = "https://github.com/hectorcanaimero/site-guria/pull/1"
URL_BLOG = "https://guria.dev/blog/agentes"


class DoblesBlog(Dobles):
    """`Dobles` de F1 más `traduzir` y `abrir_pr`, y un adaptador de LinkedIn que guarda la `url_blog`."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.traducidos: list[dict] = []
        self.prs: list[tuple[str, dict]] = []
        self.urls_linkedin: list[str | None] = []

    def deps(self):
        base = super().deps()

        def traduzir(texto, *, post_id):
            self.traducidos.append(texto)
            return {"es": texto, **{i: {**texto, "corpo": f"{texto['corpo']} ({i})"} for i in ("pt", "en")}}

        def abrir_pr(post_id, textos):
            self.prs.append((post_id, textos))
            return URL_PR

        linkedin = base.adaptar["linkedin"]

        def adaptar_linkedin(texto, url_blog, feedback, *, post_id):
            self.urls_linkedin.append(url_blog)
            return linkedin(texto, url_blog, feedback, post_id=post_id)

        return replace(base, traduzir=traduzir, abrir_pr=abrir_pr, adaptar={"linkedin": adaptar_linkedin})


def _iniciar():
    d = DoblesBlog()
    g = grafo.construir(d.deps(), InMemorySaver())
    return d, g, grafo.iniciar(g, "agentes", "editor")


def test_tema_sin_violaciones_traduce_abre_pr_y_pausa_en_pr_blog():
    d, g, post_id = _iniciar()

    assert _pausado_en(g, post_id) == ("pr_blog",)
    assert d.traducidos == [{"titulo": "agentes", "resumo": "r", "corpo": "borrador 1"}]
    [(pr_post, textos)] = d.prs
    assert pr_post == post_id and set(textos) == {"es", "pt", "en"}
    [blog] = _pecas(d.repo, post_id)
    assert (blog.canal, blog.status, blog.conteudo) == ("blog", "pendente", textos)
    assert d.urls_linkedin == [] and d.notificadas == []


def test_merge_aprueba_la_pieza_blog_y_pausa_en_esperar_deploy():
    d, g, post_id = _iniciar()

    grafo.retomar(g, post_id, "aprovado")

    assert _pausado_en(g, post_id) == ("esperar_deploy",)
    [blog] = _pecas(d.repo, post_id)
    assert blog.decisao == "aprovado"
    assert d.urls_linkedin == []
    assert len(d.prs) == 1  # reanudar no reabre el PR


def test_deploy_con_url_genera_linkedin_con_url_blog():
    d, g, post_id = _iniciar()
    grafo.retomar(g, post_id, "aprovado")

    grafo.retomar(g, post_id, url_blog=URL_BLOG)

    assert d.urls_linkedin == [URL_BLOG]
    assert _pausado_en(g, post_id) == ("aprovar",)
    assert g.get_state({"configurable": {"thread_id": post_id}}).values["url_blog"] == URL_BLOG
    pecas = {p.canal: p for p in _pecas(d.repo, post_id)}
    assert (pecas["blog"].status, pecas["blog"].decisao) == ("publicada", "aprovado")
    assert pecas["linkedin"].status == "pendente"
    assert d.notificadas == [pecas["linkedin"]]


def test_pr_cerrado_sin_merge_termina_sin_derivados():
    d, g, post_id = _iniciar()

    grafo.retomar(g, post_id, "descartar")

    assert _pausado_en(g, post_id) == ()
    assert d.urls_linkedin == []
    [blog] = _pecas(d.repo, post_id)
    assert (blog.status, blog.decisao) == ("descartada", "descartar")
    assert d.repo.posts[post_id].estado == "descartado"


def test_deploy_sin_url_falla_y_sigue_pausado_en_esperar_deploy():
    d, g, post_id = _iniciar()
    grafo.retomar(g, post_id, "aprovado")

    with pytest.raises(ValueError, match="url_blog"):
        grafo.retomar(g, post_id)

    assert _pausado_en(g, post_id) == ("esperar_deploy",)
    [blog] = _pecas(d.repo, post_id)
    assert blog.status == "aprovada"
    assert d.urls_linkedin == []


def test_sin_abrir_pr_va_directo_a_los_derivados_como_en_f1():
    d = DoblesBlog()
    g = grafo.construir(replace(d.deps(), abrir_pr=None), InMemorySaver())
    post_id = grafo.iniciar(g, "agentes", "editor")

    assert _pausado_en(g, post_id) == ("aprovar",)
    assert d.traducidos == []
