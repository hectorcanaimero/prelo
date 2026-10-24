"""Worker diario de métricas (FR-15): reacciones y comentarios de cada publicación de LinkedIn e Instagram."""

from __future__ import annotations

import logging
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from prelo.interfaces import Aviso, Publicacao

log = logging.getLogger(__name__)

CANAIS = ("linkedin", "instagram")


class Leitor(Protocol):
    canal: str

    def ler(self, publicacao: Publicacao) -> dict[str, Any]:
        """Devuelve `{"reacoes": int, "comentarios": list}`."""
        ...


class ErroLectura(RuntimeError):
    """Fallo al leer métricas; el mensaje nunca incluye el token."""


class _Http:
    """GET con el token en cabecera; todo fallo sale como `ErroLectura` sin el token."""

    def __init__(
        self, token: SecretStr | str, client: httpx.Client | None, extra: dict[str, str] | None = None
    ) -> None:
        self._token = token.get_secret_value() if isinstance(token, SecretStr) else token
        self._client = client or httpx.Client(timeout=30)
        self._headers = {"Authorization": f"Bearer {self._token}", **(extra or {})}

    def get(self, url: str, **params: str) -> dict[str, Any]:
        try:
            r = self._client.get(url, params=params or None, headers=self._headers)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = f"{type(exc).__name__}: {exc}"
            raise ErroLectura(msg.replace(self._token, "***") if self._token else msg) from None


class LeitorLinkedin:
    canal = "linkedin"
    URL = "https://api.linkedin.com/rest/socialActions"
    PAGINA = 50

    def __init__(self, token: SecretStr | str, client: httpx.Client | None = None) -> None:
        self._http = _Http(token, client, {"LinkedIn-Version": "202401", "X-Restli-Protocol-Version": "2.0.0"})

    def ler(self, publicacao: Publicacao) -> dict[str, Any]:
        base = f"{self.URL}/{quote(publicacao.id_externo, safe='')}"
        reacoes = self._http.get(base).get("likesSummary", {}).get("totalLikes", 0)
        comentarios: list[dict[str, str]] = []
        inicio = 0
        while True:
            pagina = self._http.get(f"{base}/comments", start=str(inicio), count=str(self.PAGINA))
            elementos = pagina.get("elements", [])
            comentarios += [
                {"autor": e.get("actor", ""), "texto": e.get("message", {}).get("text", "")} for e in elementos
            ]
            if len(elementos) < self.PAGINA:
                return {"reacoes": reacoes, "comentarios": comentarios}
            inicio += self.PAGINA


class LeitorInstagram:
    canal = "instagram"
    URL = "https://graph.facebook.com/v21.0"

    def __init__(self, token: SecretStr | str, client: httpx.Client | None = None) -> None:
        self._http = _Http(token, client)

    def ler(self, publicacao: Publicacao) -> dict[str, Any]:
        base = f"{self.URL}/{quote(publicacao.id_externo, safe='')}"
        reacoes = self._http.get(base, fields="like_count,comments_count").get("like_count", 0)
        comentarios: list[dict[str, str]] = []
        pagina = self._http.get(f"{base}/comments", fields="username,text")
        while True:
            comentarios += [
                {"autor": c.get("username", ""), "texto": c.get("text", "")} for c in pagina.get("data", [])
            ]
            siguiente = pagina.get("paging", {}).get("next")
            if not siguiente:
                return {"reacoes": reacoes, "comentarios": comentarios}
            pagina = self._http.get(siguiente)


def coletar(leitores: list[Leitor], repo: Any, aviso: Aviso | None = None) -> int:
    """Guarda una fila por publicación; salta las que no tienen lector de su canal. Devuelve las filas guardadas.

    Si un lector falla, avisa (sin token) y sigue con las demás publicaciones."""
    por_canal = {leitor.canal: leitor for leitor in leitores}
    n = 0
    for pub in repo.listar_publicacoes(canais=CANAIS):
        leitor = por_canal.get(pub.canal)
        if leitor is None:
            continue
        try:
            m = leitor.ler(pub)
        except ErroLectura as exc:
            texto = f"Métricas: no se pudo leer {pub.canal} {pub.id}: {exc}"
            if aviso:
                aviso.avisar(texto)
            else:
                log.warning(texto)
            continue
        repo.salvar_metrica(pub.id, reacoes=m["reacoes"], comentarios=m["comentarios"])
        n += 1
    return n
