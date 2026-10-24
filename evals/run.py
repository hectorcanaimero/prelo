"""Runner de evals (NFR-2): cada subdirectorio de `evals/` con un `casos.json` es una suite.

`casos.json`: {"umbrais": {"fidelidade": 0.8, "estilo": 0.7}, "rubrica": "...", "casos": [{"id", "tema", "fontes"}]}.
El nombre del directorio es el nombre del agente en `AGENTES`. Sale con 1 si una métrica queda bajo su umbral
o si `revisar` encuentra una violación de marca (umbral 0).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from prelo.marca import Regras, revisar

RAIZ = Path(__file__).resolve().parent

Agente = Callable[[dict[str, Any]], str]  # caso -> texto producido
Juiz = Callable[[str, str, dict[str, Any], str], float]  # (metrica, texto, caso, rubrica) -> nota 0..1

PROMPT_JUIZ = {
    "fidelidade": "¿Qué fracción de las afirmaciones del TEXTO están respaldadas por las FUENTES? 1 = todas, 0 = ninguna.",
    "estilo": "Puntúa el TEXTO de 0 a 1 según esta rúbrica:\n{rubrica}",
}


def main(
    raiz: Path,
    agentes: dict[str, Agente],
    juiz: Juiz,
    regras: Regras,
    custo: Callable[[], Decimal],
) -> int:
    falhas: list[str] = []
    for suite in sorted(p.parent for p in raiz.glob("*/casos.json")):
        cfg = json.loads((suite / "casos.json").read_text(encoding="utf-8"))
        nome, agente = suite.name, agentes[suite.name]
        notas: dict[str, list[float]] = {"fidelidade": [], "estilo": []}
        marca = 0
        for caso in cfg["casos"]:
            texto = agente(caso)
            for m, lista in notas.items():
                lista.append(juiz(m, texto, caso, cfg.get("rubrica", "")))
            vs = revisar(texto, caso["fontes"], regras)
            marca += len(vs)
            for v in vs:
                print(f"  {nome}/{caso['id']}: marca {v['regra']} {v['trecho']!r}")
        medias = {m: sum(v) / len(v) for m, v in notas.items() if v}
        for m, media in medias.items():
            umbral = cfg["umbrais"][m]
            print(f"{nome}/{m}: {media:.2f} (umbral {umbral})")
            if media < umbral:
                falhas.append(f"{nome}/{m}")
        print(f"{nome}/marca: {marca} violaciones (umbral 0)")
        if marca:
            falhas.append(f"{nome}/marca")
    print(f"Costo de la corrida: USD {custo()}")
    for f in falhas:
        print(f"FALLA {f}")
    return 1 if falhas else 0


# --- cableado real (no lo usan los tests) ---------------------------------------------------------------------


def _agente_linkedin(modelo: Any) -> Agente:
    from prelo.agentes.adaptador_linkedin import adaptador_linkedin
    from prelo.agentes.redator import redator

    def correr(caso: dict[str, Any]) -> str:
        pid = f"eval-{caso['id']}"
        texto = redator(modelo, caso["tema"], caso["fontes"], post_id=pid)
        return adaptador_linkedin(modelo, texto, None, post_id=pid)["pt"]["corpo"]

    return correr


def _juiz(modelo: Any) -> Juiz:
    def julgar(metrica: str, texto: str, caso: dict[str, Any], rubrica: str) -> float:
        fontes = "\n".join(f["trecho"] for f in caso["fontes"])
        prompt = (
            PROMPT_JUIZ[metrica].format(rubrica=rubrica)
            + f"\n\nFUENTES:\n{fontes}\n\nTEXTO:\n{texto}\n\nResponde solo con JSON: {{\"nota\": 0.0}}"
        )
        salida = modelo.gerar(prompt, agente="juiz", post_id=f"eval-{caso['id']}")
        m = re.search(r"-?\d+(?:\.\d+)?", salida.partition(":")[2] or salida)
        if not m:
            raise ValueError(f"el juez no devolvió una nota: {salida[:200]!r}")
        return min(1.0, max(0.0, float(m.group())))

    return julgar


def _real() -> tuple[dict[str, Agente], Juiz, Regras, Callable[[], Decimal]]:
    from anthropic import Anthropic

    from prelo.config import Settings
    from prelo.marca import carregar_regras
    from prelo.modelo import ModeloAnthropic

    class Repo:  # solo suma el costo (Repositorio completo no hace falta aquí)
        total = Decimal(0)

        def registrar_custo(self, c: Any) -> None:
            self.total += c.usd

    class SinTraza:
        def trace(self, **_: Any) -> None: ...

    s = Settings()
    repo = Repo()
    modelo = ModeloAnthropic(Anthropic(api_key=s.ANTHROPIC_API_KEY.get_secret_value()), SinTraza(), repo)  # type: ignore[arg-type]
    return {"linkedin": _agente_linkedin(modelo)}, _juiz(modelo), carregar_regras(s), lambda: repo.total


if __name__ == "__main__":
    ags, jz, rg, ct = _real()
    sys.exit(main(RAIZ, ags, jz, rg, ct))
