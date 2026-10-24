"""Tests del grafo de F1 con dobles para todas las funciones de `Dependencias`."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from prelo import grafo
from prelo.interfaces import Dependencias, Fonte, Peca, Post, Violacao

FONTES: list[Fonte] = [{"url": "https://ex.com", "titulo": "Ex", "trecho": "dato"}]
VIOLACAO: Violacao = {"regra": "frase_ia", "trecho": "en el mundo actual", "detalhe": "frase de IA"}


class RepoMemoria:
    """`Repositorio` en memoria: solo lo que usa el grafo, el resto falla si se llama."""

    def __init__(self) -> None:
        self.posts: dict[str, Post] = {}
        self.fontes: dict[str, list[Fonte]] = {}
        self.pecas: dict[str, Peca] = {}

    def criar_post(self, post):
        self.posts[post.id] = post

    def ler_post(self, post_id):
        return self.posts[post_id]

    def atualizar_post(self, post_id, *, estado):
        self.posts[post_id] = replace(self.posts[post_id], estado=estado)

    def salvar_fontes(self, post_id, fontes):
        self.fontes[post_id] = list(fontes)

    def ler_fontes(self, post_id):
        return self.fontes.get(post_id, [])

    def criar_peca(self, peca):
        self.pecas[peca.id] = peca

    def atualizar_peca(self, peca_id, *, status=None, decisao=None, comentario=None, agendada_para=None):
        cambios = {"status": status, "decisao": decisao, "comentario": comentario, "agendada_para": agendada_para}
        self.pecas[peca_id] = replace(self.pecas[peca_id], **{k: v for k, v in cambios.items() if v is not None})

    def ler_peca(self, peca_id):
        return self.pecas[peca_id]

    def listar_pecas(self, *, status, canal):
        return [p for p in self.pecas.values() if p.status == status and p.canal == canal]

    def registrar_publicacao(self, publicacao):
        raise AssertionError("el grafo no publica (D9)")

    def registrar_custo(self, custo):
        raise AssertionError("el grafo no registra costos")

    def custos_por_post(self, post_id):
        raise AssertionError("el grafo no lee costos")


class Dobles:
    """Arma `Dependencias` con dobles que registran sus llamadas."""

    def __init__(self, *, viola: bool = False, repo: RepoMemoria | None = None) -> None:
        self.viola = viola
        self.repo = repo or RepoMemoria()
        self.redigir_feedbacks: list[str | None] = []
        self.adaptar_feedbacks: list[str | None] = []
        self.notificadas: list[Peca] = []

    def deps(self) -> Dependencias:
        def investigar(tema, *, post_id):
            return FONTES

        def redigir(tema, fontes, feedback, *, post_id):
            self.redigir_feedbacks.append(feedback)
            return {"titulo": tema, "resumo": "r", "corpo": f"borrador {len(self.redigir_feedbacks)}"}

        def adaptar_linkedin(texto, url_blog, feedback, *, post_id):
            self.adaptar_feedbacks.append(feedback)
            n = len(self.adaptar_feedbacks)
            return {"pt": {"titulo": texto["titulo"], "resumo": "", "corpo": f"linkedin v{n}"}}

        def revisar(texto, fontes):
            return [VIOLACAO] if self.viola else []

        return Dependencias(
            investigar=investigar,
            redigir=redigir,
            adaptar={"linkedin": adaptar_linkedin},
            revisar=revisar,
            notificar=self.notificadas.append,
            repo=self.repo,
        )


def _pausado_en(g, post_id) -> tuple[str, ...]:
    return g.get_state({"configurable": {"thread_id": post_id}}).next


def _pecas(repo: RepoMemoria, post_id: str) -> list[Peca]:
    return [p for p in repo.pecas.values() if p.post_id == post_id]


def test_tema_sin_violaciones_pausa_en_aprovar_con_pieza_pendente():
    d = Dobles()
    g = grafo.construir(d.deps(), InMemorySaver())

    post_id = grafo.iniciar(g, "agentes", "editor")

    assert _pausado_en(g, post_id) == ("aprovar",)
    assert d.repo.posts[post_id].tema == "agentes"
    assert d.repo.fontes[post_id] == FONTES
    [peca] = _pecas(d.repo, post_id)
    assert (peca.canal, peca.status, peca.violacoes) == ("linkedin", "pendente", [])
    assert peca.conteudo["pt"]["corpo"] == "linkedin v1"
    assert d.notificadas == [peca]
    assert d.redigir_feedbacks == [None]


def test_retomar_aprovado_deja_la_pieza_aprovada():
    d = Dobles()
    g = grafo.construir(d.deps(), InMemorySaver())
    post_id = grafo.iniciar(g, "agentes", "editor")

    grafo.retomar(g, post_id, "aprovado")

    [peca] = _pecas(d.repo, post_id)
    assert (peca.status, peca.decisao) == ("aprovada", "aprovado")
    assert _pausado_en(g, post_id) == ()
    assert len(d.notificadas) == 1  # reanudar no vuelve a notificar


def test_borrador_que_siempre_viola_se_reescribe_dos_veces():
    d = Dobles(viola=True)
    g = grafo.construir(d.deps(), InMemorySaver())

    post_id = grafo.iniciar(g, "agentes", "editor")

    assert len(d.redigir_feedbacks) == 3  # 1 borrador + 2 reescrituras
    assert d.redigir_feedbacks[0] is None
    assert all(VIOLACAO["trecho"] in f for f in d.redigir_feedbacks[1:])
    assert _pausado_en(g, post_id) == ("aprovar",)
    estado = g.get_state({"configurable": {"thread_id": post_id}}).values
    assert estado["violacoes"] and estado["tentativas"] == 2
    [peca] = _pecas(d.repo, post_id)
    assert peca.violacoes == [VIOLACAO]


def test_editar_llama_al_adaptador_con_el_comentario_y_vuelve_a_pausar():
    d = Dobles()
    g = grafo.construir(d.deps(), InMemorySaver())
    post_id = grafo.iniciar(g, "agentes", "editor")
    [vieja] = _pecas(d.repo, post_id)

    grafo.retomar(g, post_id, "editar", "más corto")

    assert d.adaptar_feedbacks == [None, "más corto"]
    assert _pausado_en(g, post_id) == ("aprovar",)
    vieja = d.repo.pecas[vieja.id]
    assert (vieja.status, vieja.decisao, vieja.comentario) == ("descartada", "editar", "más corto")
    [nueva] = [p for p in _pecas(d.repo, post_id) if p.status == "pendente"]
    assert nueva.conteudo["pt"]["corpo"] == "linkedin v2"
    assert d.notificadas[-1] == nueva

    grafo.retomar(g, post_id, "aprovado")
    assert d.repo.pecas[nueva.id].status == "aprovada"


def test_descartar_deja_la_pieza_descartada_y_no_aprueba_nada():
    d = Dobles()
    g = grafo.construir(d.deps(), InMemorySaver())
    post_id = grafo.iniciar(g, "agentes", "editor")

    grafo.retomar(g, post_id, "descartar")

    [peca] = _pecas(d.repo, post_id)
    assert (peca.status, peca.decisao) == ("descartada", "descartar")
    assert d.repo.listar_pecas(status="aprovada", canal="linkedin") == []
    assert _pausado_en(g, post_id) == ()


@pytest.fixture
def postgres_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no definido")
    return url


def test_reinicio_con_postgres_aprueba_el_texto_pausado(postgres_url):
    from langgraph.checkpoint.postgres import PostgresSaver

    repo = RepoMemoria()  # hace de la base de datos que sobrevive al reinicio
    with PostgresSaver.from_conn_string(postgres_url) as saver:
        saver.setup()
        antes = Dobles(repo=repo)
        post_id = grafo.iniciar(grafo.construir(antes.deps(), saver), "agentes", "editor")
    [pausada] = _pecas(repo, post_id)

    # "Reinicio": conexión, checkpointer, dobles y grafo nuevos.
    with PostgresSaver.from_conn_string(postgres_url) as saver:
        despues = Dobles(repo=repo)
        despues.adaptar_feedbacks.append("contador")  # si se re-adaptara, saldría "linkedin v2"
        g = grafo.construir(despues.deps(), saver)
        assert _pausado_en(g, post_id) == ("aprovar",)
        grafo.retomar(g, post_id, "aprovado")

    assert despues.adaptar_feedbacks == ["contador"] and despues.redigir_feedbacks == []
    [aprovada] = _pecas(repo, post_id)
    assert aprovada.id == pausada.id
    assert (aprovada.status, aprovada.decisao) == ("aprovada", "aprovado")
    assert aprovada.conteudo == pausada.conteudo == {"pt": {"titulo": "agentes", "resumo": "", "corpo": "linkedin v1"}}
