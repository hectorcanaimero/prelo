"""Tests de deploy_blog.py: sondeo de guria.lat/blog para posts en esperar_deploy."""

from __future__ import annotations

from typing import Any

import httpx
import respx

from prelo.deploy_blog import DeployBlog, obter_url_blog
from prelo.interfaces import Peca

URL_BLOG = "https://guria.lat/blog/agentes"


class RelojFalso:
    def __init__(self) -> None:
        self.dormidas: list[float] = []

    def dormir(self, segundos: float) -> None:
        self.dormidas.append(segundos)

    def __call__(self, segundos: float | None = None) -> Any:
        if segundos is not None:
            self.dormir(segundos)


class Avisos:
    def __init__(self) -> None:
        self.textos: list[str] = []

    def avisar(self, texto: str) -> None:
        self.textos.append(texto)


@respx.mock
def test_404_y_luego_200_reanudan_una_sola_vez_con_la_url() -> None:
    """Un 404 y luego un 200 reanudan una sola vez con la URL."""
    respx.get(URL_BLOG).mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200),
        ]
    )

    reanudados: list[tuple[str, str]] = []

    def retomar(post_id: str, *, url_blog: str | None = None) -> None:
        reanudados.append((post_id, url_blog or ""))

    aviso = Avisos()
    reloj = RelojFalso()

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=retomar,
            aviso=aviso,
            reloj=reloj,
            intervalos=[1.0, 2.0, 4.0],
        )

        # Primera ejecución: 404 y luego 200
        exito = deploy.sondar_post("post-1", url=URL_BLOG)
        assert exito is True
        assert reanudados == [("post-1", URL_BLOG)]
        assert reloj.dormidas == [1.0]
        assert aviso.textos == []

        # Segundo llamado para el mismo post: no debe reanudar otra vez
        exito_segundo = deploy.sondar_post("post-1", url=URL_BLOG)
        assert exito_segundo is False
        assert reanudados == [("post-1", URL_BLOG)]  # Sigue habiendo solo 1 reanudación


@respx.mock
def test_tres_404_seguidos_esperan_intervalos_crecientes() -> None:
    """Tres 404 seguidos esperan intervalos crecientes antes del siguiente intento."""
    respx.get(URL_BLOG).mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(404),
            httpx.Response(404),
            httpx.Response(200),
        ]
    )

    reanudados: list[tuple[str, str]] = []

    def retomar(post_id: str, *, url_blog: str | None = None) -> None:
        reanudados.append((post_id, url_blog or ""))

    aviso = Avisos()
    reloj = RelojFalso()

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=retomar,
            aviso=aviso,
            reloj=reloj,
            limite=4,
            intervalos=[5.0, 15.0, 45.0],
        )

        exito = deploy.sondar_post("post-2", url=URL_BLOG)
        assert exito is True
        assert reanudados == [("post-2", URL_BLOG)]
        # Tres 404 seguidos esperaron exactamente 3 intervalos crecientes
        assert len(reloj.dormidas) == 3
        assert reloj.dormidas[0] < reloj.dormidas[1] < reloj.dormidas[2]
        assert reloj.dormidas == [5.0, 15.0, 45.0]


@respx.mock
def test_agotar_limite_genera_aviso_y_no_reanuda() -> None:
    """Agotar el límite genera un aviso en Slack y no reanuda (deja el post pausado)."""
    respx.get(URL_BLOG).mock(return_value=httpx.Response(404))

    reanudados: list[str] = []

    def retomar(post_id: str, *, url_blog: str | None = None) -> None:
        reanudados.append(post_id)

    aviso = Avisos()
    reloj = RelojFalso()

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=retomar,
            aviso=aviso,
            reloj=reloj,
            limite=3,
            intervalos=[1.0, 2.0],
        )

        exito = deploy.sondar_post("post-fallido", url=URL_BLOG)
        # No reanudó y el post sigue pausado
        assert exito is False
        assert reanudados == []
        # Generó aviso en Slack
        assert len(aviso.textos) == 1
        assert "post-fallido" in aviso.textos[0]
        assert URL_BLOG in aviso.textos[0]
        # Esperó los 2 intervalos antes del 3er y último intento
        assert reloj.dormidas == [1.0, 2.0]


class RepoMemoriaBlog:
    def __init__(self, pecas: list[Peca]) -> None:
        self.pecas = {p.id: p for p in pecas}

    def listar_pecas(self, *, status: str, canal: str) -> list[Peca]:
        return [p for p in self.pecas.values() if p.status == status and p.canal == canal]

    def ler_peca(self, peca_id: str) -> Peca:
        return self.pecas[peca_id]


@respx.mock
def test_sondeo_con_repositorio_encuentra_posts_pausados() -> None:
    """DeployBlog con repo consulta la URL derivada de la pieza y reanuda."""
    url_esperada = "https://guria.lat/blog/intake-langgraph"
    respx.get(url_esperada).mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200),
        ]
    )

    peca = Peca(
        id="peca-blog-1",
        post_id="post-langgraph",
        canal="blog",
        conteudo={"es": {"titulo": "Intake Langgraph", "resumo": "r", "corpo": "c"}},
        violacoes=[],
        status="aprovada",
        decisao="aprovado",
    )
    repo = RepoMemoriaBlog([peca])

    reanudados: list[tuple[str, str]] = []

    def retomar(post_id: str, *, url_blog: str | None = None) -> None:
        reanudados.append((post_id, url_blog or ""))

    aviso = Avisos()
    reloj = RelojFalso()

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=retomar,
            aviso=aviso,
            reloj=reloj,
            repo=repo,  # type: ignore[arg-type]
            intervalos=[1.0],
        )

        lista = deploy.tick()
        assert lista == ["post-langgraph"]
        assert reanudados == [("post-langgraph", url_esperada)]

        # Tick subsiguiente no reanuda nuevamente
        lista_segunda = deploy.tick()
        assert lista_segunda == []
        assert len(reanudados) == 1


@respx.mock
def test_error_de_conexion_reintenta_sin_romper() -> None:
    """Un error de conexión se trata como intento fallido y reintenta tras esperar."""
    respx.get(URL_BLOG).mock(
        side_effect=[
            httpx.ConnectError("Connection refused"),
            httpx.Response(200),
        ]
    )

    reanudados: list[str] = []
    aviso = Avisos()
    reloj = RelojFalso()

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=lambda pid, url_blog=None: reanudados.append(pid),
            aviso=aviso,
            reloj=reloj,
            intervalos=[2.0],
        )

        exito = deploy.sondar_post("post-net", url=URL_BLOG)
        assert exito is True
        assert reanudados == ["post-net"]
        assert reloj.dormidas == [2.0]


def test_obter_url_blog_prioridades() -> None:
    """Verifica la generación de la URL esperada con slug explícito, título o tema."""
    # 1. Con slug explícito
    peca_slug = Peca("1", "post-1", "blog", {"slug": "mi-super-post"}, [], "aprovada")
    assert obter_url_blog("post-1", peca_slug) == "https://guria.lat/blog/mi-super-post"

    # 2. Con título en español
    peca_es = Peca("2", "post-2", "blog", {"es": {"titulo": "¡Hola, Mundo y Más!"}}, [], "aprovada")
    assert obter_url_blog("post-2", peca_es) == "https://guria.lat/blog/hola-mundo-y-mas"

    # 3. Solo con tema
    assert obter_url_blog("post-3", tema="Agentes Autónomos") == "https://guria.lat/blog/agentes-autonomos"


@respx.mock
def test_retomar_firma_posicional() -> None:
    """Soporta firmas de `retomar` que reciben post_id y url posicionalmente."""
    respx.get(URL_BLOG).mock(return_value=httpx.Response(200))

    llamadas: list[tuple[str, str]] = []

    def retomar_posicional(pid: str, u: str) -> None:
        llamadas.append((pid, u))

    with httpx.Client() as client:
        deploy = DeployBlog(
            cliente=client,
            retomar=retomar_posicional,
            aviso=Avisos(),
            reloj=RelojFalso(),
        )
        assert deploy.sondar_post("post-pos", url=URL_BLOG) is True
        assert llamadas == [("post-pos", URL_BLOG)]
