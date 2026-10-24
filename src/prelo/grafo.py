"""Grafo editorial de F1 (docs/arch/001-prelo.md -> grafo).

START → investigar → redigir → revisar ─┬─ ok o tentativas = 2 ─► adaptar_linkedin → revisar_linkedin → aprovar ⏸
                        ▲               └─ violação ─┐                   ▲                                   │
                        └────────────────────────────┘                   └──────────── editar ───────────────┤
                                                                         END ◄─ agendar ◄─ aprovado ─────────┤
                                                                         END ◄─────────── descartar ─────────┘

No importa ningún cliente externo: todo llega por `Dependencias`. `thread_id` = `post_id` (FR-8).
`agendar` solo marca la pieza `aprovada`; publicar es trabajo de la agenda (D9).

Desde F2, si `Dependencias` trae `traduzir` y `abrir_pr`, entre `revisar` y los derivados va el blog:

revisar ─► traduzir (abre el PR) → pr_blog ⏸ merge ─┬─ aprovado ─► esperar_deploy ⏸ url_blog ─► adaptar_linkedin …
                                                    └─ descartar (PR cerrado sin merge) ─► END
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
    # La rama instagram tiene claves propias: corre en paralelo a linkedin y dos nodos no pueden escribir la misma.
    peca_ig_id: str
    violacoes_ig: list[Violacao]
    comentario_ig: str | None
    peca_blog_id: str
    url_pr: str


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
        return "traduzir" if deps.traduzir and deps.abrir_pr else "adaptar_linkedin"

    def traduzir(estado: _Estado) -> dict:
        # Traduce, abre el PR y crea la pieza aquí, no en `pr_blog`: al reanudar, `pr_blog` se re-ejecuta.
        post_id = estado["post_id"]
        textos = deps.traduzir(estado["rascunho"]["es"], post_id=post_id)
        url_pr = deps.abrir_pr(post_id, textos)
        peca = Peca(
            id=str(uuid.uuid4()),
            post_id=post_id,
            canal="blog",
            conteudo=textos,
            violacoes=estado["violacoes"],
            status="pendente",
        )
        repo.criar_peca(peca)
        repo.atualizar_post(post_id, estado="aguardando_merge")
        # `rascunho` es `dict[str, Texto]` por idioma: suma pt/en y deja el "es" revisado para los derivados.
        return {"rascunho": {**textos, "es": estado["rascunho"]["es"]}, "peca_blog_id": peca.id, "url_pr": url_pr}

    def pr_blog(estado: _Estado) -> Command:
        # Lo reanuda el webhook de GitHub: "aprovado" si el PR se mergeó, "descartar" si se cerró sin merge.
        resposta = interrupt({"peca_id": estado["peca_blog_id"], "url_pr": estado["url_pr"]})
        decisao = resposta["decisao"]
        if decisao == "aprovado":
            repo.atualizar_peca(estado["peca_blog_id"], status="aprovada", decisao="aprovado")
            repo.atualizar_post(estado["post_id"], estado="aguardando_deploy")
            return Command(goto="esperar_deploy")
        if decisao == "descartar":
            repo.atualizar_peca(estado["peca_blog_id"], status="descartada", decisao="descartar")
            repo.atualizar_post(estado["post_id"], estado="descartado")
            return Command(goto=END)
        raise ValueError(f"decisao desconocida en pr_blog: {decisao!r}")

    def esperar_deploy(estado: _Estado) -> dict:
        # Lo reanuda `deploy_blog` cuando la URL pública responde 200 (D10).
        url_blog = interrupt({"url_pr": estado["url_pr"]}).get("url_blog")
        if not url_blog:
            raise ValueError("esperar_deploy necesita url_blog para reanudar")
        repo.atualizar_peca(estado["peca_blog_id"], status="publicada")
        return {"url_blog": url_blog}

    def adaptar_linkedin(estado: _Estado) -> dict:
        conteudo = deps.adaptar["linkedin"](
            estado["rascunho"]["es"], estado["url_blog"], estado["comentario"], post_id=estado["post_id"]
        )
        return {"derivados": {"linkedin": conteudo}}

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

    # ponytail: los canales se deciden en serie (linkedin y luego instagram). En paralelo, una rama pausada impide
    # que el paso avance y "editar" en la otra nunca regenera la pieza. Para aprobarlas a la vez: un hilo por canal.
    seguinte = "adaptar_carrossel" if "instagram" in deps.adaptar else END

    def aprovar(estado: _Estado) -> Command:
        resposta = interrupt({"peca_id": estado["peca_id"], "violacoes": estado["violacoes"]})
        decisao, comentario = resposta["decisao"], resposta.get("comentario")
        atualizacao = {"decisao": decisao, "comentario": comentario}
        if decisao == "aprovado":
            repo.atualizar_peca(estado["peca_id"], status="aprovada", decisao="aprovado", comentario=comentario)
            repo.atualizar_post(estado["post_id"], estado="aprovado")
            return Command(update=atualizacao, goto=seguinte)
        if decisao == "editar":
            # La pieza vieja queda reemplazada por la que saldrá del adaptador con el comentario.
            repo.atualizar_peca(estado["peca_id"], status="descartada", decisao="editar", comentario=comentario)
            return Command(update=atualizacao, goto="adaptar_linkedin")
        if decisao == "descartar":
            repo.atualizar_peca(estado["peca_id"], status="descartada", decisao="descartar", comentario=comentario)
            if seguinte == END:
                repo.atualizar_post(estado["post_id"], estado="descartado")
            return Command(update=atualizacao, goto=seguinte)
        raise ValueError(f"decisao desconocida: {decisao!r}")

    def adaptar_carrossel(estado: _Estado) -> dict:
        conteudo = deps.adaptar["instagram"](
            estado["rascunho"]["es"], estado["url_blog"], estado["comentario_ig"], post_id=estado["post_id"]
        )
        return {"derivados": {"instagram": conteudo}}

    def revisar_carrossel(estado: _Estado) -> dict:
        # Como `revisar_linkedin`; la marca se aplica al texto de todas las láminas (no al prompt de imagen).
        conteudo = estado["derivados"]["instagram"]
        violacoes = deps.revisar(_texto(conteudo["laminas"]), estado["fontes"])
        peca = Peca(
            id=str(uuid.uuid4()),
            post_id=estado["post_id"],
            canal="instagram",
            conteudo=conteudo,
            violacoes=violacoes,
            status="pendente",
        )
        repo.criar_peca(peca)
        deps.notificar(peca)
        return {"violacoes_ig": violacoes, "peca_ig_id": peca.id}

    def aprovar_carrossel(estado: _Estado) -> Command:
        resposta = interrupt({"peca_id": estado["peca_ig_id"], "violacoes": estado["violacoes_ig"]})
        decisao, comentario = resposta["decisao"], resposta.get("comentario")
        atualizacao = {"comentario_ig": comentario}
        if decisao == "aprovado":
            repo.atualizar_peca(estado["peca_ig_id"], status="aprovada", decisao="aprovado", comentario=comentario)
            repo.atualizar_post(estado["post_id"], estado="aprovado")
            return Command(update=atualizacao, goto=END)
        if decisao == "editar":
            repo.atualizar_peca(estado["peca_ig_id"], status="descartada", decisao="editar", comentario=comentario)
            return Command(update=atualizacao, goto="adaptar_carrossel")
        if decisao == "descartar":
            # Solo la pieza; el post se descarta únicamente si linkedin también se descartó.
            repo.atualizar_peca(estado["peca_ig_id"], status="descartada", decisao="descartar", comentario=comentario)
            if repo.ler_peca(estado["peca_id"]).status == "descartada":
                repo.atualizar_post(estado["post_id"], estado="descartado")
            return Command(update=atualizacao, goto=END)
        raise ValueError(f"decisao desconocida: {decisao!r}")

    g = StateGraph(_Estado)
    g.add_node("investigar", investigar)
    g.add_node("redigir", redigir)
    g.add_node("revisar", revisar)
    g.add_node("traduzir", traduzir)
    g.add_node("pr_blog", pr_blog, destinations=("esperar_deploy", END))
    g.add_node("esperar_deploy", esperar_deploy)
    g.add_node("adaptar_linkedin", adaptar_linkedin)
    g.add_node("revisar_linkedin", revisar_linkedin)
    g.add_node("aprovar", aprovar, destinations=("adaptar_linkedin", seguinte))
    if "instagram" in deps.adaptar:
        g.add_node("adaptar_carrossel", adaptar_carrossel)
        g.add_node("revisar_carrossel", revisar_carrossel)
        g.add_node("aprovar_carrossel", aprovar_carrossel, destinations=("adaptar_carrossel", END))
        g.add_edge("adaptar_carrossel", "revisar_carrossel")
        g.add_edge("revisar_carrossel", "aprovar_carrossel")
    g.add_edge(START, "investigar")
    g.add_edge("investigar", "redigir")
    g.add_edge("redigir", "revisar")
    g.add_conditional_edges("revisar", depois_de_revisar, ["redigir", "traduzir", "adaptar_linkedin"])
    g.add_edge("traduzir", "pr_blog")
    g.add_edge("esperar_deploy", "adaptar_linkedin")
    g.add_edge("adaptar_linkedin", "revisar_linkedin")
    g.add_edge("revisar_linkedin", "aprovar")
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
        "comentario_ig": None,
    }
    grafo.invoke(estado, config=_config(post_id))
    return post_id


def retomar(
    grafo,
    post_id: str,
    decisao: Decisao | None = None,
    comentario: str | None = None,
    *,
    url_blog: str | None = None,
    peca_id: str | None = None,
) -> None:
    """Reanuda el post pausado: `aprovar` (Slack) o `pr_blog` (webhook) con `decisao`; `esperar_deploy`
    (`deploy_blog`) solo con `url_blog`. Con varias aprobaciones pendientes (linkedin e instagram), `peca_id`
    elige la que se decide."""
    resume: Any = {"decisao": decisao, "comentario": comentario, "url_blog": url_blog}
    config = _config(post_id)
    if peca_id:
        pendentes = [
            i for t in grafo.get_state(config).tasks for i in t.interrupts if i.value.get("peca_id") == peca_id
        ]
        if not pendentes:
            raise ValueError(f"la pieza {peca_id} no espera una decisión")
        resume = {pendentes[0].id: resume}
    grafo.invoke(Command(resume=resume), config=config)
