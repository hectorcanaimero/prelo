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

    def event(self, nome):
        return lambda f: self.h.setdefault(f"event:{nome}", f)


class ClienteFalso:
    def __init__(self):
        self.enviados, self.atualizados, self.modais = [], [], []

    def chat_postMessage(self, **kw):
        self.enviados.append(kw)

    def chat_update(self, **kw):
        self.atualizados.append(kw)

    def views_open(self, **kw):
        self.modais.append(kw)

    def conversations_replies(self, **kw):
        """El hilo "1.0" cuelga de una pieza con botones; cualquier otro, de un mensaje normal."""
        if kw["ts"] != "1.0":
            return {"messages": [{"text": "hola"}]}
        return {"messages": [{"blocks": slack.blocos(peca(), RepoFalso())}]}


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

    def listar_pecas(self, *, status, canal):
        return [peca()] if canal == "linkedin" else []

    def ler_post(self, post_id):
        return SimpleNamespace(tema="evals en producción")


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
    assert "Corpo do post" in t and "https://ex.com/a" not in t and "Fuentes" not in t
    assert msg["unfurl_links"] is False and msg["unfurl_media"] is False
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


@pytest.fixture
def charla():
    """Prelo conversacional con un `conversar` falso que devuelve lo que diga `ctx.r`."""
    app, cliente, calls = AppFalsa(), ClienteFalso(), []
    estado = SimpleNamespace(r={"accion": "charla", "tema": "", "comentario": "", "respuesta": "hola"}, vistos=[])

    def conversar(texto, en_hilo):
        estado.vistos.append((texto, en_hilo))
        return estado.r

    slack.registrar(
        app,
        iniciar=lambda tema, **kw: calls.append(("iniciar", tema)),
        retomar=lambda *a, **kw: calls.append(("retomar", *a, kw)),
        repo=RepoFalso(),
        canal="C1",
        cliente=cliente,
        en_fondo=lambda fn: fn(),
        conversar=conversar,
        bot_id="UBOT",
    )
    dichos = []

    def decir(text, **evento):
        ev = {"channel": "C1", "ts": "9.9", "text": text, **evento}
        app.h["event:message"](event=ev, say=lambda **kw: dichos.append(kw), client=cliente)
        return dichos

    return SimpleNamespace(estado=estado, calls=calls, decir=decir, dichos=dichos, c=cliente)


def test_en_el_canal_ignora_lo_que_no_es_para_prelo(charla):
    assert charla.decir("hola equipo") == []
    assert charla.decir("respuesta en otro hilo", thread_ts="5.0") == []
    assert charla.decir("<@UBOT> soy un bot", bot_id="B1") == []
    assert charla.estado.vistos == []


def test_mencion_inicia_un_post_y_responde_en_hilo(charla):
    charla.estado.r = {"accion": "iniciar", "tema": "memoria de agentes", "comentario": "", "respuesta": ""}
    dichos = charla.decir("<@UBOT> escribe sobre memoria de agentes")
    assert charla.estado.vistos == [("escribe sobre memoria de agentes", False)]
    assert ("iniciar", "memoria de agentes") in charla.calls
    assert "memoria de agentes" in dichos[0]["text"] and dichos[0]["thread_ts"] == "9.9"


def test_dm_pide_pendientes(charla):
    charla.estado.r = {"accion": "pendientes", "tema": "", "comentario": "", "respuesta": ""}
    dichos = charla.decir("¿qué tengo pendiente?", channel_type="im")
    assert "evals en producción" in dichos[0]["text"] and dichos[0]["thread_ts"] is None


def test_respuesta_en_hilo_de_pieza_edita_con_el_comentario(charla):
    charla.estado.r = {"accion": "editar", "tema": "", "comentario": "más corto", "respuesta": ""}
    charla.decir("hazlo más corto", thread_ts="1.0")
    assert charla.estado.vistos == [("hazlo más corto", True)]
    assert ("retomar", "post1", "editar", "más corto", {"peca_id": "peca1"}) in charla.calls
    assert charla.c.atualizados[0]["ts"] == "1.0"


def test_publicar_por_mensaje_nunca_aprueba(charla):
    charla.estado.r = {"accion": "aprobar", "tema": "", "comentario": "", "respuesta": ""}
    dichos = charla.decir("dale, publícalo", thread_ts="1.0")
    assert not [c for c in charla.calls if c[0] == "retomar"]
    assert "Aprobar" in dichos[0]["text"]
