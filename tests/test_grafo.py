import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from prelo.estado import Fonte, Rascunho
from prelo.grafo import MAX_TENTATIVAS, Dependencias, construir_grafo

REGRAS = {"bloqueia": {"empregadores": ["Acme"]}, "aviso": {}}


class Fakes:
    """Redactor que escribe los textos de una lista, en orden; publicador que registra llamadas."""

    def __init__(self, textos: list[str]):
        self.textos = textos
        self.redacoes: list[dict] = []
        self.publicados: list[str] = []

    def investigar(self, tema):
        return [Fonte(url="https://exemplo.com", titulo=tema, trecho="dato")]

    def redigir(self, estado):
        self.redacoes.append({"feedback": estado.get("feedback", "")})
        corpo = self.textos[min(len(self.redacoes), len(self.textos)) - 1]
        return Rascunho(titulo=estado["tema"], resumo="resumo", corpo=corpo)

    def publicar(self, estado):
        self.publicados.append(estado["rascunho"].corpo)
        return [{"canal": "teste", "url": "https://exemplo.com/post"}]


def _rodar(textos):
    f = Fakes(textos)
    grafo = construir_grafo(Dependencias(f.investigar, f.redigir, f.publicar, REGRAS), InMemorySaver())
    cfg = {"configurable": {"thread_id": "post-1"}}
    saida = grafo.invoke({"tema": "LangGraph"}, cfg)
    return f, grafo, cfg, saida


def test_para_en_la_aprobacion_sin_publicar():
    f, grafo, cfg, saida = _rodar(["texto limpio"])
    assert "__interrupt__" in saida
    assert saida["__interrupt__"][0].value["rascunho"]["corpo"] == "texto limpio"
    assert f.publicados == []
    assert grafo.get_state(cfg).next == ("aprovar",)


def test_aprobado_publica_una_vez():
    f, grafo, cfg, _ = _rodar(["texto limpio"])
    final = grafo.invoke(Command(resume={"decisao": "aprovado"}), cfg)
    assert f.publicados == ["texto limpio"]
    assert final["publicacoes"][0]["canal"] == "teste"


def test_descartar_termina_sin_publicar():
    f, grafo, cfg, _ = _rodar(["texto limpio"])
    grafo.invoke(Command(resume={"decisao": "descartar"}), cfg)
    assert f.publicados == []
    assert grafo.get_state(cfg).next == ()


def test_editar_vuelve_a_redactar_con_el_comentario():
    f, grafo, cfg, _ = _rodar(["primera versión", "segunda versión"])
    saida = grafo.invoke(Command(resume={"decisao": "editar", "comentario": "más corto"}), cfg)
    assert f.redacoes[-1]["feedback"] == "más corto"
    assert saida["__interrupt__"][0].value["rascunho"]["corpo"] == "segunda versión"


def test_violacion_se_corrige_sola_antes_de_pedir_aprobacion():
    f, _, _, saida = _rodar(["trabajé en Acme", "trabajé en una empresa"])
    assert len(f.redacoes) == 2
    assert "Acme" in f.redacoes[1]["feedback"]
    assert saida["__interrupt__"][0].value["violacoes"] == []


def test_violacion_persistente_no_se_puede_aprobar():
    f, grafo, cfg, saida = _rodar(["Acme siempre"])
    assert len(f.redacoes) == MAX_TENTATIVAS
    assert saida["__interrupt__"][0].value["violacoes"][0]["termo"] == "Acme"
    saida = grafo.invoke(Command(resume={"decisao": "aprovado"}), cfg)
    assert f.publicados == []
    assert "__interrupt__" in saida  # volvió a redactar y pide aprobación otra vez


def test_decision_invalida_falla():
    _, grafo, cfg, _ = _rodar(["texto limpio"])
    with pytest.raises(ValidationError):
        grafo.invoke(Command(resume={"decisao": "publica ya"}), cfg)
