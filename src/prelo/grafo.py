"""Grafo editorial de Prelo.

START → investigar → redigir → revisar ─┬─ ok ────────► aprovar (interrupt) ─┬─ aprovado ─► publicar → END
                         ▲              └─ violação ──┐                       ├─ editar ───► redigir
                         └────────────────────────────┘ (máx. MAX_TENTATIVAS) └─ descartar ─► END

Las dependencias (investigar, redigir, publicar) se inyectan: en producción usan modelos y APIs,
en los tests son funciones simples.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from prelo import revisao
from prelo.estado import Decisao, EstadoPost, Fonte, Rascunho

MAX_TENTATIVAS = 2


@dataclass
class Dependencias:
    investigar: Callable[[str], list[Fonte]]
    redigir: Callable[[EstadoPost], Rascunho]
    publicar: Callable[[EstadoPost], list[dict]]
    regras: dict | None = None


def construir_grafo(deps: Dependencias, checkpointer: BaseCheckpointSaver | None = None):
    def investigar(estado: EstadoPost) -> dict:
        return {"fontes": deps.investigar(estado["tema"]), "tentativas": 0}

    def redigir(estado: EstadoPost) -> dict:
        return {"rascunho": deps.redigir(estado), "tentativas": estado.get("tentativas", 0) + 1}

    def revisar(estado: EstadoPost) -> dict:
        achados = revisao.revisar(estado["rascunho"].texto(), deps.regras)
        feedback = ""
        if revisao.bloqueia(achados):
            termos = sorted({v.termo for v in achados if v.nivel == "bloqueia"})
            feedback = "Quita del texto: " + ", ".join(termos)
        return {"violacoes": [asdict(v) for v in achados], "feedback": feedback}

    def depois_de_revisar(estado: EstadoPost) -> str:
        bloqueado = any(v["nivel"] == "bloqueia" for v in estado["violacoes"])
        if bloqueado and estado["tentativas"] < MAX_TENTATIVAS:
            return "redigir"
        return "aprovar"

    def aprovar(estado: EstadoPost) -> dict:
        resposta = interrupt({
            "rascunho": estado["rascunho"].model_dump(),
            "violacoes": estado["violacoes"],
        })
        decisao = Decisao.model_validate(resposta)
        bloqueado = any(v["nivel"] == "bloqueia" for v in estado["violacoes"])
        if decisao.decisao == "aprovado" and bloqueado:
            # No se aprueba un texto con bloqueos: se vuelve a redactar con el comentario.
            decisao = Decisao(decisao="editar", comentario=decisao.comentario or estado["feedback"])
        return {"decisao": decisao, "feedback": decisao.comentario, "tentativas": 0}

    def depois_de_aprovar(estado: EstadoPost) -> str:
        return {"aprovado": "publicar", "editar": "redigir", "descartar": END}[estado["decisao"].decisao]

    def publicar(estado: EstadoPost) -> dict:
        if estado["decisao"].decisao != "aprovado":  # defensa en profundidad
            raise RuntimeError("Publicar sin aprobación")
        return {"publicacoes": deps.publicar(estado)}

    g = StateGraph(EstadoPost)
    g.add_node("investigar", investigar)
    g.add_node("redigir", redigir)
    g.add_node("revisar", revisar)
    g.add_node("aprovar", aprovar)
    g.add_node("publicar", publicar)
    g.add_edge(START, "investigar")
    g.add_edge("investigar", "redigir")
    g.add_edge("redigir", "revisar")
    g.add_conditional_edges("revisar", depois_de_revisar, ["redigir", "aprovar"])
    g.add_conditional_edges("aprovar", depois_de_aprovar, ["publicar", "redigir", END])
    g.add_edge("publicar", END)
    return g.compile(checkpointer=checkpointer)
