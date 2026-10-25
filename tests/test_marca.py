from prelo.config import Settings
from prelo.marca import Regras, carregar_regras, revisar


def _regras(*nomes: str):
    return carregar_regras(Settings(PRELO_BLOQUEIA=list(nomes)))


def _fonte(trecho: str):
    return {"url": "https://x.test", "titulo": "t", "trecho": trecho}


def _regra(vs):
    return [v["regra"] for v in vs]


def test_empregador():
    vs = revisar("trabajé en ACME", [], _regras("ACME"))
    assert _regra(vs) == ["empregador"]
    assert vs[0]["trecho"] == "ACME"


def test_empregador_acento_e_caixa():
    vs = revisar("trabajé en Acmé", [], _regras("ACME"))
    assert _regra(vs) == ["empregador"]
    assert vs[0]["trecho"] == "Acmé"


def test_empregador_palavra_completa():
    assert revisar("el acmeísmo es una escuela", [], _regras("ACME")) == []


def test_frase_ia():
    vs = revisar("Hoy vamos a sumérgete en el tema", [], _regras())
    assert _regra(vs) == ["frase_ia"]
    assert vs[0]["trecho"] == "sumérgete en"


def test_cifra_sem_fonte():
    vs = revisar("creció un 40%", [], _regras())
    assert _regra(vs) == ["cifra_sem_fonte"]
    assert vs[0]["trecho"] == "40%"


def test_cifra_com_fonte():
    assert revisar("creció un 40%", [_fonte("subió 40% en 2023")], _regras()) == []


def test_data_igual_cifra():
    assert _regra(revisar("en 2024", [], _regras())) == ["cifra_sem_fonte"]
    assert revisar("en 2024", [_fonte("datos de 2024")], _regras()) == []


def test_cifra_con_otro_separador_decimal_que_la_fuente():
    assert revisar("Na pesquisa, 57,3% já tinham agentes", [_fonte("57.3% of respondents")], _regras()) == []
    assert revisar("cayó 12 %", [_fonte("fell 12%")], _regras()) == []


def test_numero_de_lista_no_es_cifra_pero_en_la_frase_si():
    texto = "Pasos:\n1. Define\n  4) Mide la variación\nSon 4 pasos"
    vs = revisar(texto, [], _regras())
    assert [v["trecho"] for v in vs] == ["4"]


def test_texto_limpo():
    assert revisar("Un texto sencillo.", [], _regras()) == []


def test_bloqueia_vazio():
    r = _regras()
    assert isinstance(r, Regras)
    assert r.bloqueia == []
    assert revisar("trabajé en ACME", [], r) == []
