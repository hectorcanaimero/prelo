"""Grafo editorial de F1 (docs/arch/001-prelo.md -> grafo).

START → investigar → redigir → revisar ─┬─ ok o tentativas = 2 ─► adaptar_linkedin → revisar_linkedin → aprovar ⏸
                        ▲               └─ violação ─┐                   ▲                                   │
                        └────────────────────────────┘                   └──────────── editar ───────────────┤
                                                                         END ◄─ agendar ◄─ aprovado ─────────┤
                                                                         END ◄─────────── descartar ─────────┘

No importa ningún cliente externo: todo llega por `Dependencias`. `thread_id` = `post_id` (FR-8).
`agendar` solo marca la pieza `aprovada`; publicar es trabajo de la agenda (D9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from prelo.estado import EstadoPost
from prelo.interfaces import Decisao, Dependencias, Origem, Peca, Post, Violacao

MAX_TENTATIVAS = 2


class _Estado(EstadoPost, total=False):
    """`EstadoPost` más lo que solo necesita el grafo por dentro."""

    origem: Origem
    peca_id: str


def _texto(valor: Any) -> str:
    """Junta todos los strings de un contenido (Texto, dict por idioma, listas) para pasarlos a `revisar`."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        valor = valor.values()
    return "\n\n".join(t for t in (_texto(v) for v in valor) if t)


def _feedback(violacoes: list[Violacao]) -> str:
    return "Corrige estas violaciones de marca:\n" + "\n".join(
        f"- {v['regra']}: «{v['trecho']}» ({v['detalhe']})" for v in violacoes
    )


def construir(deps: Dependencias, checkpointer: BaseCheckpointSaver | None):
    repo = deps.repo

    def investigar(estado: _Estado) -> dict:
        post_id, tema = estado["post_id"], estado["tema"]
        repo.criar_post(
            Post(id=post_id, tema=tema, origem=estado["origem"], criado_em=datetime.now(UTC), estado="investigando")
        )
        fontes = deps.investigar(tema, post_id=post_id)
        repo.salvar_fontes(post_id, fontes)
        repo.atualizar_post(post_id, estado="redigindo")
        return {"fontes": fontes}

    def redigir(estado: _Estado) -> dict:
        violacoes = estado["violacoes"]
        feedback = _feedback(violacoes) if violacoes else None
        texto = deps.redigir(estado["tema"], estado["fontes"], feedback, post_id=estado["post_id"])
        return {"rascunho": {"es": texto}, "tentativas": estado["tentativas"] + (1 if violacoes else 0)}

    def revisar(estado: _Estado) -> dict:
        return {"violacoes": deps.revisar(_texto(estado["rascunho"]["es"]), estado["fontes"])}

    def depois_de_revisar(estado: _Estado) -> str:
        if estado["violacoes"] and estado["tentativas"] < MAX_TENTATIVAS:
            return "redigir"
        return "adaptar_linkedin"

    def adaptar_linkedin(estado: _Estado) -> dict:
        conteudo = deps.adaptar["linkedin"](
            estado["rascunho"]["es"], estado["url_blog"], estado["comentario"], post_id=estado["post_id"]
        )
        return {"derivados": {**estado["derivados"], "linkedin": conteudo}}

    def revisar_linkedin(estado: _Estado) -> dict:
        # Crea la pieza y notifica aquí, no en `aprovar`: al reanudar, `aprovar` se re-ejecuta desde el principio.
        post_id = estado["post_id"]
        conteudo = estado["derivados"]["linkedin"]
        violacoes = deps.revisar(_texto(conteudo), estado["fontes"])
        peca = Peca(
            id=str(uuid.uuid4()),
            post_id=post_id,
            canal="linkedin",
            conteudo=conteudo,
            violacoes=violacoes,
            status="pendente",
        )
        repo.criar_peca(peca)
        repo.atualizar_post(post_id, estado="aguardando_aprovacao")
        deps.notificar(peca)
        return {"violacoes": violacoes, "peca_id": peca.id}

    def aprovar(estado: _Estado) -> Command:
        resposta = interrupt({"peca_id": estado["peca_id"], "violacoes": estado["violacoes"]})
        decisao, comentario = resposta["decisao"], resposta.get("comentario")
        atualizacao = {"decisao": decisao, "comentario": comentario}
        if decisao == "aprovado":
            return Command(update=atualizacao, goto="agendar")
        if decisao == "editar":
            # La pieza vieja queda reemplazada por la que saldrá del adaptador con el comentario.
            repo.atualizar_peca(estado["peca_id"], status="descartada", decisao="editar", comentario=comentario)
            return Command(update=atualizacao, goto="adaptar_linkedin")
        if decisao == "descartar":
            repo.atualizar_peca(estado["peca_id"], status="descartada", decisao="descartar", comentario=comentario)
            repo.atualizar_post(estado["post_id"], estado="descartado")
            return Command(update=atualizacao, goto=END)
        raise ValueError(f"decisao desconocida: {decisao!r}")

    def agendar(estado: _Estado) -> dict:
        repo.atualizar_peca(estado["peca_id"], status="aprovada", decisao="aprovado", comentario=estado["comentario"])
        repo.atualizar_post(estado["post_id"], estado="aprovado")
        return {}

    g = StateGraph(_Estado)
    g.add_node("investigar", investigar)
    g.add_node("redigir", redigir)
    g.add_node("revisar", revisar)
    g.add_node("adaptar_linkedin", adaptar_linkedin)
    g.add_node("revisar_linkedin", revisar_linkedin)
    g.add_node("aprovar", aprovar, destinations=("agendar", "adaptar_linkedin", END))
    g.add_node("agendar", agendar)
    g.add_edge(START, "investigar")
    g.add_edge("investigar", "redigir")
    g.add_edge("redigir", "revisar")
    g.add_conditional_edges("revisar", depois_de_revisar, ["redigir", "adaptar_linkedin"])
    g.add_edge("adaptar_linkedin", "revisar_linkedin")
    g.add_edge("revisar_linkedin", "aprovar")
    g.add_edge("agendar", END)
    return g.compile(checkpointer=checkpointer)


def _config(post_id: str) -> dict:
    return {"configurable": {"thread_id": post_id}}


def iniciar(grafo, tema: str, origem: Origem) -> str:
    """Corre un post nuevo hasta la primera pausa (el nodo `investigar` crea la fila en `posts`). Devuelve `post_id`."""
    post_id = str(uuid.uuid4())
    estado: _Estado = {
        "post_id": post_id,
        "tema": tema,
        "origem": origem,
        "fontes": [],
        "rascunho": {},
        "derivados": {},
        "violacoes": [],
        "tentativas": 0,
        "decisao": None,
        "comentario": None,
        "url_blog": None,
    }
    grafo.invoke(estado, config=_config(post_id))
    return post_id


def retomar(grafo, post_id: str, decisao: Decisao, comentario: str | None = None) -> None:
    """Reanuda el post pausado en `aprovar` con la decisión del editor."""
    grafo.invoke(Command(resume={"decisao": decisao, "comentario": comentario}), config=_config(post_id))
