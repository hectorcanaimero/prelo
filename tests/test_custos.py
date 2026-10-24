import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from prelo.custos import PRECIOS, calcular_usd
from prelo.modelo import ModeloAnthropic

KEY = "sk-ant-super-secret"


class FakeAnthropic:
    api_key = KEY

    def __init__(self):
        self.llamadas = []
        self.messages = self

    def create(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(text="hola")],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        )


class FakeLangfuse:
    def __init__(self):
        self.trazas = []

    def trace(self, **kw):
        self.trazas.append(kw)


class FakeRepo:
    def __init__(self):
        self.custos = []

    def registrar_custo(self, custo):
        self.custos.append(custo)


def _modelo():
    a, lf, repo = FakeAnthropic(), FakeLangfuse(), FakeRepo()
    return ModeloAnthropic(a, lf, repo), a, lf, repo


def test_redator_usa_modelo_fuerte_y_adaptador_el_barato():
    m, a, _, _ = _modelo()
    m.gerar("p", agente="redator", post_id="1")
    m.gerar("p", agente="adaptador_linkedin", post_id="1")
    fuerte, barato = (c["model"] for c in a.llamadas)
    assert fuerte != barato
    assert PRECIOS[fuerte][0] > PRECIOS[barato][0]


def test_registra_costo_con_tokens_y_usd_de_la_tabla():
    m, a, _, repo = _modelo()
    assert m.gerar("p", agente="redator", post_id="7") == "hola"
    (c,) = repo.custos
    pin, pout = PRECIOS[a.llamadas[0]["model"]]
    assert (c.post_id, c.agente, c.tokens_entrada, c.tokens_saida) == ("7", "redator", 1000, 200)
    assert c.usd == (Decimal(1000) * pin + Decimal(200) * pout) / Decimal(1_000_000)
    assert c.modelo == a.llamadas[0]["model"]
    assert isinstance(c.criado_em, datetime)


def test_modelo_sin_precio_da_error_con_contexto():
    with pytest.raises(ValueError, match="modelo-x"):
        calcular_usd("modelo-x", 1, 1)


def test_error_de_la_api_lleva_agente_y_post_id():
    m, a, _, repo = _modelo()

    def boom(**kw):
        raise ConnectionError("red caida")

    a.create = boom
    with pytest.raises(RuntimeError, match=r"agente=redator post_id=9") as ei:
        m.gerar("p", agente="redator", post_id="9")
    assert isinstance(ei.value.__cause__, ConnectionError)
    assert repo.custos == []


def test_traza_lleva_post_id_agente_y_no_la_api_key():
    m, _, lf, _ = _modelo()
    m.gerar("p", agente="redator", post_id="7")
    (t,) = lf.trazas
    assert t["metadata"]["post_id"] == "7" and t["metadata"]["agente"] == "redator"
    assert KEY not in json.dumps(t, default=str)
