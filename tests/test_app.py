"""Tests de api.py y app.py: API de salud/Hermes y cableado con dobles."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_grafo import RepoMemoria

from prelo import grafo
from prelo.api import criar_api
from prelo.app import montar_dependencias
from prelo.config import Settings
from prelo.interfaces import Dependencias
from prelo.slack import registrar

TOKEN = "s3creto"


def _cliente(ping=lambda: None):
    chamadas: list[str] = []

    def iniciar(tema):
        chamadas.append(tema)
        return "post-1"

    api = criar_api(Settings(PRELO_API_TOKEN=TOKEN), iniciar=iniciar, ping=ping)
    return TestClient(api), chamadas


def test_saude_200_con_base():
    c, _ = _cliente()
    assert c.get("/saude").status_code == 200


def test_saude_503_sin_base():
    def ping():
        raise ConnectionError("caída")

    c, _ = _cliente(ping)
    assert c.get("/saude").status_code == 503


def test_post_con_token_inicia_y_responde_202():
    c, chamadas = _cliente()
    r = c.post("/posts", json={"tema": "agentes"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 202
    assert r.json() == {"post_id": "post-1"}
    assert chamadas == ["agentes"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer otro"}, {"Authorization": TOKEN}])
def test_post_sin_token_o_incorrecto_401(headers):
    c, chamadas = _cliente()
    assert c.post("/posts", json={"tema": "x"}, headers=headers).status_code == 401
    assert chamadas == []


def test_post_con_token_vacio_configurado_siempre_401():
    api = criar_api(Settings(PRELO_API_TOKEN=""), iniciar=lambda t: "x", ping=lambda: None)
    r = TestClient(api).post("/posts", json={"tema": "x"}, headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_tema_vacio_422():
    c, chamadas = _cliente()
    for tema in ("", "   "):
        r = c.post("/posts", json={"tema": tema}, headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 422
    assert chamadas == []


def test_no_hay_endpoint_que_apruebe():
    api = criar_api(Settings(PRELO_API_TOKEN=TOKEN), iniciar=lambda t: "x", ping=lambda: None)
    rutas = {r.path for r in api.routes}
    assert not any("aprob" in p or "retomar" in p for p in rutas)


class RepoConCostos(RepoMemoria):
    def custos_por_post(self, post_id):
        return {}


class _Modelo:
    def gerar(self, prompt, *, agente, post_id):
        return "texto"


def _clientes(repo, buscador=None):
    return {
        "modelo": _Modelo(),
        "buscador": buscador or SimpleNamespace(buscar=lambda q, max_resultados=5: []),
        "repo": repo,
        "notificar": lambda peca: None,
    }


def test_montar_dependencias_devuelve_todas_las_claves():
    deps = montar_dependencias(Settings(), _clientes(RepoMemoria()))
    assert isinstance(deps, Dependencias)
    for campo in ("investigar", "redigir", "adaptar", "revisar", "notificar", "repo"):
        assert getattr(deps, campo) is not None
    assert "linkedin" in deps.adaptar


def test_prelo_simulado_termina_en_pieza_pendiente_notificada_en_slack():
    class Modelo:
        def gerar(self, prompt, *, agente, post_id):
            if agente == "redator":
                return '{"titulo": "T", "resumo": "R", "corpo": "Cuerpo limpio"}'
            return "consulta" if agente == "investigador" else "Post en pt"

    enviados: list[dict] = []
    cliente_slack = SimpleNamespace(chat_postMessage=lambda **kw: enviados.append(kw))
    handlers: dict = {}

    class AppFalsa:
        def command(self, nome):
            return lambda f: handlers.setdefault(nome, f)

        def action(self, nome):
            return lambda f: f

        def view(self, nome):
            return lambda f: f

    repo = RepoConCostos()
    destino: dict = {}
    notificar = registrar(
        AppFalsa(),
        iniciar=lambda tema: grafo.iniciar(destino["g"], tema, "editor"),
        retomar=lambda *a, **k: None,
        repo=repo,
        canal="C1",
        cliente=cliente_slack,
        en_fondo=lambda fn: fn(),
    )
    buscador = SimpleNamespace(
        buscar=lambda q, max_resultados=5: [{"url": "https://ex.com", "titulo": "Ex", "trecho": "dato"}]
    )
    clientes = {**_clientes(repo, buscador), "modelo": Modelo(), "notificar": notificar}
    deps = montar_dependencias(Settings(), clientes)
    destino["g"] = grafo.construir(deps, InMemorySaver())

    respuestas: list[str] = []
    handlers["/prelo"](lambda: None, {"text": "agentes"}, respuestas.append)

    assert len(respuestas) == 1 and "Recibí el tema: *agentes*" in respuestas[0]
    assert len(enviados) == 1 and enviados[0]["channel"] == "C1"
    (peca,) = repo.pecas.values()
    assert peca.status == "pendente" and peca.canal == "linkedin"
