"""Tests de webhooks.py: firma, decisión según el PR y reenvíos."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from prelo.webhooks import criar_router

SECRETO = "s3creto"


def _cliente():
    chamadas: list[tuple] = []
    api = FastAPI()
    api.include_router(criar_router(SECRETO, retomar=lambda *a: chamadas.append(a)))
    return TestClient(api), chamadas


def _enviar(cliente, payload, evento="pull_request", segredo=SECRETO):
    corpo = json.dumps(payload).encode()
    firma = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return cliente.post(
        "/webhooks/github", content=corpo, headers={"X-Hub-Signature-256": firma, "X-GitHub-Event": evento}
    )


def _pr(rama="prelo/abc", merged=True, action="closed"):
    return {"action": action, "pull_request": {"merged": merged, "head": {"ref": rama}}}


def test_firma_invalida_401_sin_retomar():
    c, chamadas = _cliente()
    assert _enviar(c, _pr(), segredo="otro").status_code == 401
    assert c.post("/webhooks/github", json=_pr()).status_code == 401
    assert chamadas == []


def test_pr_mergeado_aprueba():
    c, chamadas = _cliente()
    assert _enviar(c, _pr()).status_code == 204
    assert chamadas == [("abc", "aprovado")]


def test_pr_cerrado_sin_merge_descarta():
    c, chamadas = _cliente()
    assert _enviar(c, _pr(merged=False)).status_code == 204
    assert chamadas == [("abc", "descartar")]


def test_otra_rama_push_u_otra_accion_sin_efecto():
    c, chamadas = _cliente()
    assert _enviar(c, _pr(rama="feature/x")).status_code == 204
    assert _enviar(c, _pr(), evento="push").status_code == 204
    assert _enviar(c, _pr(action="opened")).status_code == 204
    assert chamadas == []


def test_reenvio_no_reanuda_dos_veces():
    c, chamadas = _cliente()
    _enviar(c, _pr())
    assert _enviar(c, _pr()).status_code == 204
    assert chamadas == [("abc", "aprovado")]
