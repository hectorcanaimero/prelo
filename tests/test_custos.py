import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from prelo.config import Settings
from prelo.custos import PRECIOS, calcular_usd
from prelo.modelo import ModeloRouter

KEY = "sk-router-super-secret"


def _chunk(texto=None, usage=None, model="claude-sonnet-5-5"):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=texto))] if texto is not None else []
    return SimpleNamespace(model=model, choices=choices, usage=usage)


class FakeOpenAI:
    """Imita `client.chat.completions.create(stream=True)`: devuelve chunks y al final el uso."""

    api_key = KEY

    def __init__(self, model="claude-sonnet-5-5"):
        self.llamadas, self.model = [], model
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.llamadas.append(kw)
        uso = SimpleNamespace(prompt_tokens=1000, completion_tokens=200)
        return iter(
            [_chunk("ho", model=self.model), _chunk("la", model=self.model), _chunk(usage=uso, model=self.model)]
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


def _modelo(**kw):
    a, lf, repo = FakeOpenAI(), FakeLangfuse(), FakeRepo()
    return ModeloRouter(a, lf, repo, **kw), a, lf, repo


def test_cada_agente_pide_su_combo_salvo_los_renombrados():
    m, a, _, _ = _modelo(modelo_por_agente={"redator": "redactor"})
    m.gerar("p", agente="redator", post_id="1")
    m.gerar("p", agente="adaptador_linkedin", post_id="1")
    assert [c["model"] for c in a.llamadas] == ["redactor", "adaptador_linkedin"]
    assert all(c["stream"] is True and c["stream_options"] == {"include_usage": True} for c in a.llamadas)


def test_junta_el_stream_y_registra_costo_con_el_modelo_que_respondio():
    m, _, _, repo = _modelo()
    assert m.gerar("p", agente="redator", post_id="7") == "hola"
    (c,) = repo.custos
    pin, pout = PRECIOS["claude-sonnet-5-5"]
    assert (c.post_id, c.agente, c.modelo, c.tokens_entrada, c.tokens_saida) == (
        "7",
        "redator",
        "claude-sonnet-5-5",
        1000,
        200,
    )
    assert c.usd == (Decimal(1000) * pin + Decimal(200) * pout) / Decimal(1_000_000)
    assert isinstance(c.criado_em, datetime)


def test_modelo_sin_precio_cuenta_cero_y_con_prefijo_usa_la_tabla():
    assert calcular_usd("gemini-3.8-flash-n", 1000, 1000) == Decimal(0)
    assert calcular_usd("cc/claude-sonnet-5-5", 1_000_000, 0) == PRECIOS["claude-sonnet-5-5"][0]


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


def test_prelo_modelos_se_lee_como_mapa(monkeypatch):
    monkeypatch.setenv("PRELO_MODELOS", "redator=redactor, tradutor = traductor,mal")
    assert Settings(_env_file=None).PRELO_MODELOS == {"redator": "redactor", "tradutor": "traductor"}


def test_precios_desde_config_y_un_solo_aviso(caplog):
    from prelo.custos import cargar_precios

    cargar_precios("gpt-6-luna=1.25/10, mal, otro=1")
    assert calcular_usd("cx/gpt-6-luna", 1_000_000, 100_000) == Decimal("2.25")
    calcular_usd("modelo-nuevo-x", 1, 1)
    calcular_usd("modelo-nuevo-x", 1, 1)
    assert caplog.text.count("modelo-nuevo-x") == 1
