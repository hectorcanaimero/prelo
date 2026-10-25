"""Contratos de Prelo: tipos y protocolos.

Este archivo es el contrato del que parten las tareas paralelas de F1 (marca,
agentes, costo, slack, agenda, publicadores). No importa ningun SDK externo
y no contiene implementaciones.

Las piezas publicas estan descritas en docs/arch/001-prelo.md -> Interfaces.
`EstadoPost` vive en `prelo.estado` para evitar un ciclo con los agentes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

# ---------------------------------------------------------------------------
# TypedDicts del flujo (lo que viaja por EstadoPost y por los prompts).
# ---------------------------------------------------------------------------


class Fonte(TypedDict):
    """Fuente que el investigador adjunta a un post."""

    url: str
    titulo: str
    trecho: str


class Violacao(TypedDict):
    """Violacion detectada por `marca.revisar`."""

    regra: Literal["empregador", "cifra_sem_fonte", "frase_ia"]
    trecho: str
    detalhe: str


class Texto(TypedDict):
    """Un idioma de una pieza (titulo, resumo y corpo)."""

    titulo: str
    resumo: str
    corpo: str


# ---------------------------------------------------------------------------
# Dataclasses del data model (filas de Postgres).
# IDs van como `str` para empatar con `EstadoPost.post_id` y `thread_id`.
# ---------------------------------------------------------------------------


Canal = Literal["blog", "linkedin", "instagram"]
Origem = Literal["editor", "sugestao"]
StatusPeca = Literal["pendente", "aprovada", "agendada", "publicada", "descartada"]
Decisao = Literal["aprovado", "editar", "descartar"]


@dataclass(frozen=True)
class Post:
    """Fila de la tabla `posts`. `id` es tambien `thread_id` del grafo."""

    id: str
    tema: str
    origem: Origem
    criado_em: datetime
    estado: str


@dataclass
class Peca:
    """Fila de la tabla `pecas`: una pieza por canal y post."""

    id: str
    post_id: str
    canal: Canal
    # blog: {"es"|"pt"|"en": Texto}; linkedin: {"pt": Texto}; instagram: {"laminas": [...], "prompt_imagem": str,
    # "url_blog": str}. jsonb en Postgres, por eso el valor es libre.
    conteudo: dict[str, Any]
    violacoes: list[Violacao]
    status: StatusPeca
    decisao: Decisao | None = None
    comentario: str | None = None
    agendada_para: datetime | None = None


@dataclass(frozen=True)
class Publicacao:
    """Fila de la tabla `publicacoes`: registro de que una pieza salio."""

    id: str
    peca_id: str
    canal: Canal
    url: str
    publicada_em: datetime
    id_externo: str


@dataclass(frozen=True)
class Custo:
    """Fila de la tabla `custos`: tokens y USD de una llamada al modelo."""

    post_id: str
    agente: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    usd: Decimal
    criado_em: datetime


@dataclass(frozen=True)
class CustoAgente:
    """Suma de `custos` de un agente en un post: lo que muestra Slack (FR-16)."""

    tokens_entrada: int
    tokens_saida: int
    usd: Decimal


# ---------------------------------------------------------------------------
# Regras: tipo opaco. marca.carregar_regras devuelve una instancia concreta;
# el grafo y los consumidores solo lo pasan a `revisar`.
# ---------------------------------------------------------------------------


class Regras(Protocol):
    """Reglas de revision de marca cargadas por `marca.carregar_regras`.

    Opaco en este contrato: `marca.py` define los campos concretos
    (frases, patrones, lista de empleadores bloqueados). El resto del
    sistema solo lo pasa sin tocarlo.
    """


# ---------------------------------------------------------------------------
# Protocolos de servicios inyectados.
# ---------------------------------------------------------------------------


class Modelo(Protocol):
    """Cliente del LLM. Lo usan los agentes; el grafo no lo ve."""

    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str:
        """Pide una completion al LLM.

        Registra tokens y USD en la tabla `custos` y manda la traza a
        Langfuse etiquetada con `post_id` y `agente` (FR-16).
        """
        ...


class Buscador(Protocol):
    """Cliente de busqueda web. Lo usa el investigador."""

    def buscar(self, consulta: str, *, max_resultados: int = 5) -> list[Fonte]:
        """Devuelve hasta `max_resultados` fuentes para `consulta`."""
        ...


class Publicador(Protocol):
    """Cliente de un canal (linkedin, github, instagram). Lo usa la agenda."""

    canal: Canal

    def publicar(self, peca: Peca) -> Publicacao:
        """Publica `peca` en el canal y devuelve la `Publicacao` resultante."""
        ...


@runtime_checkable
class Aviso(Protocol):
    """Canal de avisos de la agenda (en M1 implementado por Slack)."""

    def avisar(self, texto: str) -> None:
        """Envia un aviso al canal (p.ej. token de LinkedIn por caducar)."""
        ...


# ---------------------------------------------------------------------------
# Repositorio: el contrato del DB layer que usan grafo, agenda, slack y custos.
# `runtime_checkable` para que los tests pasen un repo en memoria con isinstance.
# ---------------------------------------------------------------------------


@runtime_checkable
class Repositorio(Protocol):
    """Acceso a Postgres. F1.1.T2 implementa esta interfaz en `db/repositorio.py`."""

    def criar_post(self, post: Post) -> None:
        """Inserta una fila en `posts`."""
        ...

    def ler_post(self, post_id: str) -> Post:
        """Lee la fila de `posts` con las fuentes asociadas disponibles por aparte."""
        ...

    def atualizar_post(self, post_id: str, *, estado: str) -> None:
        """Cambia `posts.estado` (el nodo en que va el post: `investigando`, `aguardando_aprovacao`, `encerrado`...)."""
        ...

    def salvar_fontes(self, post_id: str, fontes: list[Fonte]) -> None:
        """Guarda la lista de fuentes del investigador para `post_id`.

        Reemplaza las fuentes anteriores del post (idempotente por `post_id`).
        """
        ...

    def ler_fontes(self, post_id: str) -> list[Fonte]:
        """Devuelve todas las fuentes guardadas para `post_id`."""
        ...

    def criar_peca(self, peca: Peca) -> None:
        """Inserta una fila en `pecas`."""
        ...

    def atualizar_peca(
        self,
        peca_id: str,
        *,
        status: StatusPeca | None = None,
        decisao: Decisao | None = None,
        comentario: str | None = None,
        agendada_para: datetime | None = None,
    ) -> None:
        """Actualiza los campos no-None de la pieza. `None` significa 'no tocar'."""
        ...

    def ler_peca(self, peca_id: str) -> Peca:
        """Lee una pieza por id."""
        ...

    def listar_pecas(self, *, status: StatusPeca, canal: Canal) -> list[Peca]:
        """Devuelve las piezas con `status` y `canal` dados (lo que usa la agenda)."""
        ...

    def registrar_publicacao(self, publicacao: Publicacao) -> None:
        """Guarda una fila en `publicacoes` (FR-14)."""
        ...

    def registrar_custo(self, custo: Custo) -> None:
        """Guarda una fila en `custos` (FR-16)."""
        ...

    def custos_por_post(self, post_id: str) -> dict[str, CustoAgente]:
        """Suma tokens y `usd` por `agente` para `post_id` (FR-16).

        Devuelve `{agente: CustoAgente}`; agentes sin costo no aparecen. El total es la suma de los valores.
        """
        ...


# ---------------------------------------------------------------------------
# Dependencias: lo que recibe `grafo.construir(deps, checkpointer)`.
# El grafo no importa agentes, marca ni slack; los recibe ya armados en app.py
# y los tests pasan dobles.
# ---------------------------------------------------------------------------


@dataclass
class Dependencias:
    """Dobles de los servicios que usa el grafo.

    `traduzir` y `abrir_pr` llegan en F2: sin ellos el grafo va directo a los
    derivados, como en F1. En F3 el dict `adaptar` tendra tambien la clave `instagram`.
    """

    # (tema, *, post_id) -> list[Fonte]
    investigar: Callable[..., list[Fonte]]
    # (tema, fontes, feedback: str | None, *, post_id) -> Texto
    redigir: Callable[..., Texto]
    # canal -> (texto, url_blog: str | None, feedback, *, post_id) -> dict
    adaptar: dict[str, Callable[..., dict[str, Any]]]
    # (texto, fontes) -> list[Violacao]
    revisar: Callable[[str, list[Fonte]], list[Violacao]]
    # (peca) -> None; avisa en Slack que una pieza espera aprobacion
    notificar: Callable[[Peca], None]
    repo: Repositorio
    # (texto, *, post_id) -> dict[str, Texto] con "es" | "pt" | "en"
    traduzir: Callable[..., dict[str, Texto]] | None = None
    # (post_id, textos) -> URL del PR en site-guria
    abrir_pr: Callable[[str, dict[str, Texto]], str] | None = None
    # (texto, canal) -> violaciones de formato del canal (palabras, emojis, hashtags); se reescribe hasta 2 veces
    formato: Callable[[str, Canal], list[Violacao]] = lambda texto, canal: []


__all__ = [
    "Aviso",
    "Buscador",
    "Canal",
    "Custo",
    "CustoAgente",
    "Decisao",
    "Dependencias",
    "Fonte",
    "Modelo",
    "Origem",
    "Peca",
    "Post",
    "Publicacao",
    "Publicador",
    "Regras",
    "Repositorio",
    "StatusPeca",
    "Texto",
    "Violacao",
]
