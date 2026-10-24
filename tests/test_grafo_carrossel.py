"""Tests de F3.1: tras el deploy, `linkedin` y luego `instagram`, cada uno con su aprobación (en serie, ver grafo)."""

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


def _linkedin_decidido(decisao: str = "aprovado", d: DoblesCarrossel | None = None):
    d, g, post_id = _tras_deploy(d)
    grafo.retomar(g, post_id, decisao, None, peca_id=_por_canal(d, post_id)["linkedin"].id)
    return d, g, post_id


def test_tras_el_deploy_primero_linkedin_y_al_decidirlo_el_carrusel():
    d, _g, post_id = _tras_deploy()
    assert "instagram" not in _por_canal(d, post_id)

    d, _g, post_id = _linkedin_decidido()
    pecas = _por_canal(d, post_id)
    assert (pecas["linkedin"].status, pecas["instagram"].status) == ("aprovada", "pendente")
    assert pecas["instagram"].conteudo == {"laminas": LAMINAS, "prompt_imagem": "fondo abstracto", "url_blog": URL_BLOG}
    assert sorted(p.canal for p in d.notificadas) == ["instagram", "linkedin"]


def test_aprobar_el_carrusel_no_toca_linkedin_y_cierra_el_post():
    d, g, post_id = _linkedin_decidido()

    grafo.retomar(g, post_id, "aprovado", None, peca_id=_por_canal(d, post_id)["instagram"].id)

    pecas = _por_canal(d, post_id)
    assert (pecas["instagram"].status, pecas["instagram"].decisao) == ("aprovada", "aprovado")
    assert pecas["linkedin"].status == "aprovada"
    assert g.get_state({"configurable": {"thread_id": post_id}}).next == ()


def test_descartar_linkedin_sigue_al_carrusel_y_descartar_el_carrusel_no_afecta_a_linkedin():
    d, g, post_id = _linkedin_decidido("descartar")
    pecas = _por_canal(d, post_id)
    assert (pecas["linkedin"].status, pecas["instagram"].status) == ("descartada", "pendente")
    assert d.repo.posts[post_id].estado != "descartado"

    d, g, post_id = _linkedin_decidido()
    grafo.retomar(g, post_id, "descartar", None, peca_id=_por_canal(d, post_id)["instagram"].id)
    pecas = _por_canal(d, post_id)
    assert (pecas["instagram"].status, pecas["linkedin"].status) == ("descartada", "aprovada")


def test_editar_el_carrusel_regenera_la_pieza_y_vuelve_a_pedir_aprobacion():
    # La llamada que hace Slack: posicionales + `peca_id`.
    d, g, post_id = _linkedin_decidido()

    grafo.retomar(g, post_id, "editar", "más visual", peca_id=_por_canal(d, post_id)["instagram"].id)

    ig = [p for p in _pecas(d.repo, post_id) if p.canal == "instagram"]
    assert sorted(p.status for p in ig) == ["descartada", "pendente"]
    nueva = next(p for p in ig if p.status == "pendente")
    grafo.retomar(g, post_id, "aprovado", None, peca_id=nueva.id)
    assert next(p for p in _pecas(d.repo, post_id) if p.id == nueva.id).status == "aprovada"


def test_editar_linkedin_con_el_carrusel_activo_regenera_linkedin():
    d, g, post_id = _tras_deploy()

    grafo.retomar(g, post_id, "editar", "más corto", peca_id=_por_canal(d, post_id)["linkedin"].id)

    li = [p for p in _pecas(d.repo, post_id) if p.canal == "linkedin"]
    assert sorted(p.status for p in li) == ["descartada", "pendente"]
    assert "instagram" not in _por_canal(d, post_id)


def test_retomar_con_una_pieza_que_no_espera_decision_falla():
    _d, g, post_id = _tras_deploy()
    try:
        grafo.retomar(g, post_id, "aprovado", None, peca_id="otra")
    except ValueError as e:
        assert "otra" in str(e)
    else:
        raise AssertionError("debió fallar")


def test_la_revision_de_marca_cubre_el_texto_de_todas_las_laminas():
    d = DoblesCarrossel()
    d.violar_si = "texto dos"  # solo la segunda lámina viola

    d, _g, post_id = _linkedin_decidido(d=d)

    revisado = next(t for t in d.textos_revisados if "Portada" in t)
    assert all(s in revisado for s in ("Portada", "texto uno", "Idea", "texto dos"))
    assert "fondo abstracto" not in revisado
    pecas = _por_canal(d, post_id)
    assert pecas["instagram"].violacoes == [VIOLACAO]
    assert pecas["linkedin"].violacoes == []


def test_slack_muestra_el_texto_de_cada_lamina():
    d, _g, post_id = _linkedin_decidido()
    ig = _por_canal(d, post_id)["instagram"]
    d.repo.custos_por_post = lambda post_id: {}

    texto = "\n".join(b["text"]["text"] for b in blocos(ig, d.repo) if b["type"] == "section")

    assert "instagram" in texto
    assert all(s in texto for s in ("Portada", "texto uno", "Idea", "texto dos"))


def test_linkedin_descartado_el_post_se_resuelve_con_la_decision_del_carrusel():
    d, g, post_id = _linkedin_decidido("descartar")
    grafo.retomar(g, post_id, "aprovado", None, peca_id=_por_canal(d, post_id)["instagram"].id)
    assert d.repo.posts[post_id].estado == "aprovado"

    d, g, post_id = _linkedin_decidido("descartar")
    grafo.retomar(g, post_id, "descartar", None, peca_id=_por_canal(d, post_id)["instagram"].id)
    assert d.repo.posts[post_id].estado == "descartado"
