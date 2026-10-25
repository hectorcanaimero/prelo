"""Prelo conversacional en Slack: un LLM decide qué acción pide el editor. Aprobar nunca es una de ellas (FR-7)."""

from __future__ import annotations

import json
import re
from typing import Any

from prelo.interfaces import Modelo

AGENTE = "prelo"
ACCIONES = ("iniciar", "pendientes", "sugerir", "editar", "aprobar", "charla")

PROMPT = """Eres Prelo, el asistente editorial de Héctor en Slack: investigas, escribes y adaptas posts para su blog,
LinkedIn e Instagram. Lee su mensaje y elige UNA acción:

- iniciar: quiere un post nuevo sobre un tema. "tema" = el tema con el enfoque que pida.
- pendientes: pregunta qué está pendiente, en qué va o el estado de sus posts.
- sugerir: pide ideas o temas.
- editar: pide cambios a una pieza. "comentario" = el cambio pedido, claro y completo.{nota_hilo}
- aprobar: pide aprobar, publicar o dar el visto bueno. Tú no puedes hacerlo: Héctor aprueba con el botón.
- charla: cualquier otra cosa. "respuesta" = una respuesta breve y útil en español; si no sabes qué quiere, explica
  lo que puedes hacer.

El mensaje va entre <mensaje> y </mensaje>.

<mensaje>
{mensaje}
</mensaje>

Responde solo con JSON: {{"accion": "...", "tema": "", "comentario": "", "respuesta": ""}}"""

NOTA_HILO = " Este mensaje es una respuesta en el hilo de una pieza pendiente: si pide cambios, es editar."
NOTA_SIN_HILO = " Solo se puede editar respondiendo en el hilo de la pieza."


def interpretar(modelo: Modelo, mensaje: str, *, en_hilo_de_pieza: bool) -> dict[str, str]:
    """Devuelve `{"accion", "tema", "comentario", "respuesta"}`; ante una salida rara, `charla` sin respuesta."""
    nota = NOTA_HILO if en_hilo_de_pieza else NOTA_SIN_HILO
    limpio = re.sub(r"</?\s*mensaje\s*>", "", mensaje, flags=re.IGNORECASE)  # el mensaje no cierra su delimitador
    crudo = modelo.gerar(PROMPT.format(mensaje=limpio, nota_hilo=nota), agente=AGENTE, post_id="").strip()
    if crudo.startswith("```"):
        crudo = crudo.partition("\n")[2].rsplit("```", 1)[0]
    try:
        d: Any = json.loads(crudo)
    except ValueError:
        d = {}
    if not isinstance(d, dict) or d.get("accion") not in ACCIONES:
        d = {"accion": "charla"}
    return {k: str(d.get(k) or "") for k in ("accion", "tema", "comentario", "respuesta")}
