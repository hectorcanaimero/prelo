"""`Juiz` sobre Jev (TypeSafe System One): juicios tipados con probabilidades, nunca texto (D16)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
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


class JuizRouter:
    """Jev por el endpoint `/v1/systemone` de 9router; prueba `modelos` en orden. `http` es un `httpx.Client`."""

    def __init__(self, http: Any, url: str, api_key: str, modelos: list[str], repo: Repositorio) -> None:
        self._http, self._url, self._key, self._modelos, self._repo = http, url.rstrip("/"), api_key, modelos, repo

    def avaliar(self, estado: dict, perguntas: dict, *, post_id: str | None = None) -> Respostas:
        for modelo in self._modelos:
            try:
                r = self._http.post(
                    self._url + "/v1/systemone",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"model": modelo, "state": estado, "questions": perguntas},
                    timeout=60,
                )
                r.raise_for_status()
                d = r.json()
                d = d.get("result", d)  # algunos proveedores (Cloudflare) envuelven la respuesta
                answers = {k: SimpleNamespace(**v) for k, v in d["answers"].items()}
                if set(answers) != set(perguntas):
                    raise ValueError("faltan respuestas")
            except Exception as e:  # noqa: BLE001 — cualquier fallo pasa al siguiente modelo
                # Sin `str(e)`: un error de httpx puede incluir la cabecera con la clave (NFR-3).
                log.warning("Jev vía 9router falló: modelo=%s %s", modelo, type(e).__name__)
                continue
            uso = d.get("usage") or {}
            if post_id is not None:
                self._repo.registrar_custo(
                    Custo(
                        post_id,
                        AGENTE,
                        d.get("model", modelo),
                        uso.get("input_tokens") or 0,
                        uso.get("output_tokens") or 0,
                        Decimal(str(uso.get("cost") or 0)),
                        datetime.now(UTC),
                    )
                )
            log.info("avaliar post_id=%s modelo=%s", post_id, d.get("model", modelo))
            return Respostas(answers)
        raise JuizIndisponivel("fallaron todos los modelos de Jev en 9router")


class JuizEmCadeia:
    """Prueba cada `Juiz` en orden hasta que uno responda (p. ej. 9router y luego TypeSafe directo)."""

    def __init__(self, *juizes: Juiz) -> None:
        self._juizes = juizes

    def avaliar(self, estado: dict, perguntas: dict, *, post_id: str | None = None) -> Respostas:
        for juiz in self._juizes:
            try:
                return juiz.avaliar(estado, perguntas, post_id=post_id)
            except JuizIndisponivel:
                continue
        raise JuizIndisponivel("ningún Juiz respondió")
