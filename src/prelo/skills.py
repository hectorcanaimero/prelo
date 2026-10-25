"""Skills de escritura (`skills/<nombre>/SKILL.md`): instrucciones y ejemplos que van tal cual en el prompt.

Mismo patrón que agno-content: el texto de la skill sin su cabecera YAML, directo en las instrucciones del agente.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@cache
def skill(*nomes: str) -> str:
    partes = []
    for n in nomes:
        corpo = re.sub(
            r"\A---\n.*?\n---\n", "", (SKILLS_DIR / n / "SKILL.md").read_text(encoding="utf-8"), flags=re.DOTALL
        )
        partes.append(f'<skill nome="{n}">\n{corpo.strip()}\n</skill>')
    return "\n\n".join(partes)
