"""Tests del publicador de LinkedIn (`prelo.publicadores.linkedin`)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from pydantic import SecretStr

from prelo.config import Settings
from prelo.interfaces import Peca, Publicacao, Publicador
from prelo.publicadores.linkedin import (
    LINKEDIN_POSTS_URL,
    ErroPublicacaoLinkedin,
    PublicadorLinkedin,
)


def _peca_linkedin(texto: str = "Post sobre agentes em produção.") -> Peca:
    return Peca(
        id="peca-1",
        post_id="post-1",
        canal="linkedin",
        conteudo={"pt": {"titulo": "Agentes", "resumo": "Resumo", "corpo": texto}},
        violacoes=[],
        status="aprovada",
        decisao="aprovado",
    )


@respx.mock
def test_publicacao_correta_envia_texto_e_autor_e_retorna_publicacao() -> None:
    """Una publicación correcta manda el texto y el autor esperados y devuelve una Publicacao con URL e id_externo."""
    id_externo = "urn:li:share:7250000000000000001"
    rota = respx.post(LINKEDIN_POSTS_URL).mock(
        return_value=httpx.Response(
            status_code=201,
            headers={"x-restli-id": id_externo},
            json={"id": id_externo},
        )
    )

    settings = Settings(
        LINKEDIN_TOKEN=SecretStr("tok-secreto-123"),
        LINKEDIN_AUTHOR_URN="urn:li:person:hector123",
    )
    publicador: Publicador = PublicadorLinkedin(settings)
    assert publicador.canal == "linkedin"

    peca = _peca_linkedin("Post sobre LangGraph e agentes em pt-BR.")
    pub = publicador.publicar(peca)

    assert rota.called
    request = rota.calls.last.request
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["author"] == "urn:li:person:hector123"
    assert payload["commentary"] == "Post sobre LangGraph e agentes em pt-BR."
    assert payload["lifecycleState"] == "PUBLISHED"
    assert payload["visibility"] == "PUBLIC"

    assert isinstance(pub, Publicacao)
    assert pub.peca_id == "peca-1"
    assert pub.canal == "linkedin"
    assert pub.id_externo == id_externo
    assert id_externo in pub.url
    assert pub.url.startswith("https://www.linkedin.com/feed/update/")


@respx.mock
def test_erro_401_levanta_excecao_com_codigo_e_mensagem_sem_token() -> None:
    """Un 401 levanta un error con el código y el mensaje que no contiene el token."""
    token_secreto = "li-super-secret-token-999"
    respx.post(LINKEDIN_POSTS_URL).mock(
        return_value=httpx.Response(
            status_code=401,
            json={"status": 401, "message": f"Invalid access token {token_secreto}"},
        )
    )

    settings = Settings(
        LINKEDIN_TOKEN=SecretStr(token_secreto),
        LINKEDIN_AUTHOR_URN="urn:li:person:hector123",
    )
    publicador = PublicadorLinkedin(settings)

    with pytest.raises(ErroPublicacaoLinkedin) as exc_info:
        publicador.publicar(_peca_linkedin())

    assert exc_info.value.codigo == 401
    assert exc_info.value.status_code == 401
    erro_str = str(exc_info.value)
    erro_repr = repr(exc_info.value)
    assert "401" in erro_str
    assert "Invalid access token" in erro_str
    assert token_secreto not in erro_str
    assert token_secreto not in erro_repr
    assert token_secreto not in exc_info.value.mensagem


@respx.mock
def test_cabecalho_autorizacao_leva_token_mas_nenhum_log_o_mostra(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """La cabecera de autorización lleva el token pero ningún log lo muestra."""
    token_secreto = "li-secret-bearer-token-xyz-789"
    id_externo = "urn:li:share:7250000000000000002"
    rota = respx.post(LINKEDIN_POSTS_URL).mock(
        return_value=httpx.Response(
            status_code=201,
            headers={"x-restli-id": id_externo},
            json={"id": id_externo},
        )
    )

    settings = Settings(
        LINKEDIN_TOKEN=SecretStr(token_secreto),
        LINKEDIN_AUTHOR_URN="urn:li:person:hector123",
    )
    publicador = PublicadorLinkedin(settings)

    with caplog.at_level(logging.DEBUG):
        publicador.publicar(_peca_linkedin("Texto publicado sem vazar token."))

    assert rota.called
    request = rota.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {token_secreto}"

    # Verifica que el publicador registra actividad en logs pero jamás expone el token.
    assert any(r.name.startswith("prelo") for r in caplog.records)
    assert token_secreto not in caplog.text
    for record in caplog.records:
        assert token_secreto not in record.getMessage()
    assert token_secreto not in repr(publicador)
