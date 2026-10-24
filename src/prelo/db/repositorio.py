from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from prelo.interfaces import Canal, Custo, CustoAgente, Decisao, Fonte, Peca, Post, Publicacao, StatusPeca

_PECA = "id::text, post_id::text, canal, conteudo, violacoes, status, decisao, comentario, agendada_para"


class RepositorioPg:
    """Implementa `Repositorio` sobre una conexion psycopg (autocommit)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def _q(self, sql: str, params=()) -> list[dict]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def criar_post(self, post: Post) -> None:
        self._q(
            "INSERT INTO posts (id, tema, origem, criado_em, estado) VALUES (%s, %s, %s, %s, %s)",
            (post.id, post.tema, post.origem, post.criado_em, post.estado),
        )

    def ler_post(self, post_id: str) -> Post:
        rows = self._q("SELECT id::text, tema, origem, criado_em, estado FROM posts WHERE id = %s", (post_id,))
        if not rows:
            raise KeyError(post_id)
        return Post(**rows[0])

    def atualizar_post(self, post_id: str, *, estado: str) -> None:
        self._q("UPDATE posts SET estado = %s WHERE id = %s", (estado, post_id))

    def salvar_fontes(self, post_id: str, fontes: list[Fonte]) -> None:
        with self.conn.transaction():
            self._q("DELETE FROM fontes WHERE post_id = %s", (post_id,))
            for f in fontes:
                self._q(
                    "INSERT INTO fontes (post_id, url, titulo, trecho) VALUES (%s, %s, %s, %s)",
                    (post_id, f["url"], f["titulo"], f["trecho"]),
                )

    def ler_fontes(self, post_id: str) -> list[Fonte]:
        rows = self._q("SELECT url, titulo, trecho FROM fontes WHERE post_id = %s ORDER BY id", (post_id,))
        return [Fonte(url=r["url"], titulo=r["titulo"], trecho=r["trecho"]) for r in rows]

    def criar_peca(self, peca: Peca) -> None:
        self._q(
            "INSERT INTO pecas (id, post_id, canal, conteudo, violacoes, status, decisao, comentario, agendada_para)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                peca.id,
                peca.post_id,
                peca.canal,
                Jsonb(peca.conteudo),
                Jsonb(peca.violacoes),
                peca.status,
                peca.decisao,
                peca.comentario,
                peca.agendada_para,
            ),
        )

    def atualizar_peca(
        self,
        peca_id: str,
        *,
        status: StatusPeca | None = None,
        decisao: Decisao | None = None,
        comentario: str | None = None,
        agendada_para: datetime | None = None,
    ) -> None:
        campos = {"status": status, "decisao": decisao, "comentario": comentario, "agendada_para": agendada_para}
        campos = {k: v for k, v in campos.items() if v is not None}
        if not campos:
            return
        sets = ", ".join(f"{k} = %s" for k in campos)  # nombres fijos de arriba, no input externo
        self._q(f"UPDATE pecas SET {sets} WHERE id = %s", (*campos.values(), peca_id))

    def ler_peca(self, peca_id: str) -> Peca:
        rows = self._q(f"SELECT {_PECA} FROM pecas WHERE id = %s", (peca_id,))
        if not rows:
            raise KeyError(peca_id)
        return Peca(**rows[0])

    def listar_pecas(self, *, status: StatusPeca, canal: Canal) -> list[Peca]:
        rows = self._q(f"SELECT {_PECA} FROM pecas WHERE status = %s AND canal = %s ORDER BY id", (status, canal))
        return [Peca(**r) for r in rows]

    def registrar_publicacao(self, publicacao: Publicacao) -> None:
        self._q(
            "INSERT INTO publicacoes (id, peca_id, canal, url, publicada_em, id_externo)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                publicacao.id,
                publicacao.peca_id,
                publicacao.canal,
                publicacao.url,
                publicacao.publicada_em,
                publicacao.id_externo,
            ),
        )

    def listar_publicacoes(self, *, canais: tuple[Canal, ...]) -> list[Publicacao]:
        rows = self._q(
            "SELECT id::text, peca_id::text, canal, url, publicada_em, id_externo FROM publicacoes"
            " WHERE canal = ANY(%s) ORDER BY publicada_em",
            (list(canais),),
        )
        return [Publicacao(**r) for r in rows]

    def salvar_metrica(self, publicacao_id: str, *, reacoes: int, comentarios: list) -> None:
        self._q(
            "INSERT INTO metricas (publicacao_id, reacoes, comentarios) VALUES (%s, %s, %s)",
            (publicacao_id, reacoes, Jsonb(comentarios)),
        )

    def ler_ultima_metrica(self, publicacao_id: str) -> dict | None:
        rows = self._q(
            "SELECT publicacao_id::text, coletada_em, reacoes, comentarios FROM metricas"
            " WHERE publicacao_id = %s ORDER BY coletada_em DESC, id DESC LIMIT 1",
            (publicacao_id,),
        )
        return rows[0] if rows else None

    def registrar_custo(self, custo: Custo) -> None:
        self._q(
            "INSERT INTO custos (post_id, agente, modelo, tokens_entrada, tokens_saida, usd, criado_em)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                custo.post_id,
                custo.agente,
                custo.modelo,
                custo.tokens_entrada,
                custo.tokens_saida,
                custo.usd,
                custo.criado_em,
            ),
        )

    def custos_por_post(self, post_id: str) -> dict[str, CustoAgente]:
        rows = self._q(
            "SELECT agente, sum(tokens_entrada)::int AS tokens_entrada, sum(tokens_saida)::int AS tokens_saida,"
            " sum(usd) AS usd FROM custos WHERE post_id = %s GROUP BY agente",
            (post_id,),
        )
        return {r.pop("agente"): CustoAgente(**r) for r in rows}
