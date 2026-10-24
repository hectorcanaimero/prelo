"""Tests de F3.1: tras el deploy, derivados `linkedin` e `instagram` en paralelo, cada uno con su aprobación."""

from __future__ import annotations

from dataclasses import replace

from langgraph.checkpoint.memory import InMemorySaver
from test_grafo import VIOLACAO, _pecas
from test_grafo_blog import URL_BLOG, DoblesBlog

from prelo import grafo
from prelo.interfaces import Peca
from prelo.slack import blocos

LAMINAS = [{"titulo": "Portada", "texto": "texto uno"}, {"titulo": "Idea", "texto": "texto dos"}]


class DoblesCarrossel(DoblesBlog):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.textos_revisados: list[str] = []
        self.violar_si: str | None = None

    def deps(self):
        base = super().deps()

        def adaptar_instagram(texto, url_blog, feedback, *, post_id):
            return {"laminas": LAMINAS, "prompt_imagem": "fondo abstracto", "url_blog": url_blog}

        def revisar(texto, fontes):
            self.textos_revisados.append(texto)
            return [VIOLACAO] if self.violar_si and self.violar_si in texto else []

        return replace(base, adaptar={**base.adaptar, "instagram": adaptar_instagram}, revisar=revisar)


def _tras_deploy(d: DoblesCarrossel | None = None):
    d = d or DoblesCarrossel()
    g = grafo.construir(d.deps(), InMemorySaver())
    post_id = grafo.iniciar(g, "agentes", "editor")
    grafo.retomar(g, post_id, "aprovado")
    grafo.retomar(g, post_id, url_blog=URL_BLOG)
    return d, g, post_id


def _por_canal(d, post_id) -> dict[str, Peca]:
    return {p.canal: p for p in _pecas(d.repo, post_id)}


def test_tras_el_deploy_hay_dos_piezas_pendientes_linkedin_e_instagram():
    d, _g, post_id = _tras_deploy()

    pecas = _por_canal(d, post_id)
    assert (pecas["linkedin"].status, pecas["instagram"].status) == ("pendente", "pendente")
    assert pecas["instagram"].conteudo == {"laminas": LAMINAS, "prompt_imagem": "fondo abstracto", "url_blog": URL_BLOG}
    assert sorted(p.canal for p in d.notificadas) == ["instagram", "linkedin"]


def test_aprobar_una_no_aprueba_la_otra():
    d, g, post_id = _tras_deploy()
    pecas = _por_canal(d, post_id)

    grafo.retomar(g, post_id, "aprovado", peca_id=pecas["instagram"].id)

    pecas = _por_canal(d, post_id)
    assert (pecas["instagram"].status, pecas["instagram"].decisao) == ("aprovada", "aprovado")
    assert (pecas["linkedin"].status, pecas["linkedin"].decisao) == ("pendente", None)

    grafo.retomar(g, post_id, "aprovado", peca_id=pecas["linkedin"].id)
    assert _por_canal(d, post_id)["linkedin"].status == "aprovada"
    assert g.get_state({"configurable": {"thread_id": post_id}}).next == ()


def test_descartar_el_carrusel_no_afecta_a_linkedin():
    d, g, post_id = _tras_deploy()
    pecas = _por_canal(d, post_id)

    grafo.retomar(g, post_id, "descartar", peca_id=pecas["instagram"].id)

    pecas = _por_canal(d, post_id)
    assert pecas["instagram"].status == "descartada"
    assert pecas["linkedin"].status == "pendente"
    assert d.repo.posts[post_id].estado != "descartado"

    grafo.retomar(g, post_id, "aprovado", peca_id=pecas["linkedin"].id)
    assert _por_canal(d, post_id)["linkedin"].status == "aprovada"


def test_la_revision_de_marca_cubre_el_texto_de_todas_las_laminas():
    d = DoblesCarrossel()
    d.violar_si = "texto dos"  # solo la segunda lámina viola

    d, _g, post_id = _tras_deploy(d)

    revisado = next(t for t in d.textos_revisados if "Portada" in t)
    assert all(s in revisado for s in ("Portada", "texto uno", "Idea", "texto dos"))
    assert "fondo abstracto" not in revisado
    pecas = _por_canal(d, post_id)
    assert pecas["instagram"].violacoes == [VIOLACAO]
    assert pecas["linkedin"].violacoes == []


def test_slack_muestra_el_texto_de_cada_lamina():
    d, _g, post_id = _tras_deploy()
    ig = _por_canal(d, post_id)["instagram"]
    d.repo.custos_por_post = lambda post_id: {}

    texto = "\n".join(b["text"]["text"] for b in blocos(ig, d.repo) if b["type"] == "section")

    assert "instagram" in texto
    assert all(s in texto for s in ("Portada", "texto uno", "Idea", "texto dos"))
