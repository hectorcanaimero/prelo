"""Publicador de LinkedIn via LinkedIn Posts API."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr

from prelo.config import Settings
from prelo.interfaces import Canal, Peca, Publicacao

logger = logging.getLogger(__name__)

LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_FEED_UPDATE_URL = "https://www.linkedin.com/feed/update"
LINKEDIN_API_VERSION = "202401"


class ErroPublicacaoLinkedin(RuntimeError):
    """Error devuelto por la API de LinkedIn al publicar."""

    def __init__(self, codigo: int, mensagem: str) -> None:
        self.codigo = codigo
        self.status_code = codigo
        self.mensagem = mensagem
        super().__init__(f"LinkedIn API error {codigo}: {mensagem}")


def _ocultar_token(texto: str, token: str) -> str:
    if token and token in texto:
        return texto.replace(token, "***")
    return texto


class _FiltroSemToken(logging.Filter):
    """Filtro de logging que garantiza que el token nunca aparezca en los logs."""

    def __init__(self, token: SecretStr) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        segredo = self._token.get_secret_value()
        if not segredo:
            return True
        if isinstance(record.msg, str) and segredo in record.msg:
            record.msg = _ocultar_token(record.msg, segredo)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _ocultar_token(v, segredo) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _ocultar_token(a, segredo) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def _extrair_mensagem_erro(response: httpx.Response, token: str) -> str:
    mensagem = ""
    if response.content:
        try:
            body = response.json()
            if isinstance(body, dict):
                for chave in ("message", "error_description", "error"):
                    valor = body.get(chave)
                    if isinstance(valor, str) and valor.strip():
                        mensagem = valor.strip()
                        break
        except ValueError:
            pass
    if not mensagem:
        mensagem = response.text.strip() or response.reason_phrase or "Erro desconhecido"
    return _ocultar_token(mensagem, token)


def _extrair_texto(peca: Peca) -> str:
    """Extrae el texto a publicar del contenido de `peca`."""
    conteudo: Any = peca.conteudo
    if isinstance(conteudo, str):
        return conteudo

    if isinstance(conteudo, dict):
        for chave in ("texto", "corpo", "commentary"):
            valor = conteudo.get(chave)
            if isinstance(valor, str) and valor:
                return valor

        pt = conteudo.get("pt")
        if isinstance(pt, str) and pt:
            return pt
        if isinstance(pt, dict):
            for chave in ("corpo", "texto", "resumo", "titulo"):
                valor = pt.get(chave)
                if isinstance(valor, str) and valor:
                    return valor

        for valor in conteudo.values():
            if isinstance(valor, str) and valor:
                return valor
            if isinstance(valor, dict):
                for subchave in ("corpo", "texto", "resumo", "titulo"):
                    subvalor = valor.get(subchave)
                    if isinstance(subvalor, str) and subvalor:
                        return subvalor

    return ""


class PublicadorLinkedin:
    """Publicador para el canal `linkedin` usando LinkedIn Posts API."""

    canal: Canal = "linkedin"

    def __init__(
        self,
        settings: Settings | SecretStr | str | None = None,
        autor: str | None = None,
        *,
        token: SecretStr | str | None = None,
        author_urn: str | None = None,
        client: httpx.Client | None = None,
        api_url: str = LINKEDIN_POSTS_URL,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(settings, Settings):
            cfg_token = settings.LINKEDIN_TOKEN
            cfg_autor = settings.LINKEDIN_AUTHOR_URN
        elif isinstance(settings, (SecretStr, str)):
            cfg_token = settings if isinstance(settings, SecretStr) else SecretStr(settings)
            cfg_autor = ""
        else:
            cfg = Settings()
            cfg_token = cfg.LINKEDIN_TOKEN
            cfg_autor = cfg.LINKEDIN_AUTHOR_URN

        if token is not None:
            self._token: SecretStr = token if isinstance(token, SecretStr) else SecretStr(token)
        else:
            self._token = cfg_token

        self._autor: str = autor or author_urn or cfg_autor
        self._client = client
        self._api_url = api_url
        self._reloj = reloj or (lambda: datetime.now(UTC))

        filtro = _FiltroSemToken(self._token)
        for nome_logger in (__name__, "httpx", "httpcore"):
            logging.getLogger(nome_logger).addFilter(filtro)

    def __repr__(self) -> str:
        return f"PublicadorLinkedin(canal={self.canal!r}, autor={self._autor!r}, token=SecretStr('**********'))"

    def publicar(self, peca: Peca) -> Publicacao:
        """Publica el texto de `peca` en LinkedIn y devuelve la `Publicacao`."""
        texto = _extrair_texto(peca)
        segredo = self._token.get_secret_value()
        headers = {
            "Authorization": f"Bearer {segredo}",
            "LinkedIn-Version": LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": self._autor,
            "commentary": texto,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        logger.info("Publicando peça %s no LinkedIn (autor=%s)", peca.id, self._autor)

        try:
            if self._client is not None:
                response = self._client.post(self._api_url, headers=headers, json=payload)
            else:
                with httpx.Client() as client:
                    response = client.post(self._api_url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            mensagem = _ocultar_token(str(exc), segredo)
            logger.error("Erro de rede ao publicar peça %s no LinkedIn: %s", peca.id, mensagem)
            raise ErroPublicacaoLinkedin(0, mensagem) from None

        if response.status_code >= 400:
            mensagem = _extrair_mensagem_erro(response, segredo)
            logger.error(
                "Erro da API do LinkedIn ao publicar peça %s (status=%d): %s",
                peca.id,
                response.status_code,
                mensagem,
            )
            raise ErroPublicacaoLinkedin(response.status_code, mensagem)

        id_externo = response.headers.get("x-restli-id", "").strip()
        url_post = ""
        if response.content:
            try:
                body = response.json()
                if isinstance(body, dict):
                    if not id_externo and isinstance(body.get("id"), str):
                        id_externo = body["id"].strip()
                    if isinstance(body.get("url"), str) and body["url"].strip():
                        url_post = body["url"].strip()
            except ValueError:
                pass

        if not url_post:
            url_post = f"{LINKEDIN_FEED_UPDATE_URL}/{id_externo}"

        logger.info("Peça %s publicada no LinkedIn com id_externo=%s", peca.id, id_externo)

        return Publicacao(
            id=str(uuid4()),
            peca_id=peca.id,
            canal=self.canal,
            url=url_post,
            publicada_em=self._reloj(),
            id_externo=id_externo,
        )


LinkedInPublicador = PublicadorLinkedin
PublicadorLinkedIn = PublicadorLinkedin

__all__ = [
    "LINKEDIN_API_VERSION",
    "LINKEDIN_FEED_UPDATE_URL",
    "LINKEDIN_POSTS_URL",
    "ErroPublicacaoLinkedin",
    "LinkedInPublicador",
    "PublicadorLinkedIn",
    "PublicadorLinkedin",
]
