from datetime import datetime, time
from zoneinfo import ZoneInfo

from prelo.agenda import Agenda, proximo_hueco
from prelo.interfaces import Peca, Publicacao

TZ = ZoneInfo("America/Sao_Paulo")
H = time(9, 0)


def dt(d, h=0, m=0, mes=10):
    return datetime(2026, mes, d, h, m, tzinfo=TZ)  # 2026-10-26 es lunes


class Repo:
    def __init__(self, pecas):
        self.pecas, self.pubs = list(pecas), []

    def get(self, i):
        return next(p for p in self.pecas if p.id == i)

    def listar_pecas(self, *, status, canal):
        return [p for p in self.pecas if p.status == status and p.canal == canal]

    def atualizar_peca(self, i, *, status=None, decisao=None, comentario=None, agendada_para=None):
        p = self.get(i)
        p.status = status or p.status
        p.agendada_para = agendada_para or p.agendada_para

    def registrar_publicacao(self, pub):
        self.pubs.append(pub)


class Pub:
    def __init__(self, canal, falla=False):
        self.canal, self.falla, self.llamadas = canal, falla, []

    def publicar(self, peca):
        if self.falla:
            raise RuntimeError("boom")
        self.llamadas.append(peca.id)
        return Publicacao("x", peca.id, self.canal, "https://l/1", dt(27, 9), "ext1")


class Avisos:
    def __init__(self):
        self.textos = []

    def avisar(self, t):
        self.textos.append(t)


def peca(id, canal="linkedin", status="aprovada", decisao="aprovado", para=None):
    return Peca(id, "p", canal, {}, [], status, decisao, agendada_para=para)


def montar(*pecas, ahora=None, falla=False, token=None):
    repo, avisos, reloj = Repo(pecas), Avisos(), [ahora or dt(26, 15)]
    pubs = {c: Pub(c, falla) for c in ("linkedin", "instagram")}
    a = Agenda(pubs, repo, avisos, lambda: reloj[0], hora=H, token_expira_em=token)
    return a, repo, avisos, pubs, reloj


def test_lunes_va_al_martes():
    assert proximo_hueco("linkedin", [], dt(26, 15), H) == dt(27, 9)


def test_jueves_despues_de_la_hora_va_al_martes_siguiente():
    assert proximo_hueco("linkedin", [], dt(29, 10), H) == dt(3, 9, mes=11)


def test_martes_ocupado_va_al_miercoles():
    assert proximo_hueco("linkedin", [dt(27, 9)], dt(26, 15), H) == dt(28, 9)


def test_otro_canal_puede_usar_el_martes():
    a, repo, *_ = montar(peca("1", status="agendada", para=dt(27, 9)), peca("2", canal="instagram"))
    a.tick()
    assert repo.get("2").agendada_para == dt(27, 9)


def test_decisao_no_aprobada_no_se_publica():
    a, repo, avisos, pubs, _ = montar(
        peca("1", status="agendada", decisao="editar", para=dt(27, 9)), ahora=dt(27, 9, 1)
    )
    a.tick()
    assert pubs["linkedin"].llamadas == [] and repo.pubs == []
    assert repo.get("1").status != "publicada" and avisos.textos


def test_al_llegar_la_hora_publica_y_registra():
    a, repo, avisos, _, reloj = montar(peca("1"))
    a.tick()
    assert repo.get("1").status == "agendada" and avisos.textos
    reloj[0] = dt(27, 9, 1)
    a.tick()
    assert repo.get("1").status == "publicada"
    assert (repo.pubs[0].canal, repo.pubs[0].url, repo.pubs[0].publicada_em) == ("linkedin", "https://l/1", dt(27, 9))


def test_fallo_del_publicador_vuelve_a_aprovada_y_avisa():
    a, repo, avisos, *_ = montar(peca("1", status="agendada", para=dt(27, 9)), ahora=dt(27, 9, 1), falla=True)
    a.tick()
    assert repo.get("1").status == "aprovada" and repo.pubs == [] and any("boom" in t for t in avisos.textos)


def test_aviso_de_token_a_7_dias_una_sola_vez():
    a, _, avisos, *_ = montar(token=dt(31, 12))
    a.tick()
    a.tick()
    assert len([t for t in avisos.textos if "token" in t.lower()]) == 1
    b, _, avisos, *_ = montar(token=dt(1, 12, mes=12))
    b.tick()
    assert avisos.textos == []
