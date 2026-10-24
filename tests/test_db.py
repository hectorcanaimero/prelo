import uuid
from datetime import UTC, datetime
from decimal import Decimal

import psycopg

from prelo.db.conexao import conectar
from prelo.db.migrar import aplicar_migracoes
from prelo.db.repositorio import RepositorioPg
from prelo.interfaces import Custo, Peca, Post, Repositorio


def _id() -> str:
    return str(uuid.uuid4())


def _post(repo) -> Post:
    post = Post(id=_id(), tema="tema", origem="editor", criado_em=datetime.now(UTC), estado="investigando")
    repo.criar_post(post)
    return post


def _peca(repo, post_id: str) -> Peca:
    peca = Peca(id=_id(), post_id=post_id, canal="linkedin", conteudo={"pt": {}}, violacoes=[], status="pendente")
    repo.criar_peca(peca)
    return peca


def test_migraciones_idempotentes(pg_url):
    with psycopg.connect(pg_url, autocommit=True) as conn:
        aplicar_migracoes(conn)
        aplicar_migracoes(conn)
        assert conn.execute("SELECT count(*) FROM migracoes").fetchone()[0] == 1


def test_post_con_dos_fuentes(pg_url):
    with conectar(pg_url) as conn:
        repo = RepositorioPg(conn)
        assert isinstance(repo, Repositorio)
        post = _post(repo)
        fontes = [{"url": "http://a", "titulo": "A", "trecho": "x"}, {"url": "http://b", "titulo": "B", "trecho": "y"}]
        repo.salvar_fontes(post.id, fontes)
        repo.salvar_fontes(post.id, fontes)  # reemplaza, no duplica
        assert repo.ler_post(post.id).tema == "tema"
        assert repo.ler_fontes(post.id) == fontes


def test_pieza_aprobada_se_lista(pg_url):
    with conectar(pg_url) as conn:
        repo = RepositorioPg(conn)
        peca = _peca(repo, _post(repo).id)
        assert repo.listar_pecas(status="aprovada", canal="linkedin") == []
        repo.atualizar_peca(peca.id, status="aprovada", decisao="aprovado", comentario="ok")
        [p] = repo.listar_pecas(status="aprovada", canal="linkedin")
        assert (p.id, p.decisao, p.comentario) == (peca.id, "aprovado", "ok")
        assert repo.listar_pecas(status="aprovada", canal="blog") == []


def test_costos_por_agente(pg_url):
    with conectar(pg_url) as conn:
        repo = RepositorioPg(conn)
        post = _post(repo)
        for agente, usd in [("redator", "0.10"), ("redator", "0.05"), ("investigador", "0.02")]:
            repo.registrar_custo(Custo(post.id, agente, "m", 100, 10, Decimal(usd), datetime.now(UTC)))
        c = repo.custos_por_post(post.id)
        assert c["redator"].usd == Decimal("0.15") and c["redator"].tokens_entrada == 200
        assert c["investigador"].usd == Decimal("0.02")
        assert sum(v.usd for v in c.values()) == Decimal("0.17")
