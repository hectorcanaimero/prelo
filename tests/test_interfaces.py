"""Contratos de `prelo.interfaces` y `prelo.estado`.

Tres cosas: (1) un `Repositorio` escrito en memoria aqui cumple el protocolo
via `isinstance`; (2) un `EstadoPost` con los tres idiomas se construye como
diccionario literal y los tipos tipicos leen de el; (3) importar
`prelo.interfaces` no arrastra ningun SDK externo.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from prelo.estado import EstadoPost
from prelo.interfaces import (
    Aviso,
    Canal,
    Custo,
    CustoAgente,
    Decisao,
    Fonte,
    Peca,
    Post,
    Publicacao,
    Repositorio,
    StatusPeca,
    Texto,
    Violacao,
)


class RepoEmMemoria:
    """Implementacion minima en memoria para probar el protocolo."""

    def __init__(self) -> None:
        self.posts: dict[str, Post] = {}
        self.fontes: dict[str, list[Fonte]] = {}
        self.pecas: dict[str, Peca] = {}
        self.publicacoes: list[Publicacao] = []
        self.custos: list[Custo] = []

    def criar_post(self, post: Post) -> None:
        self.posts[post.id] = post

    def ler_post(self, post_id: str) -> Post:
        return self.posts[post_id]

    def salvar_fontes(self, post_id: str, fontes: list[Fonte]) -> None:
        self.fontes[post_id] = list(fontes)

    def ler_fontes(self, post_id: str) -> list[Fonte]:
        return list(self.fontes.get(post_id, []))

    def criar_peca(self, peca: Peca) -> None:
        self.pecas[peca.id] = peca

    def atualizar_peca(
        self,
        peca_id: str,
        *,
        status: StatusPeca | None = None,
        decisao: Decisao | None = None,
        comentario: str | None = None,
        agendada_para: datetime | None = None,
    ) -> None:
        p = self.pecas[peca_id]
        if status is not None:
            p.status = status
        if decisao is not None:
            p.decisao = decisao
        if comentario is not None:
            p.comentario = comentario
        if agendada_para is not None:
            p.agendada_para = agendada_para

    def ler_peca(self, peca_id: str) -> Peca:
        return self.pecas[peca_id]

    def listar_pecas(self, *, status: StatusPeca, canal: Canal) -> list[Peca]:
        return [p for p in self.pecas.values() if p.status == status and p.canal == canal]

    def registrar_publicacao(self, publicacao: Publicacao) -> None:
        self.publicacoes.append(publicacao)

    def registrar_custo(self, custo: Custo) -> None:
        self.custos.append(custo)

    def atualizar_post(self, post_id: str, *, estado: str) -> None:
        self.posts[post_id] = replace(self.posts[post_id], estado=estado)

    def custos_por_post(self, post_id: str) -> dict[str, CustoAgente]:
        total: dict[str, CustoAgente] = {}
        for c in self.custos:
            if c.post_id == post_id:
                a = total.get(c.agente, CustoAgente(0, 0, Decimal(0)))
                total[c.agente] = CustoAgente(
                    a.tokens_entrada + c.tokens_entrada, a.tokens_saida + c.tokens_saida, a.usd + c.usd
                )
        return total


class AvisoFalso:
    def __init__(self) -> None:
        self.textos: list[str] = []

    def avisar(self, texto: str) -> None:
        self.textos.append(texto)


def test_repositorio_em_memoria_cumple_protocolo() -> None:
    repo = RepoEmMemoria()
    assert isinstance(repo, Repositorio)


def test_aviso_falso_cumple_protocolo() -> None:
    aviso = AvisoFalso()
    assert isinstance(aviso, Aviso)


def test_objeto_sin_metodos_no_cumple_repositorio() -> None:
    class Vazio:
        pass

    assert not isinstance(Vazio(), Repositorio)


def test_estadopost_tres_idiomas_se_construye_y_se_lee() -> None:
    es: Texto = {"titulo": "Agents", "resumo": "...", "corpo": "..."}
    pt: Texto = {"titulo": "Agentes", "resumo": "...", "corpo": "..."}
    en: Texto = {"titulo": "Agents", "resumo": "...", "corpo": "..."}
    fonte: Fonte = {"url": "https://x", "titulo": "t", "trecho": "40% de X"}
    estado: EstadoPost = {
        "post_id": "post-1",
        "tema": "LangGraph",
        "fontes": [fonte],
        "rascunho": {"es": es, "pt": pt, "en": en},
        "derivados": {"linkedin": {"corpo": "..."}},
        "violacoes": [],
        "tentativas": 0,
        "decisao": None,
        "comentario": None,
        "url_blog": None,
    }
    assert set(estado["rascunho"].keys()) == {"es", "pt", "en"}
    assert estado["rascunho"]["es"]["titulo"] == "Agents"


def test_dataclasses_del_data_model_se_construyen() -> None:
    now = datetime(2026, 10, 24, 10, 0, 0)
    post = Post(id="p1", tema="x", origem="editor", criado_em=now, estado="rascunho")
    peca = Peca(id="pe1", post_id="p1", canal="linkedin", conteudo={}, violacoes=[], status="pendente")
    pub = Publicacao(id="pb1", peca_id="pe1", canal="linkedin", url="https://x", publicada_em=now, id_externo="ext")
    custo = Custo(
        post_id="p1",
        agente="redator",
        modelo="m",
        tokens_entrada=1,
        tokens_saida=2,
        usd=Decimal("0.01"),
        criado_em=now,
    )
    # Transicion valida: pendente -> aprovada con decisao.
    peca.status = "aprovada"
    peca.decisao = "aprovado"
    assert (post.origem, peca.status, peca.decisao, pub.canal, custo.agente) == (
        "editor",
        "aprovada",
        "aprovado",
        "linkedin",
        "redator",
    )


def test_violacao_lleva_trecho_y_regra_tipada() -> None:
    v: Violacao = {"regra": "cifra_sem_fonte", "trecho": "40%", "detalhe": "sin fuente"}
    assert v["regra"] == "cifra_sem_fonte"


def test_importar_interfaces_no_importa_sdks_externos() -> None:
    """`prelo.interfaces` no debe arrastrar anthropic, langgraph, langfuse, slack, httpx, psycopg, tavily."""
    sdks = ["anthropic", "langgraph", "langfuse", "slack_bolt", "tavily", "httpx", "psycopg", "fastapi"]
    code = (
        "import sys\n"
        "import prelo.interfaces\n"
        f"sdks = {sdks!r}\n"
        "fugas = [s for s in sdks if any(m == s or m.startswith(s + '.') for m in sys.modules)]\n"
        "assert not fugas, f'fugas: {fugas}'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_custos_por_post_suma_tokens_y_usd_por_agente() -> None:
    now = datetime(2026, 10, 24, 10, 0, 0)
    repo = RepoEmMemoria()
    for usd in ("0.01", "0.02"):
        repo.registrar_custo(Custo("p1", "redator", "m", 10, 5, Decimal(usd), now))
    repo.registrar_custo(Custo("p2", "redator", "m", 99, 99, Decimal(9), now))
    assert repo.custos_por_post("p1") == {"redator": CustoAgente(20, 10, Decimal("0.03"))}
