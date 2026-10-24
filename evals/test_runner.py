"""Tests del runner de evals, con agentes y juez falsos."""

import json
from decimal import Decimal

import run

from prelo.marca import Regras

REGRAS = Regras(bloqueia=["AcmeCorp"], frases=[], padroes=[])
CASO = {"id": "c1", "tema": "t", "fontes": [{"url": "u", "titulo": "T", "trecho": "x"}]}


def _suite(raiz, nome, umbrais=None, casos=(CASO,)):
    d = raiz / nome
    d.mkdir()
    cfg = {"umbrais": umbrais or {"fidelidade": 0.8, "estilo": 0.7}, "rubrica": "r", "casos": list(casos)}
    (d / "casos.json").write_text(json.dumps(cfg))


def _juiz(fid=1.0, est=1.0):
    return lambda metrica, texto, caso, rubrica: fid if metrica == "fidelidade" else est


def _correr(raiz, agentes, juiz, capsys):
    code = run.main(raiz, agentes, juiz, REGRAS, lambda: Decimal("0.0123"))
    return code, capsys.readouterr().out


def test_sobre_el_umbral_sale_0(tmp_path, capsys):
    _suite(tmp_path, "linkedin")
    code, out = _correr(tmp_path, {"linkedin": lambda c: "texto limpio"}, _juiz(), capsys)
    assert code == 0
    assert "USD 0.0123" in out  # costo de la corrida


def test_bajo_el_umbral_sale_1_y_nombra_la_metrica(tmp_path, capsys):
    _suite(tmp_path, "linkedin")
    code, out = _correr(tmp_path, {"linkedin": lambda c: "texto"}, _juiz(est=0.2), capsys)
    assert code == 1
    assert "FALLA linkedin/estilo" in out
    assert "FALLA linkedin/fidelidade" not in out


def test_violacion_de_marca_en_un_caso_falla(tmp_path, capsys):
    _suite(tmp_path, "linkedin", casos=[CASO, {**CASO, "id": "c2"}])
    agente = lambda c: "trabajo en AcmeCorp" if c["id"] == "c2" else "ok"
    code, out = _correr(tmp_path, {"linkedin": agente}, _juiz(), capsys)
    assert code == 1
    assert "FALLA linkedin/marca" in out


def test_descubre_un_subdirectorio_nuevo(tmp_path, capsys):
    _suite(tmp_path, "linkedin")
    _suite(tmp_path, "nuevo")
    vistos = []
    agentes = {"linkedin": lambda c: "a", "nuevo": lambda c: vistos.append(c["id"]) or "b"}
    code, out = _correr(tmp_path, agentes, _juiz(), capsys)
    assert code == 0 and vistos == ["c1"]
    assert "nuevo/estilo" in out


def test_casos_reales_de_linkedin():
    cfg = json.loads((run.RAIZ / "linkedin" / "casos.json").read_text())
    assert len(cfg["casos"]) >= 5
