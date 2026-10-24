from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from prelo.config import Settings
from prelo.juizo import JuizIndisponivel, JuizTypeSafe

KEY = "ts-super-secret"


class FakeClient:
    def __init__(self, resp=None, error=None):
        self.resp, self.error, self.llamadas = resp, error, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def system_one(self, *, state, questions):
        self.llamadas.append((state, questions))
        if self.error:
            raise self.error
        return self.resp


class FakeRepo:
    def __init__(self):
        self.custos = []

    def registrar_custo(self, custo):
        self.custos.append(custo)


def _resp():
    return SimpleNamespace(
        model="jev-latest",
        usage=SimpleNamespace(input_tokens=120, output_tokens=12),
        answers={
            "gancho": SimpleNamespace(type="noul", noul=0.8),
            "tom": SimpleNamespace(type="choice", choice="directo"),
            "aprobacao": SimpleNamespace(type="score", score=3.5),
        },
    )


def _juiz(client):
    repo = FakeRepo()
    return JuizTypeSafe(lambda: client, repo), repo


def test_noul_choice_y_score_por_nombre_propio():
    j, _ = _juiz(FakeClient(_resp()))
    r = j.avaliar({}, {"gancho": object(), "tom": object(), "aprobacao": object()}, post_id="p1")
    assert r.noul("gancho") == 0.8
    assert r.choice("tom") == "directo"
    assert r.score("aprobacao") == 3.5


def test_envia_state_y_questions_tal_cual():
    c = FakeClient(_resp())
    j, _ = _juiz(c)
    q = {"gancho": object()}
    j.avaliar({"texto": "hola"}, q, post_id="p1")
    assert c.llamadas == [({"texto": "hola"}, q)]


def test_error_del_cliente_levanta_juiz_indisponivel():
    j, repo = _juiz(FakeClient(error=ConnectionError("red")))
    with pytest.raises(JuizIndisponivel) as ei:
        j.avaliar({}, {}, post_id="p1")
    assert isinstance(ei.value.__cause__, ConnectionError)
    assert repo.custos == []


def test_registra_costo_con_agente_juizo():
    j, repo = _juiz(FakeClient(_resp()))
    j.avaliar({}, {}, post_id="p1")
    (c,) = repo.custos
    assert (c.post_id, c.agente, c.modelo, c.tokens_entrada, c.tokens_saida) == ("p1", "juizo", "jev-latest", 120, 12)
    assert isinstance(c.usd, Decimal) and isinstance(c.criado_em, datetime)


def test_sin_post_id_no_registra_costo_pero_devuelve_respuestas():
    j, repo = _juiz(FakeClient(_resp()))
    r = j.avaliar({}, {"gancho": object()})
    assert r.noul("gancho") == 0.8
    assert repo.custos == []


def test_repr_de_la_configuracion_no_contiene_la_clave():
    s = Settings(TYPESAFE_API_KEY=KEY)
    assert s.TYPESAFE_API_KEY.get_secret_value() == KEY
    assert KEY not in repr(s) and KEY not in str(s)
