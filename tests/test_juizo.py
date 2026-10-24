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


class FakeHttp:
    """Responde en orden: un dict es el JSON de la respuesta, una excepción se lanza."""

    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def post(self, url, **kw):
        self.llamadas.append((url, kw))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: r)


PERGUNTAS = {"urgente": {"type": "noul", "instructions": "?"}}
JEV_OK = {
    "model": "typesafe/jev-1.13",
    "answers": {"urgente": {"type": "noul", "noul": 0.96}},
    "usage": {"input_tokens": 344, "output_tokens": 37, "cost": 0.000014448},
}


def _router(http, repo=None, modelos=("jev", "clef")):
    from prelo.juizo import JuizRouter

    return JuizRouter(http, "https://r.x/", KEY, list(modelos), repo or FakeRepo())


def test_router_usa_systemone_y_registra_costo():
    http, repo = FakeHttp(JEV_OK), FakeRepo()
    r = _router(http, repo).avaliar({"a": 1}, PERGUNTAS, post_id="p1")
    assert r.noul("urgente") == 0.96
    url, kw = http.llamadas[0]
    assert url == "https://r.x/v1/systemone"
    assert kw["json"] == {"model": "jev", "state": {"a": 1}, "questions": PERGUNTAS}
    assert repo.custos[0].modelo == "typesafe/jev-1.13"
    assert repo.custos[0].usd == Decimal("0.000014448")


def test_router_pasa_al_siguiente_modelo_y_desenvuelve_result():
    envuelto = {"result": {"model": "clef", "answers": {"urgente": {"type": "noul", "noul": 0.9}}}}
    http = FakeHttp(RuntimeError(KEY), envuelto)
    assert _router(http).avaliar({}, PERGUNTAS).noul("urgente") == 0.9
    assert [kw["json"]["model"] for _, kw in http.llamadas] == ["jev", "clef"]


def test_router_sin_respuestas_completas_es_indisponivel(caplog):
    http = FakeHttp({"error": {"message": "429"}}, RuntimeError(f"Bearer {KEY}"))
    with pytest.raises(JuizIndisponivel):
        _router(http).avaliar({}, PERGUNTAS)
    assert KEY not in caplog.text


def test_cadeia_cae_a_typesafe_cuando_9router_falla():
    from prelo.juizo import JuizEmCadeia

    typesafe = JuizTypeSafe(lambda: FakeClient(resp=_resp()), FakeRepo())
    cadeia = JuizEmCadeia(_router(FakeHttp(RuntimeError(), RuntimeError())), typesafe)
    assert cadeia.avaliar({}, {"x": {}}) is not None
