"""Punto de entrada: conecta config, db, agentes, grafo, Slack, agenda y API en un solo proceso."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from functools import partial
from typing import Any

from prelo import grafo
from prelo.agentes.adaptador_linkedin import adaptador_linkedin
from prelo.agentes.investigador import criar_investigador
from prelo.agentes.redator import redator
from prelo.config import Settings
from prelo.interfaces import Dependencias
from prelo.marca import carregar_regras, revisar

log = logging.getLogger(__name__)


def montar_dependencias(settings: Settings, clientes: dict[str, Any]) -> Dependencias:
    """Arma las `Dependencias` con clientes ya construidos: `modelo`, `buscador`, `repo` y `notificar`."""
    modelo = clientes["modelo"]
    regras = carregar_regras(settings)
    return Dependencias(
        investigar=criar_investigador(modelo, clientes["buscador"]),
        redigir=partial(redator, modelo),
        adaptar={"linkedin": partial(adaptador_linkedin, modelo)},
        revisar=lambda texto, fontes: revisar(texto, fontes, regras),
        notificar=clientes["notificar"],
        repo=clientes["repo"],
    )


class _TrazaLangfuse:
    """Adapta el cliente Langfuse v5 a la llamada `trace(...)` que usa `ModeloAnthropic`."""

    def __init__(self, cliente: Any) -> None:
        self._c = cliente

    def trace(self, *, name: str, input: Any, output: Any, tags: list[str], metadata: dict[str, Any]) -> None:
        self._c.start_observation(
            name=name, as_type="generation", input=input, output=output, metadata={**metadata, "tags": tags}
        ).end()


class _AvisoSlack:
    def __init__(self, cliente: Any, canal: str) -> None:
        self._cliente, self._canal = cliente, canal

    def avisar(self, texto: str) -> None:
        self._cliente.chat_postMessage(channel=self._canal, text=texto)


def _bucle_agenda(agenda: Any) -> None:
    while True:
        try:
            agenda.tick()
        except Exception:  # un tick fallido no mata el worker
            log.exception("fallo el tick de la agenda")
        time.sleep(60)


def main() -> None:
    import anthropic
    import psycopg
    import uvicorn
    from langfuse import Langfuse
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    from prelo import slack
    from prelo.agenda import Agenda
    from prelo.api import criar_api
    from prelo.buscador import criar_buscador
    from prelo.db.conexao import conectar
    from prelo.db.migrar import aplicar_migracoes
    from prelo.db.repositorio import RepositorioPg
    from prelo.modelo import ModeloAnthropic
    from prelo.publicadores.linkedin import PublicadorLinkedin

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    conn = conectar(settings.DATABASE_URL)
    aplicar_migracoes(conn)
    repo = RepositorioPg(conn)

    langfuse = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY.get_secret_value(),
        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
        host=settings.LANGFUSE_HOST,
    )
    modelo = ModeloAnthropic(
        anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value()), _TrazaLangfuse(langfuse), repo
    )

    # El grafo necesita `notificar` (Slack) y Slack necesita iniciar/retomar (grafo): se cierra el ciclo con `g`.
    g: dict[str, Any] = {}
    app_slack = App(token=settings.SLACK_BOT_TOKEN.get_secret_value())

    def iniciar(tema: str, origem: Any = "editor") -> str:
        return grafo.iniciar(g["grafo"], tema, origem)

    def retomar(*args: Any, **kwargs: Any) -> None:
        grafo.retomar(g["grafo"], *args, **kwargs)

    notificar = slack.registrar(
        app_slack,
        iniciar=iniciar,
        retomar=retomar,
        repo=repo,
        canal=settings.SLACK_CANAL,
        cliente=app_slack.client,
    )
    deps = montar_dependencias(
        settings,
        {
            "modelo": modelo,
            "buscador": criar_buscador(api_key=settings.TAVILY_API_KEY),
            "repo": repo,
            "notificar": notificar,
        },
    )
    # El checkpointer usa su propia conexión (autocommit + dict_row, como exige PostgresSaver).
    cp_conn = psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row, prepare_threshold=0)
    checkpointer = PostgresSaver(cp_conn)
    checkpointer.setup()
    g["grafo"] = grafo.construir(deps, checkpointer)

    expira = settings.LINKEDIN_TOKEN_EXPIRES_AT
    agenda = Agenda(
        {"linkedin": PublicadorLinkedin(settings)},
        repo,
        _AvisoSlack(app_slack.client, settings.SLACK_CANAL),
        lambda: datetime.now(UTC),
        token_expira_em=datetime.fromisoformat(expira) if expira else None,
    )
    threading.Thread(target=_bucle_agenda, args=(agenda,), daemon=True).start()
    SocketModeHandler(app_slack, settings.SLACK_APP_TOKEN.get_secret_value()).connect()

    api = criar_api(settings, iniciar=iniciar, ping=lambda: conn.execute("SELECT 1"))
    uvicorn.run(api, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
