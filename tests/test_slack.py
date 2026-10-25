import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from prelo import slack
from prelo.interfaces import CustoAgente, Peca


class AppFalsa:
    """Registra los handlers que Bolt recibiria."""

    def __init__(self):
        self.h = {}

    def command(self, nome):
        return lambda f: self.h.setdefault(nome, f)

    def action(self, nome):
        return lambda f: self.h.setdefault(nome, f)

    def view(self, nome):
        return lambda f: self.h.setdefault(nome, f)


class ClienteFalso:
    def __init__(self):
        self.enviados, self.atualizados, self.modais = [], [], []

    def chat_postMessage(self, **kw):
        self.enviados.append(kw)

    def chat_update(self, **kw):
        self.atualizados.append(kw)

    def views_open(self, **kw):
        self.modais.append(kw)


class RepoFalso:
    def ler_fontes(self, post_id):
        return [{"url": "https://ex.com/a", "titulo": "Fonte A", "trecho": "x"}]

    def custos_por_post(self, post_id):
        return {
            "redator": CustoAgente(10, 20, Decimal("0.0300")),
            "investigador": CustoAgente(5, 5, Decimal("0.0100")),
        }

    def ler_peca(self, peca_id):
        return peca()


def peca(violacoes=()):
    return Peca(
        id="peca1",
        post_id="post1",
        canal="linkedin",
        conteudo={"pt": {"titulo": "T", "resumo": "R", "corpo": "Corpo do post"}},
        violacoes=list(violacoes),
        status="pendente",
    )


@pytest.fixture
def ctx():
    app, cliente, chamadas = AppFalsa(), ClienteFalso(), []

    def iniciar(tema):
        if tema == "falla":
            raise RuntimeError("sin cupo")
        chamadas.append(("iniciar", tema))
        return "post1"

    def retomar(*a, **kw):
        chamadas.append(("retomar", *a, kw))

    notificar = slack.registrar(
        app, iniciar=iniciar, retomar=retomar, repo=RepoFalso(), canal="C1", cliente=cliente, en_fondo=lambda fn: fn()
    )
    return SimpleNamespace(app=app, c=cliente, calls=chamadas, notificar=notificar)


def comando(ctx, texto):
    resp = []
    ctx.app.h["/prelo"](ack=lambda: None, command={"text": texto}, respond=resp.append)
    return resp


def botoes(msg):
    return [e for b in msg["blocks"] if b["type"] == "actions" for e in b["elements"]]


def texto_total(msg):
    return json.dumps(msg["blocks"], ensure_ascii=False)


def test_comando_llama_a_iniciar(ctx):
    resp = comando(ctx, "IA local")
    assert ("iniciar", "IA local") in ctx.calls
    assert "IA local" in resp[0]


def test_fallo_de_iniciar_responde_motivo(ctx):
    resp = comando(ctx, "falla")
    assert "falla" in resp[0] and "sin cupo" in resp[1]


def test_responde_antes_de_terminar_el_trabajo(ctx):
    pendientes = []
    ctx.app = AppFalsa()
    slack.registrar(
        ctx.app,
        iniciar=lambda t: ctx.calls.append(("iniciar", t)),
        retomar=None,
        repo=RepoFalso(),
        canal="C1",
        cliente=ctx.c,
        en_fondo=pendientes.append,
    )
    resp = comando(ctx, "IA local")
    assert "IA local" in resp[0] and ctx.calls == []  # ya respondió y todavía no corrió el grafo
    pendientes[0]()
    assert ctx.calls == [("iniciar", "IA local")]


def test_pieza_sin_violaciones(ctx):
    ctx.notificar(peca())
    msg = ctx.c.enviados[0]
    assert msg["channel"] == "C1"
    bs = botoes(msg)
    assert [b["action_id"] for b in bs] == ["prelo_aprovar", "prelo_editar", "prelo_descartar"]
    assert all(json.loads(b["value"]) == {"post_id": "post1", "peca_id": "peca1"} for b in bs)
    t = texto_total(msg)
    assert "https://ex.com/a" in t and "Corpo do post" in t
    assert "redator" in t and "0.0400" in t


def test_pieza_con_violaciones_sin_aprobar(ctx):
    ctx.notificar(peca([{"regra": "frase_ia", "trecho": "en el mundo de", "detalhe": "cara de IA"}]))
    msg = ctx.c.enviados[0]
    assert "prelo_aprovar" not in [b["action_id"] for b in botoes(msg)]
    assert "en el mundo de" in texto_total(msg)


def accion(ctx, nome):
    valor = json.dumps({"post_id": "post1", "peca_id": "peca1"})
    body = {"channel": {"id": "C1"}, "message": {"ts": "1.1"}, "trigger_id": "tg"}
    ctx.app.h[nome](ack=lambda: None, body=body, action={"value": valor}, client=ctx.c)


def test_aprobar(ctx):
    accion(ctx, "prelo_aprovar")
    assert ctx.calls == [("retomar", "post1", "aprovado", None, {"peca_id": "peca1"})]
    assert ctx.c.atualizados


def test_descartar(ctx):
    accion(ctx, "prelo_descartar")
    assert ctx.calls == [("retomar", "post1", "descartar", None, {"peca_id": "peca1"})]
    assert ctx.c.atualizados


def test_editar_abre_modal_y_envia(ctx):
    accion(ctx, "prelo_editar")
    assert ctx.calls == []
    modal = ctx.c.modais[0]["view"]
    assert modal["blocks"][0]["block_id"] == "comentario"
    view = {
        "private_metadata": modal["private_metadata"],
        "state": {"values": {"comentario": {"comentario": {"value": "más corto"}}}},
    }
    ctx.app.h[modal["callback_id"]](ack=lambda: None, view=view, client=ctx.c)
    assert ctx.calls == [("retomar", "post1", "editar", "más corto", {"peca_id": "peca1"})]
    assert ctx.c.atualizados
