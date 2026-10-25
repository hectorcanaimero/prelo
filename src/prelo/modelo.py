"""`Modelo` real sobre 9router (SDK de OpenAI, NFR-9), con costos en `custos` y trazas en Langfuse."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from prelo.custos import calcular_usd
from prelo.interfaces import Custo, Repositorio

log = logging.getLogger(__name__)


class ModeloRouter:
    """Cada agente pide a 9router el modelo (combo) con su mismo nombre, salvo que `modelo_por_agente` diga otro.

    `openai` es un cliente `OpenAI(base_url=<9router>/v1, api_key=...)`. Se pide siempre en streaming: 9router responde
    con SSE en casi todos los combos aunque no se pida.
    """

    def __init__(
        self,
        openai: Any,
        langfuse: Any,
        repo: Repositorio,
        *,
        modelo_por_agente: dict[str, str] | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._openai = openai
        self._langfuse = langfuse
        self._repo = repo
        self._tabla = modelo_por_agente or {}
        self._max_tokens = max_tokens

    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str:
        pedido = self._tabla.get(agente, agente)
        partes: list[str] = []
        modelo, tin, tout = pedido, 0, 0
        try:
            for ch in self._openai.chat.completions.create(
                model=pedido,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True},
            ):
                modelo = ch.model or modelo
                if ch.choices and ch.choices[0].delta.content:
                    partes.append(ch.choices[0].delta.content)
                if ch.usage:
                    tin, tout = ch.usage.prompt_tokens or 0, ch.usage.completion_tokens or 0
        except Exception as e:
            raise RuntimeError(
                f"fallo la llamada a 9router: agente={agente} post_id={post_id} modelo={pedido}: {type(e).__name__}"
            ) from e
        texto = "".join(partes)
        usd = calcular_usd(modelo, tin, tout)
        # `modelo` es el que respondió de verdad dentro del combo, no el nombre del combo.
        self._repo.registrar_custo(Custo(post_id, agente, modelo, tin, tout, usd, datetime.now(UTC)))
        # Solo prompt, salida, modelo y uso: nunca credenciales (NFR-3).
        self._langfuse.trace(
            name=agente,
            input=prompt,
            output=texto,
            tags=[agente],
            metadata={
                "post_id": post_id,
                "agente": agente,
                "combo": pedido,
                "modelo": modelo,
                "tokens_entrada": tin,
                "tokens_saida": tout,
                "usd": str(usd),
            },
        )
        log.info("gerar agente=%s post_id=%s modelo=%s tin=%d tout=%d", agente, post_id, modelo, tin, tout)
        return texto
