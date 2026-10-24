"""App de Slack (Socket Mode): `/prelo <tema>` y aprobación de piezas con botones.

No importa el grafo: `iniciar(tema) -> post_id` y `retomar(post_id, decisao, comentario=None)` llegan inyectados.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from prelo.interfaces import Peca, Repositorio

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
    fontes = "\n".join(f"• <{f['url']}|{f['titulo']}>" for f in repo.ler_fontes(peca.post_id)) or "_sin fuentes_"
    custos = repo.custos_por_post(peca.post_id)
    linhas = "".join(f"{ag}: ${c.usd}\n" for ag, c in custos.items())
    total = sum((c.usd for c in custos.values()), Decimal(0))
    out = [_md(f"*Pieza pendiente ({peca.canal})*\n{texto}"), _md(f"*Fuentes*\n{fontes}")]
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


def registrar(
    app: Any,
    *,
    iniciar: Callable[[str], str],
    retomar: Callable[..., None],
    repo: Repositorio,
    canal: str,
    cliente: Any,
) -> Callable[[Peca], None]:
    """Registra los handlers en `app` y devuelve `notificar(peca)`."""

    def notificar(peca: Peca) -> None:
        cliente.chat_postMessage(channel=canal, text="Pieza pendiente de aprobación", blocks=blocos(peca, repo))

    @app.command("/prelo")
    def comando(ack, command, respond):
        ack()
        tema = (command.get("text") or "").strip()
        if not tema:
            respond("Uso: /prelo <tema>")
            return
        try:
            iniciar(tema)
        except Exception as e:  # noqa: BLE001 - el motivo va al editor
            respond(f"No pude iniciar el post: {e}")
            return
        respond(f"Recibí el tema: {tema}")

    def decidir(decisao, meta, client, comentario=None):
        if comentario is None:
            retomar(meta["post_id"], decisao)
        else:
            retomar(meta["post_id"], decisao, comentario)
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
