"""`Modelo` real sobre el SDK de Anthropic, con costos en `custos` y trazas en Langfuse."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from prelo.custos import calcular_usd
from prelo.interfaces import Custo, Repositorio

log = logging.getLogger(__name__)

# D4: fuerte para el redactor, barato para el resto. Configurable.
MODELO_FUERTE = "claude-sonnet-5-5"
MODELO_BARATO = "claude-haiku-5-5"
MODELO_POR_AGENTE: dict[str, str] = {"redator": MODELO_FUERTE}


class ModeloAnthropic:
    def __init__(
        self,
        anthropic: Any,
        langfuse: Any,
        repo: Repositorio,
        *,
        modelo_por_agente: dict[str, str] | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._anthropic = anthropic
        self._langfuse = langfuse
        self._repo = repo
        self._tabla = MODELO_POR_AGENTE if modelo_por_agente is None else modelo_por_agente
        self._max_tokens = max_tokens

    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str:
        modelo = self._tabla.get(agente, MODELO_BARATO)
        try:
            resp = self._anthropic.messages.create(
                model=modelo,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            raise RuntimeError(
                f"fallo la llamada a Anthropic: agente={agente} post_id={post_id} modelo={modelo}: {type(e).__name__}"
            ) from e
        texto = "".join(b.text for b in resp.content if hasattr(b, "text"))
        tin, tout = resp.usage.input_tokens, resp.usage.output_tokens
        usd = calcular_usd(modelo, tin, tout)
        self._repo.registrar_custo(Custo(post_id, agente, modelo, tin, tout, usd, datetime.now(UTC)))
        # Solo prompt, salida, modelo y uso: nunca credenciales (NFR-3).
        # ponytail: llamada langfuse.trace(...) duck-typed; adaptar al SDK real en app.py si difiere.
        self._langfuse.trace(
            name=agente,
            input=prompt,
            output=texto,
            tags=[agente],
            metadata={
                "post_id": post_id,
                "agente": agente,
                "modelo": modelo,
                "tokens_entrada": tin,
                "tokens_saida": tout,
                "usd": str(usd),
            },
        )
        log.info("gerar agente=%s post_id=%s modelo=%s tin=%d tout=%d", agente, post_id, modelo, tin, tout)
        return texto
