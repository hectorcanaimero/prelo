"""App de Slack (Socket Mode): `/prelo <tema>`, conversación con `@Prelo` y aprobación de piezas con botones.

No importa el grafo: `iniciar(tema) -> post_id` y `retomar(post_id, decisao, comentario=None)` llegan inyectados.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from prelo.interfaces import Peca, Repositorio
from prelo.porta import CHAVE as PROBABILIDADE

MODAL = "prelo_editar_modal"
ESTADOS = {"aprovado": "✅ Aprobada", "editar": "✏️ Enviada a reescribir", "descartar": "🗑️ Descartada"}
BOTOES = [
    ("prelo_aprovar", "Aprobar", "primary"),
    ("prelo_editar", "Editar", None),
    ("prelo_descartar", "Descartar", "danger"),
]


def _md(texto: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": texto}}


def blocos(peca: Peca, repo: Repositorio, estado: str | None = None) -> list[dict[str, Any]]:
    """Mensaje de una pieza. Con `estado` reemplaza los botones por el resultado de la decision."""
    if peca.canal == "instagram":  # carrusel: una entrada por lámina
        texto = "\n\n".join(f"*{i}. {la['titulo']}*\n{la['texto']}" for i, la in enumerate(peca.conteudo["laminas"], 1))
    else:
        texto = "\n\n".join(t["corpo"] for t in peca.conteudo.values() if isinstance(t, dict) and "corpo" in t)
    custos = repo.custos_por_post(peca.post_id)
    linhas = "".join(f"{ag}: ${c.usd}\n" for ag, c in custos.items())
    total = sum((c.usd for c in custos.values()), Decimal(0))
    # Sin la lista de fuentes: Héctor quiere ver solo el post (las fuentes siguen en la base y en Langfuse).
    out = [_md(f"*Pieza pendiente ({peca.canal})*\n{texto}")]
    if (prob := peca.conteudo.get(PROBABILIDADE)) is not None:  # FR-17
        out.append(_md(f"*Probabilidad de aprobarla sin editar*\n{prob:.0%}"))
    if peca.violacoes:
        viol = "\n".join(f"• [{v['regra']}] «{v['trecho']}»: {v['detalhe']}" for v in peca.violacoes)
        out.append(_md(f"*Violaciones*\n{viol}"))
    out.append(_md(f"*Costo*\n{linhas}Total: ${total}"))
    if estado:
        out.append(_md(estado))
        return out
    valor = json.dumps({"post_id": peca.post_id, "peca_id": peca.id})
    botoes = []
    for aid, rotulo, estilo in BOTOES:
        if aid == "prelo_aprovar" and peca.violacoes:  # FR-6
            continue
        b: dict[str, Any] = {
            "type": "button",
            "action_id": aid,
            "value": valor,
            "text": {"type": "plain_text", "text": rotulo},
        }
        if estilo:
            b["style"] = estilo
        botoes.append(b)
    out.append({"type": "actions", "elements": botoes})
    return out


def _blocos_sugestoes(temas: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in temas:
        out.append(_md(f"*{t['tema']}*\n_{t['origem']}_ · <{t['link']}|link>"))
        boton = {
            "type": "button",
            "action_id": "prelo_escolher",
            "value": t["tema"],
            "text": {"type": "plain_text", "text": "Escribir este"},
        }
        out.append({"type": "actions", "elements": [boton]})
    return out


def registrar(
    app: Any,
    *,
    iniciar: Callable[..., str],
    retomar: Callable[..., None],
    repo: Repositorio,
    canal: str,
    cliente: Any,
    sugerir: Callable[[], list[dict[str, str]]] | None = None,
    en_fondo: Callable[[Callable[[], None]], None] | None = None,
    conversar: Callable[[str, bool], dict[str, str]] | None = None,
    bot_id: str | None = None,
) -> Callable[[Peca], None]:
    """Registra los handlers en `app` y devuelve `notificar(peca)`.

    `en_fondo(fn)` corre el trabajo largo (de 1 a 2 min de agentes) fuera del handler; por defecto, en un hilo.
    """
    en_fondo = en_fondo or (lambda fn: threading.Thread(target=fn, daemon=True).start())

    def lanzar(tema: str, respond: Callable[..., Any], **kw: Any) -> None:
        respond(f"⏳ Recibí el tema: *{tema}*. Investigando y redactando; la pieza aparece en el canal en 1-2 min.")

        def trabajo() -> None:
            try:
                iniciar(tema, **kw)
            except Exception as e:  # noqa: BLE001 - el motivo va al editor
                respond(f"No pude iniciar el post: {e}")

        en_fondo(trabajo)

    def notificar(peca: Peca) -> None:
        # Sin previsualizar links: Slack los expandía en tarjetas con imagen debajo del post.
        cliente.chat_postMessage(
            channel=canal,
            text="Pieza pendiente de aprobación",
            blocks=blocos(peca, repo),
            unfurl_links=False,
            unfurl_media=False,
        )

    @app.command("/prelo")
    def comando(ack, command, respond):
        ack()
        tema = (command.get("text") or "").strip()
        if tema == "sugerir" and sugerir:
            try:
                temas = sugerir()[:3]
            except Exception as e:  # noqa: BLE001
                respond(f"No pude sugerir temas: {e}")
                return
            respond(text="Temas sugeridos", blocks=_blocos_sugestoes(temas))
            return
        if not tema:
            respond("Uso: /prelo <tema> — o /prelo sugerir para recibir 3 temas")
            return
        lanzar(tema, respond)

    @app.action("prelo_escolher")
    def escolher(ack, action, respond):
        ack()
        lanzar(action["value"], respond, origem="sugestao")

    def decidir(decisao, meta, client, comentario=None):
        # `peca_id` elige la pausa: linkedin e instagram pueden esperar aprobación a la vez en el mismo post.
        retomar(meta["post_id"], decisao, comentario, peca_id=meta["peca_id"])
        peca = repo.ler_peca(meta["peca_id"])
        client.chat_update(
            channel=meta["channel"], ts=meta["ts"], text=ESTADOS[decisao], blocks=blocos(peca, repo, ESTADOS[decisao])
        )

    def accion(decisao):
        def handler(ack, body, action, client):
            ack()
            meta = {**json.loads(action["value"]), "channel": body["channel"]["id"], "ts": body["message"]["ts"]}
            decidir(decisao, meta, client)

        return handler

    def pieza_del_hilo(client: Any, channel: str, thread_ts: str) -> dict[str, str] | None:
        """Si el hilo cuelga de una pieza con botones, sus ids (están en el `value` de los botones)."""
        msgs = client.conversations_replies(channel=channel, ts=thread_ts, limit=1).get("messages") or []
        for b in (msgs[0].get("blocks") or []) if msgs else []:
            for e in b.get("elements", []) if b.get("type") == "actions" else []:
                if e.get("action_id") in ("prelo_aprovar", "prelo_editar", "prelo_descartar"):
                    return {**json.loads(e["value"]), "channel": channel, "ts": thread_ts}
        return None

    def pendientes() -> str:
        pecas = [p for canal in ("linkedin", "instagram") for p in repo.listar_pecas(status="pendente", canal=canal)]
        if not pecas:
            return "No tienes piezas pendientes. ¿Escribimos algo? Dime un tema."
        linhas = [f"• *{p.canal}*: {repo.ler_post(p.post_id).tema}" for p in pecas]
        return "Pendientes de tu aprobación (están en el canal con sus botones):\n" + "\n".join(linhas)

    def atender(texto: str, pieza: dict[str, str] | None, client: Any, responder: Callable[[str], Any]) -> None:
        assert conversar is not None
        r = conversar(texto, pieza is not None)
        accion = r["accion"]
        if accion == "iniciar" and r["tema"]:
            lanzar(r["tema"], responder)
        elif accion == "pendientes":
            responder(pendientes())
        elif accion == "sugerir" and sugerir:
            temas = sugerir()[:3]
            responder("Ideas:\n" + "\n".join(f"• *{t['tema']}* ({t['origem']})" for t in temas))
        elif accion == "editar" and pieza and r["comentario"]:
            responder(f"✏️ La reescribo con: _{r['comentario']}_")
            decidir("editar", pieza, client, r["comentario"])
        elif accion == "editar":
            responder("Para editar una pieza, respóndeme en el hilo de esa pieza con el cambio que quieres.")
        elif accion == "aprobar":
            responder("Eso lo decides tú: usa el botón ✅ *Aprobar* de la pieza. Yo no publico nada sin ese clic.")
        else:
            responder(
                r["respuesta"]
                or "Puedo escribir un post (dime el tema), contarte qué está pendiente, sugerirte temas o "
                "reescribir una pieza si me respondes en su hilo. Aprobar es con el botón."
            )

    if conversar:

        @app.event("message")
        def mensaje(event, say, client):
            if event.get("subtype") or event.get("bot_id"):
                return  # ediciones, uniones al canal y mensajes de bots (incluido Prelo)
            texto, canal, hilo = event.get("text") or "", event["channel"], event.get("thread_ts")
            dm = event.get("channel_type") == "im"
            mencion = bool(bot_id) and f"<@{bot_id}>" in texto
            pieza = pieza_del_hilo(client, canal, hilo) if hilo and not dm else None
            if not (dm or mencion or pieza):
                return  # en el canal solo atiende menciones y respuestas en el hilo de una pieza
            texto = re.sub(r"<@[A-Z0-9]+>", "", texto).strip()

            def responder(t: str) -> Any:
                return say(
                    text=t,
                    thread_ts=None if dm and not hilo else hilo or event["ts"],
                    unfurl_links=False,
                    unfurl_media=False,
                )

            try:
                atender(texto, pieza, client, responder)
            except Exception as e:  # noqa: BLE001 - el motivo va al editor
                responder(f"Algo falló: {e}")

    app.action("prelo_aprovar")(accion("aprovado"))
    app.action("prelo_descartar")(accion("descartar"))

    @app.action("prelo_editar")
    def editar(ack, body, action, client):
        ack()
        meta = {**json.loads(action["value"]), "channel": body["channel"]["id"], "ts": body["message"]["ts"]}
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": MODAL,
                "private_metadata": json.dumps(meta),
                "title": {"type": "plain_text", "text": "Editar pieza"},
                "submit": {"type": "plain_text", "text": "Enviar"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "comentario",
                        "label": {"type": "plain_text", "text": "Comentario"},
                        "element": {"type": "plain_text_input", "action_id": "comentario", "multiline": True},
                    }
                ],
            },
        )

    @app.view(MODAL)
    def enviar(ack, view, client):
        ack()
        comentario = view["state"]["values"]["comentario"]["comentario"]["value"]
        decidir("editar", json.loads(view["private_metadata"]), client, comentario)

    return notificar


def criar_app(config: Any, *, iniciar, retomar, repo: Repositorio):
    """Construye la app Bolt real y devuelve `(handler Socket Mode, notificar)`. Se arranca con `handler.start()`."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=config.SLACK_BOT_TOKEN.get_secret_value())
    notificar = registrar(
        app, iniciar=iniciar, retomar=retomar, repo=repo, canal=config.SLACK_CANAL, cliente=app.client
    )
    return SocketModeHandler(app, config.SLACK_APP_TOKEN.get_secret_value()), notificar
