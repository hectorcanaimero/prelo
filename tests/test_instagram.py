"""Tests del publicador de Instagram (`prelo.publicadores.instagram`)."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic import SecretStr

from prelo.interfaces import Peca, Publicador
from prelo.publicadores.instagram import ErroPublicacaoInstagram, PublicadorInstagram

TOKEN = "ig-tok-secreto-999"
BASE = "https://graph.instagram.com/v21.0"
URLS = [f"https://r2.example/lamina-{i}.png" for i in range(3)]


def _peca() -> Peca:
    return Peca(
        id="peca-ig",
        post_id="post-1",
        canal="instagram",
        conteudo={"laminas": [], "prompt_imagem": "x", "url_blog": "https://b.example/p", "urls_imagens": URLS},
        violacoes=[],
        status="aprovada",
        decisao="aprovado",
    )


def _publicador() -> PublicadorInstagram:
    return PublicadorInstagram(token=SecretStr(TOKEN), user_id="1789", dormir=lambda _s: None)


def _campos(call: respx.models.Call) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(call.request.content.decode()).items()}


def _mock_fluxo(estados: list[str]) -> tuple[respx.Route, respx.Route, respx.Route]:
    ids = iter(["c1", "c2", "c3", "car"])
    criar = respx.post(f"{BASE}/1789/media").mock(side_effect=lambda r: httpx.Response(200, json={"id": next(ids)}))

    def _get(r: httpx.Request) -> httpx.Response:
        if "status_code" in str(r.url):
            return httpx.Response(200, json={"status_code": estados.pop(0)})
        return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/ABC/"})

    estado = respx.get(url__regex=rf"{BASE}/(car|999).*").mock(side_effect=_get)
    publicar = respx.post(f"{BASE}/1789/media_publish").mock(return_value=httpx.Response(200, json={"id": "999"}))
    return criar, estado, publicar


@respx.mock
def test_tres_imagenes_crean_tres_hijos_y_un_carousel_con_sus_ids() -> None:
    criar, _, _ = _mock_fluxo(["FINISHED"])
    pub: Publicador = _publicador()
    assert pub.canal == "instagram"
    pub.publicar(_peca())

    chamadas = [_campos(c) for c in criar.calls]
    assert len(chamadas) == 4
    for campos, url in zip(chamadas[:3], URLS, strict=True):
        assert campos["image_url"] == url
        assert campos["is_carousel_item"] == "true"
    assert chamadas[3]["media_type"] == "CAROUSEL"
    assert chamadas[3]["children"] == "c1,c2,c3"
    assert chamadas[3]["caption"]


@respx.mock
def test_espera_finished_antes_de_publicar() -> None:
    _, estado, publicar = _mock_fluxo(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
    _publicador().publicar(_peca())
    consultas = [c for c in estado.calls if "status_code" in str(c.request.url)]
    assert len(consultas) == 3
    assert _campos(publicar.calls.last)["creation_id"] == "car"


@respx.mock
def test_devuelve_permalink_e_id_externo() -> None:
    _mock_fluxo(["FINISHED"])
    pub = _publicador().publicar(_peca())
    assert pub.canal == "instagram"
    assert pub.peca_id == "peca-ig"
    assert pub.id_externo == "999"
    assert pub.url == "https://www.instagram.com/p/ABC/"


@respx.mock
def test_contenedor_en_error_levanta_sin_token(caplog: pytest.LogCaptureFixture) -> None:
    _, _, publicar = _mock_fluxo(["ERROR"])
    with caplog.at_level(logging.DEBUG), pytest.raises(ErroPublicacaoInstagram) as exc:
        _publicador().publicar(_peca())
    assert TOKEN not in str(exc.value)
    assert TOKEN not in caplog.text
    assert not publicar.called
