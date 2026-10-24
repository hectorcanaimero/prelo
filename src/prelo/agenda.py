"""Worker de agenda (D9): asigna huecos de martes a jueves y publica al llegar la hora."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from prelo.interfaces import Aviso, Canal, Peca, Publicador, Repositorio

TZ = ZoneInfo("America/Sao_Paulo")
DIAS_PUBLICACION = (1, 2, 3)  # martes a jueves
AVISO_TOKEN = timedelta(days=7)


def proximo_hueco(canal: Canal, ocupados: list[datetime], agora: datetime, hora: time = time(9, 0)) -> datetime:
    """Siguiente martes-jueves a `hora` posterior a `agora`, sin día ocupado (máx. 1 por día, FR-13).

    `ocupados` son las fechas ya tomadas en `canal`; otros canales no cuentan.
    """
    agora = agora.astimezone(TZ)
    dias_ocupados = {o.astimezone(TZ).date() for o in ocupados}
    dia = agora.date()
    while True:
        hueco = datetime.combine(dia, hora, tzinfo=TZ)
        if dia.weekday() in DIAS_PUBLICACION and dia not in dias_ocupados and hueco > agora:
            return hueco
        dia += timedelta(days=1)


class Agenda:
    def __init__(
        self,
        publicadores: Mapping[Canal, Publicador],
        repo: Repositorio,
        aviso: Aviso,
        reloj: Callable[[], datetime],
        hora: time = time(9, 0),
        token_expira_em: datetime | None = None,
    ) -> None:
        self.publicadores, self.repo, self.aviso, self.reloj = publicadores, repo, aviso, reloj
        # LINKEDIN_TOKEN_EXPIRES_AT suele ser solo una fecha ("2026-12-24"): sin zona se toma como hora local de TZ
        if token_expira_em and token_expira_em.tzinfo is None:
            token_expira_em = token_expira_em.replace(tzinfo=TZ)
        self.hora, self.token_expira_em = hora, token_expira_em
        self._token_avisado = False

    def tick(self) -> None:
        """Se ejecuta cada minuto: publica lo vencido, agenda lo aprobado y vigila el token."""
        agora = self.reloj()
        self._vigilar_token(agora)
        for canal, publicador in self.publicadores.items():
            # leídas antes de publicar: una pieza que falla se reintenta en otro tick/hueco
            aprovadas = self.repo.listar_pecas(status="aprovada", canal=canal)
            for peca in self.repo.listar_pecas(status="agendada", canal=canal):
                if peca.agendada_para and peca.agendada_para <= agora:
                    self._publicar(publicador, peca)
            ocupados = [
                p.agendada_para
                for st in ("agendada", "publicada")
                for p in self.repo.listar_pecas(status=st, canal=canal)
                if p.agendada_para
            ]
            for peca in aprovadas:
                hueco = proximo_hueco(canal, ocupados, agora, self.hora)
                ocupados.append(hueco)
                self.repo.atualizar_peca(peca.id, status="agendada", agendada_para=hueco)
                self.aviso.avisar(f"Pieza {peca.id} ({canal}) agendada para {hueco:%d/%m/%Y %H:%M}.")

    def _publicar(self, publicador: Publicador, peca: Peca) -> None:
        if peca.decisao != "aprovado":  # FR-7: defensa en profundidad
            self.repo.atualizar_peca(peca.id, status="pendente")
            self.aviso.avisar(f"Pieza {peca.id} ({peca.canal}) no se publicó: su decisión no es 'aprovado'.")
            return
        try:
            publicacao = publicador.publicar(peca)
        except Exception as e:  # noqa: BLE001 - cualquier fallo devuelve la pieza a aprovada
            self.repo.atualizar_peca(peca.id, status="aprovada")
            self.aviso.avisar(f"Falló la publicación de {peca.id} ({peca.canal}): {e}. Se reintentará.")
            return
        self.repo.registrar_publicacao(publicacao)
        self.repo.atualizar_peca(peca.id, status="publicada")
        self.aviso.avisar(f"Pieza {peca.id} publicada en {peca.canal}: {publicacao.url}")

    def _vigilar_token(self, agora: datetime) -> None:
        if self.token_expira_em and not self._token_avisado and self.token_expira_em - agora <= AVISO_TOKEN:
            self._token_avisado = True
            self.aviso.avisar(f"El token de LinkedIn caduca el {self.token_expira_em:%d/%m/%Y}: renuévalo.")
