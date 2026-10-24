"""Sondeo del deploy del blog según D10: espera a que la URL responda 200 para reanudar."""

from __future__ import annotations

import inspect
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from prelo.interfaces import Aviso, Peca, Repositorio

try:
    from prelo import mdx
except ImportError:
    mdx = None

log = logging.getLogger(__name__)

URL_BASE_BLOG = "https://guria.lat/blog"
INTERVALOS_DEFECTO = (10.0, 20.0, 40.0, 80.0, 160.0)


def _slugify(texto: str) -> str:
    """Convierte un texto a slug url-friendly."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    return re.sub(r"[-\s]+", "-", texto)


def _dormir(reloj: Any, segundos: float) -> None:
    """Espera `segundos` usando el reloj inyectado o time.sleep."""
    if hasattr(reloj, "dormir"):
        reloj.dormir(segundos)
    elif hasattr(reloj, "sleep"):
        reloj.sleep(segundos)
    elif callable(reloj):
        try:
            reloj(segundos)
        except TypeError:
            pass
    else:
        time.sleep(segundos)


def _enviar_aviso(aviso: Any, texto: str) -> None:
    """Envía un aviso a través de la interfaz Aviso o un callable."""
    if hasattr(aviso, "avisar"):
        aviso.avisar(texto)
    elif callable(aviso):
        aviso(texto)


def _chamar_retomar(retomar: Callable[..., Any], post_id: str, url: str) -> None:
    """Llama a `retomar` adaptándose a firmas con `url_blog` por keyword o posicional."""
    try:
        sig = inspect.signature(retomar)
        params = list(sig.parameters.values())
        if (
            len(params) == 2
            and params[1].name not in ("url_blog", "kwargs")
            and params[1].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ):
            retomar(post_id, url)
            return
        retomar(post_id, url_blog=url)
    except TypeError:
        retomar(post_id, url)


def obter_url_blog(post_id: str, peca: Peca | None = None, tema: str | None = None) -> str:
    """Determina la URL pública esperada en guria.lat/blog para el post."""
    if mdx is not None:
        if hasattr(mdx, "url_esperada"):
            return mdx.url_esperada(post_id, peca)
        if hasattr(mdx, "url_blog"):
            try:
                return str(mdx.url_blog(peca.conteudo if peca else post_id))
            except (TypeError, ValueError, AttributeError):
                try:
                    return str(mdx.url_blog(post_id))
                except (TypeError, ValueError, AttributeError):
                    log.debug("No se pudo obtener url_blog desde mdx")
        if hasattr(mdx, "slug"):
            try:
                slug = mdx.slug(tema or (peca.conteudo if peca else post_id))
                return f"{URL_BASE_BLOG}/{slug}"
            except (TypeError, ValueError, AttributeError):
                log.debug("No se pudo obtener slug desde mdx")

    slug = ""
    if peca and isinstance(peca.conteudo, dict):
        if "slug" in peca.conteudo:
            slug = str(peca.conteudo["slug"])
        elif "es" in peca.conteudo and isinstance(peca.conteudo["es"], dict):
            es = peca.conteudo["es"]
            slug = str(es.get("slug") or _slugify(str(es.get("titulo", ""))))
        elif "titulo" in peca.conteudo:
            slug = _slugify(str(peca.conteudo["titulo"]))

    if not slug and tema:
        slug = _slugify(tema)
    if not slug:
        slug = _slugify(post_id)

    return f"{URL_BASE_BLOG}/{slug}"


class DeployBlog:
    """Vigila el deploy del blog y reanuda los posts pausados en `esperar_deploy`."""

    def __init__(
        self,
        cliente: httpx.Client,
        retomar: Callable[..., Any],
        aviso: Aviso | Callable[[str], None],
        reloj: Any,
        repo: Repositorio | None = None,
        *,
        limite: int = 5,
        intervalos: Sequence[float] | None = None,
    ) -> None:
        self.cliente = cliente
        self.retomar = retomar
        self.aviso = aviso
        self.reloj = reloj
        self.repo = repo
        self.limite = limite
        self.intervalos = list(intervalos) if intervalos is not None else list(INTERVALOS_DEFECTO)
        self._reanudados: set[str] = set()

    def _intervalo_para_intento(self, intento: int) -> float:
        """Devuelve el intervalo creciente correspondiente al intento (1-indexed)."""
        idx = intento - 1
        if idx < len(self.intervalos):
            return self.intervalos[idx]
        ultimo = self.intervalos[-1] if self.intervalos else 10.0
        return ultimo * (2 ** (idx - len(self.intervalos) + 1))

    def sondar_post(self, post_id: str, url: str | None = None) -> bool:
        """Sondea la URL esperada hasta que responda 200 o se agote el límite."""
        if post_id in self._reanudados:
            return False

        if not url:
            peca = self.repo.ler_peca(post_id) if self.repo else None
            url = obter_url_blog(post_id, peca)

        for intento in range(1, self.limite + 1):
            try:
                resp = self.cliente.get(url)
                status_code = resp.status_code
            except httpx.HTTPError as exc:
                log.warning("Error HTTP consultando deploy de %s (%s): %s", post_id, url, exc)
                status_code = None

            if status_code == 200:
                self._reanudados.add(post_id)
                _chamar_retomar(self.retomar, post_id, url)
                return True

            if intento < self.limite:
                espera = self._intervalo_para_intento(intento)
                _dormir(self.reloj, espera)

        # Límite agotado sin 200: avisa en Slack y deja el post pausado
        _enviar_aviso(
            self.aviso,
            f"Deploy del blog para el post {post_id} no respondió 200 tras {self.limite} intentos ({url}).",
        )
        return False

    def sondar_todos(self) -> list[str]:
        """Consulta cada post pausado en `esperar_deploy` y reanuda los que respondan 200."""
        if not self.repo:
            return []
        reanudados: list[str] = []
        pecas = self.repo.listar_pecas(status="aprovada", canal="blog")
        for peca in pecas:
            if peca.post_id in self._reanudados:
                continue
            url = obter_url_blog(peca.post_id, peca)
            if self.sondar_post(peca.post_id, url):
                reanudados.append(peca.post_id)
        return reanudados

    def tick(self) -> list[str]:
        """Alias para sondeo periódico, compatible con el patrón de agenda."""
        return self.sondar_todos()


def esperar_deploy(
    post_id: str,
    *,
    cliente: httpx.Client,
    retomar: Callable[..., Any],
    aviso: Aviso | Callable[[str], None],
    reloj: Any,
    url: str | None = None,
    limite: int = 5,
    intervalos: Sequence[float] | None = None,
) -> bool:
    """Espera que la URL del post responda 200 y reanuda."""
    deploy = DeployBlog(
        cliente=cliente,
        retomar=retomar,
        aviso=aviso,
        reloj=reloj,
        limite=limite,
        intervalos=intervalos,
    )
    return deploy.sondar_post(post_id, url=url)


def sondar(
    repo: Repositorio,
    *,
    cliente: httpx.Client,
    retomar: Callable[..., Any],
    aviso: Aviso | Callable[[str], None],
    reloj: Any,
    limite: int = 5,
    intervalos: Sequence[float] | None = None,
) -> list[str]:
    """Sondea todos los posts en espera de deploy en el repositorio."""
    deploy = DeployBlog(
        cliente=cliente,
        retomar=retomar,
        aviso=aviso,
        reloj=reloj,
        repo=repo,
        limite=limite,
        intervalos=intervalos,
    )
    return deploy.sondar_todos()
