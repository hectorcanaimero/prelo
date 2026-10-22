from pathlib import Path

from prelo import revisao

REGRAS = {
    "bloqueia": {"empregadores": ["Acme", "Foo Bar"]},
    "aviso": {"cara_de_ia": ["vale ressaltar", "delve"], "caracteres": ["—"]},
}


def test_bloqueia_empregador_sin_importar_mayusculas():
    v = revisao.revisar("Trabajé en ACME durante dos años.", REGRAS)
    assert [(x.regra, x.nivel, x.termo) for x in v] == [("empregadores", "bloqueia", "Acme")]
    assert revisao.bloqueia(v)


def test_no_confunde_palabras_que_contienen_el_termino():
    assert revisao.revisar("Acmeísmo y Foo Barra no son la empresa.", REGRAS) == []


def test_avisos_no_bloquean():
    v = revisao.revisar("Vale ressaltar que a gente testou — e funcionou.", REGRAS)
    assert {x.termo for x in v} == {"vale ressaltar", "—"}
    assert not revisao.bloqueia(v)


def test_trecho_muestra_contexto():
    v = revisao.revisar("x" * 100 + " Acme " + "y" * 100, REGRAS)
    assert v[0].trecho.startswith("…") and v[0].trecho.endswith("…") and "Acme" in v[0].trecho


def test_suma_listas_de_varios_archivos(tmp_path: Path):
    (tmp_path / "a.toml").write_text('[bloqueia]\nempregadores = ["Uno"]\n', encoding="utf-8")
    (tmp_path / "b.toml").write_text('[bloqueia]\nempregadores = ["Dos"]\n', encoding="utf-8")
    regras = revisao.carregar_regras([tmp_path / "a.toml", tmp_path / "b.toml", tmp_path / "no-existe.toml"])
    assert regras["bloqueia"]["empregadores"] == ["Uno", "Dos"]


def test_marca_toml_del_repo_carga():
    regras = revisao.carregar_regras([revisao.RAIZ / "marca.toml"])
    assert regras["bloqueia"]["empregadores"]
    assert "—" in regras["aviso"]["caracteres"]
