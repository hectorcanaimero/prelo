"""`Juiz` sobre Jev (TypeSafe System One): juicios tipados con probabilidades, nunca texto (D16)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from prelo.interfaces import Custo, Repositorio

log = logging.getLogger(__name__)

AGENTE = "juizo"
# ponytail: TypeSafe cobra fuera de esta tabla; USD 0 hasta fijar su precio por token.
USD_POR_LLAMADA = Decimal(0)


class JuizIndisponivel(Exception):
    """TypeSafe falló: quien llama decide si sigue sin el juicio."""


class Respostas:
    """Respuestas de Jev por nombre de pregunta propio del código."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers

    def noul(self, id: str) -> float:
        return self._answers[id].noul

    def choice(self, id: str) -> str:
        return self._answers[id].choice

    def score(self, id: str) -> float:
        return self._answers[id].score


class Juiz(Protocol):
    def avaliar(self, estado: dict, perguntas: dict, *, post_id: str | None = None) -> Respostas: ...


class JuizTypeSafe:
    """`client_factory()` devuelve un context manager tipo `TypeSafeClient(api_key=...)`."""

    def __init__(self, client_factory: Callable[[], Any], repo: Repositorio) -> None:
        self._client_factory = client_factory
        self._repo = repo

    def avaliar(self, estado: dict, perguntas: dict, *, post_id: str | None = None) -> Respostas:
        try:
            with self._client_factory() as client:
                resp = client.system_one(state=estado, questions=perguntas)
        except Exception as e:
            raise JuizIndisponivel(f"fallo TypeSafe: {type(e).__name__}") from e
        # custos.post_id es NOT NULL: sin post_id (llamada fuera de un post) no hay fila.
        if post_id is not None:
            self._repo.registrar_custo(
                Custo(
                    post_id,
                    AGENTE,
                    resp.model,
                    resp.usage.input_tokens or 0,
                    resp.usage.output_tokens or 0,
                    USD_POR_LLAMADA,
                    datetime.now(UTC),
                )
            )
        log.info("avaliar post_id=%s modelo=%s", post_id, resp.model)
        return Respostas(resp.answers)
