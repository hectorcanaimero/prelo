import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from prelo import slack
from prelo.db.conexao import conectar
from prelo.db.migrar import DIR, aplicar_migracoes
from prelo.db.repositorio import RepositorioPg
from prelo.interfaces import Peca, Post, Publicacao
from prelo.metricas import coletar
from tests.test_slack import AppFalsa, ClienteFalso, RepoFalso


class RepoMem:
    def __init__(self, pubs):
        self.pubs, self.metricas = pubs, []

    def listar_publicacoes(self, *, canais):
        return [p for p in self.pubs if p.canal in canais]

    def salvar_metrica(self, publicacao_id, *, reacoes, comentarios):
        self.metricas.append((publicacao_id, reacoes, comentarios))


class LeitorFalso:
    def __init__(self, canal):
        self.canal = canal

    def ler(self, publicacao):
        return {"reacoes": 7, "comentarios": [{"autor": "a", "texto": "t"}]}


def _pub(canal, i):
    return Publicacao(
        id=f"p{i}", peca_id="x", canal=canal, url="u", publicada_em=datetime.now(UTC), id_externo=f"e{i}"
    )


def test_coletar_guarda_una_fila_por_publicacion():
    repo = RepoMem([_pub("linkedin", 1), _pub("instagram", 2)])
    assert coletar([LeitorFalso("linkedin"), LeitorFalso("instagram")], repo) == 2
    assert [m[0] for m in repo.metricas] == ["p1", "p2"]


def test_publicacion_sin_lector_se_salta():
    repo = RepoMem([_pub("linkedin", 1), _pub("instagram", 2)])
    assert coletar([LeitorFalso("linkedin")], repo) == 1
    assert [m[0] for m in repo.metricas] == ["p1"]


def test_migracion_002_sobre_001(pg_url):
    assert (DIR / "002_metricas.sql").exists()
    with psycopg.connect(pg_url, autocommit=True) as conn:
        aplicar_migracoes(conn)
        assert conn.execute("SELECT count(*) FROM metricas").fetchone()[0] == 0


def test_repo_guarda_y_lee_ultima_metrica(pg_url):
    with conectar(pg_url) as conn:
        repo = RepositorioPg(conn)
        pid, peid, pub_id = (str(uuid.uuid4()) for _ in range(3))
        repo.criar_post(Post(id=pid, tema="t", origem="editor", criado_em=datetime.now(UTC), estado="x"))
        repo.criar_peca(Peca(id=peid, post_id=pid, canal="linkedin", conteudo={}, violacoes=[], status="publicada"))
        repo.registrar_publicacao(
            Publicacao(id=pub_id, peca_id=peid, canal="linkedin", url="u", publicada_em=datetime.now(UTC), id_externo="e")
        )
        assert repo.ler_ultima_metrica(pub_id) is None
        repo.salvar_metrica(pub_id, reacoes=1, comentarios=[])
        repo.salvar_metrica(pub_id, reacoes=5, comentarios=[{"autor": "a", "texto": "t"}])
        ultima = repo.ler_ultima_metrica(pub_id)
        assert ultima["reacoes"] == 5 and ultima["comentarios"][0]["autor"] == "a"
        assert [p.id for p in repo.listar_publicacoes(canais=("linkedin",))] == [pub_id]


TEMAS = [{"tema": f"Tema {i}", "origem": "commits", "link": f"https://ex.com/{i}"} for i in range(3)]


@pytest.fixture
def ctx():
    app, chamadas, respuestas = AppFalsa(), [], []
    slack.registrar(
        app,
        iniciar=lambda tema, origem="editor": chamadas.append((tema, origem)) or "post1",
        retomar=lambda *a, **kw: None,
        repo=RepoFalso(),
        canal="C1",
        cliente=ClienteFalso(),
        sugerir=lambda: TEMAS,
    )
    return app, chamadas, respuestas


def test_sugerir_muestra_3_temas_con_link(ctx):
    app, _, _ = ctx
    enviados = []
    app.h["/prelo"](lambda: None, {"text": "sugerir"}, lambda *a, **kw: enviados.append(kw))
    blocos = enviados[0]["blocks"]
    textos = " ".join(b["text"]["text"] for b in blocos if b["type"] == "section")
    botones = [e for b in blocos if b["type"] == "actions" for e in b["elements"]]
    assert len(botones) == 3 and all(b["action_id"] == "prelo_escolher" for b in botones)
    assert all(t["tema"] in textos and t["link"] in textos for t in TEMAS)


def test_escolher_inicia_con_origen_sugestao(ctx):
    app, chamadas, _ = ctx
    app.h["prelo_escolher"](lambda: None, {"value": "Tema 1"}, lambda *a, **kw: None)
    assert chamadas == [("Tema 1", "sugestao")]
