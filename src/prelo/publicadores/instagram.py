"""Publicador de Instagram (carrusel) via Instagram Graph API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr

from prelo.config import Settings
from prelo.interfaces import Canal, Peca, Publicacao

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"


class ErroPublicacaoInstagram(RuntimeError):
    """Error al publicar en Instagram. Su mensaje nunca contiene el token."""


class PublicadorInstagram:
    """Publicador para el canal `instagram`: carrusel con `conteudo["urls_imagens"]` (URLs de R2)."""

    canal: Canal = "instagram"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        token: SecretStr | str | None = None,
        user_id: str | None = None,
        client: httpx.Client | None = None,
        espera_max: float = 60.0,
        intervalo: float = 2.0,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        cfg = settings or Settings()
        tok = token if token is not None else cfg.IG_TOKEN
        self._token = tok if isinstance(tok, SecretStr) else SecretStr(tok)
        self._user_id = user_id or cfg.IG_USER_ID
        self._client = client
        self._espera_max = espera_max
        self._intervalo = intervalo
        self._dormir = dormir
        self._reloj = reloj or (lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return f"PublicadorInstagram(canal={self.canal!r}, user_id={self._user_id!r}, token=SecretStr('**********'))"

    def _limpar(self, texto: str) -> str:
        segredo = self._token.get_secret_value()
        return texto.replace(segredo, "***") if segredo else texto

    def _chamar(self, http: httpx.Client, metodo: str, caminho: str, **campos: str) -> dict[str, Any]:
        """Llama a la Graph API. El token va en la cabecera: ni la URL (que httpx loguea) ni los errores lo llevan."""
        cabecera = {"Authorization": f"Bearer {self._token.get_secret_value()}"}
        try:
            if metodo == "POST":
                resp = http.post(f"{GRAPH_URL}/{caminho}", data=campos, headers=cabecera)
            else:
                resp = http.get(f"{GRAPH_URL}/{caminho}", params=campos, headers=cabecera)
        except httpx.HTTPError as exc:
            raise ErroPublicacaoInstagram(f"Red: {self._limpar(str(exc))}") from None
        if resp.status_code >= 400:
            raise ErroPublicacaoInstagram(
                f"Instagram API {resp.status_code} en {caminho}: {self._limpar(resp.text.strip())}"
            )
        return resp.json()  # type: ignore[no-any-return]

    def _esperar_finished(self, http: httpx.Client, contenedor: str) -> None:
        espera = 0.0
        while True:
            estado = self._chamar(http, "GET", contenedor, fields="status_code").get("status_code")
            if estado == "FINISHED":
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErroPublicacaoInstagram(f"El contenedor {contenedor} terminó en estado {estado}")
            if espera >= self._espera_max:
                raise ErroPublicacaoInstagram(f"El contenedor {contenedor} sigue en {estado} tras {espera:.0f}s")
            self._dormir(self._intervalo)
            espera += self._intervalo

    def publicar(self, peca: Peca) -> Publicacao:
        """Publica `peca` como carrusel y devuelve la `Publicacao` con el permalink."""
        conteudo: dict[str, Any] = peca.conteudo if isinstance(peca.conteudo, dict) else {}
        urls: list[str] = conteudo.get("urls_imagens") or []
        if len(urls) < 2:  # Instagram exige entre 2 y 10 imágenes por carrusel
            raise ErroPublicacaoInstagram(f"Carrusel de la pieza {peca.id} necesita 2-10 imágenes, hay {len(urls)}")
        legenda = conteudo.get("legenda") or "\n".join(
            p for p in ((conteudo.get("laminas") or [{}])[0].get("titulo"), conteudo.get("url_blog")) if p
        )

        logger.info("Publicando peça %s no Instagram (%d imagens)", peca.id, len(urls))
        with self._client or httpx.Client() as http:
            ruta = f"{self._user_id}/media"
            filhos = [self._chamar(http, "POST", ruta, image_url=u, is_carousel_item="true")["id"] for u in urls]
            carrossel = self._chamar(
                http, "POST", ruta, media_type="CAROUSEL", children=",".join(filhos), caption=legenda
            )["id"]
            self._esperar_finished(http, carrossel)
            id_externo = self._chamar(http, "POST", f"{self._user_id}/media_publish", creation_id=carrossel)["id"]
            permalink = self._chamar(http, "GET", id_externo, fields="permalink")["permalink"]

        logger.info("Peça %s publicada no Instagram com id_externo=%s", peca.id, id_externo)
        return Publicacao(
            id=str(uuid4()),
            peca_id=peca.id,
            canal=self.canal,
            url=permalink,
            publicada_em=self._reloj(),
            id_externo=id_externo,
        )


__all__ = ["GRAPH_URL", "ErroPublicacaoInstagram", "PublicadorInstagram"]
