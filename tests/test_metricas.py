from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from prelo.interfaces import Publicacao
from prelo.metricas import ErroLectura, LeitorInstagram, LeitorLinkedin, coletar

TOKEN = "tok-secreto-123"
URN = "urn:li:share:99"
LI = "https://api.linkedin.com/rest/socialActions/urn%3Ali%3Ashare%3A99"
IG = "https://graph.instagram.com/v21.0"


def _pub(canal, i, id_externo=None):
    return Publicacao(
        id=f"p{i}",
        peca_id="x",
        canal=canal,
        url="u",
        publicada_em=datetime.now(UTC),
        id_externo=id_externo or f"e{i}",
    )


@respx.mock
def test_linkedin_devuelve_reacciones_y_comentarios():
    respx.get(f"{LI}/comments").mock(
        return_value=httpx.Response(
            200, json={"elements": [{"actor": "urn:li:person:1", "message": {"text": "genial"}}]}
        )
    )
    respx.get(LI).mock(return_value=httpx.Response(200, json={"likesSummary": {"totalLikes": 12}}))
    m = LeitorLinkedin(SecretStr(TOKEN)).ler(_pub("linkedin", 1, URN))
    assert m == {"reacoes": 12, "comentarios": [{"autor": "urn:li:person:1", "texto": "genial"}]}
    assert respx.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"


@respx.mock
def test_instagram_devuelve_likes_y_comentarios_paginados():
    pag2 = f"{IG}/17900/comments?after=B"
    respx.get(f"{IG}/17900", params={"fields": "like_count,comments_count"}).mock(
        return_value=httpx.Response(200, json={"like_count": 5, "comments_count": 2})
    )
    respx.get(f"{IG}/17900/comments", params={"fields": "username,text"}).mock(
        return_value=httpx.Response(200, json={"data": [{"username": "ana", "text": "hola"}], "paging": {"next": pag2}})
    )
    respx.get(pag2).mock(return_value=httpx.Response(200, json={"data": [{"username": "bo", "text": "chao"}]}))
    m = LeitorInstagram(SecretStr(TOKEN)).ler(_pub("instagram", 1, "17900"))
    assert m["reacoes"] == 5
    assert m["comentarios"] == [{"autor": "ana", "texto": "hola"}, {"autor": "bo", "texto": "chao"}]


class RepoMem:
    def __init__(self, pubs):
        self.pubs, self.metricas = pubs, []

    def listar_publicacoes(self, *, canais):
        return [p for p in self.pubs if p.canal in canais]

    def salvar_metrica(self, publicacao_id, *, reacoes, comentarios):
        self.metricas.append(publicacao_id)


class Avisos:
    def __init__(self):
        self.textos = []

    def avisar(self, texto):
        self.textos.append(texto)


@respx.mock
def test_un_500_no_impide_guardar_las_demas_y_no_filtra_token():
    respx.get(url__startswith=f"{IG}/bad").mock(return_value=httpx.Response(500))
    respx.get(url__startswith=f"{IG}/ok").mock(return_value=httpx.Response(200, json={"like_count": 1, "data": []}))
    repo, aviso = RepoMem([_pub("instagram", 1, "bad"), _pub("instagram", 2, "ok")]), Avisos()
    assert coletar([LeitorInstagram(SecretStr(TOKEN))], repo, aviso) == 1
    assert repo.metricas == ["p2"]
    assert len(aviso.textos) == 1 and "p1" in aviso.textos[0]
    assert TOKEN not in aviso.textos[0]


@respx.mock
def test_linkedin_pagina_los_comentarios_hasta_una_pagina_corta():
    respx.get(LI).mock(return_value=httpx.Response(200, json={"likesSummary": {"totalLikes": 1}}))
    llena = [{"actor": f"a{i}", "message": {"text": "t"}} for i in range(LeitorLinkedin.PAGINA)]
    ruta = respx.get(f"{LI}/comments").mock(
        side_effect=[
            httpx.Response(200, json={"elements": llena}),
            httpx.Response(200, json={"elements": [{"actor": "ultimo", "message": {"text": "fin"}}]}),
        ]
    )
    m = LeitorLinkedin(SecretStr(TOKEN)).ler(_pub("linkedin", 1, URN))
    assert ruta.call_count == 2
    assert ruta.calls[1].request.url.params["start"] == str(LeitorLinkedin.PAGINA)
    assert len(m["comentarios"]) == LeitorLinkedin.PAGINA + 1
    assert m["comentarios"][-1] == {"autor": "ultimo", "texto": "fin"}


@respx.mock
def test_instagram_escapa_el_id_externo():
    ruta = respx.get(url__startswith=f"{IG}/a%2Fb").mock(return_value=httpx.Response(200, json={"like_count": 0}))
    LeitorInstagram(SecretStr(TOKEN)).ler(_pub("instagram", 1, "a/b?x=1"))
    assert ruta.called


@respx.mock
def test_fallo_sin_aviso_se_registra_en_el_log(caplog):
    respx.get(url__startswith=IG).mock(return_value=httpx.Response(500))
    repo = RepoMem([_pub("instagram", 1, "bad")])
    assert coletar([LeitorInstagram(SecretStr(TOKEN))], repo) == 0
    assert "p1" in caplog.text and TOKEN not in caplog.text


@respx.mock
def test_error_de_red_no_contiene_el_token():
    respx.get(url__startswith=IG).mock(side_effect=httpx.ConnectError(f"fallo https://x?access_token={TOKEN}"))
    with pytest.raises(ErroLectura) as e:
        LeitorInstagram(SecretStr(TOKEN)).ler(_pub("instagram", 1))
    assert TOKEN not in str(e.value)
