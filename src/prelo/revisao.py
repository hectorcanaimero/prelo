"""Revisión de marca determinista.

Un modelo puede saltarse una regla del prompt; esto no. Las reglas vienen de `marca.toml`
(versionado) y `marca.local.toml` (fuera de git, con los nombres reales de empleadores).
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Violacao:
    regra: str
    nivel: str  # "bloqueia" | "aviso"
    termo: str
    trecho: str


def carregar_regras(arquivos: list[Path] | None = None) -> dict[str, dict[str, list[str]]]:
    """Suma las listas de todos los archivos que existan."""
    arquivos = arquivos or [RAIZ / "marca.toml", RAIZ / "marca.local.toml"]
    regras: dict[str, dict[str, list[str]]] = {"bloqueia": {}, "aviso": {}}
    for arq in arquivos:
        if not arq.exists():
            continue
        dados = tomllib.loads(arq.read_text(encoding="utf-8"))
        for nivel, grupos in regras.items():
            for nome, termos in dados.get(nivel, {}).items():
                grupos.setdefault(nome, []).extend(termos)
    return regras


def _padrao(termo: str) -> re.Pattern:
    if re.fullmatch(r"\W+", termo):  # caracteres sueltos, p. ej. la raya larga
        return re.compile(re.escape(termo))
    return re.compile(r"(?<!\w)" + re.escape(termo) + r"(?!\w)", re.IGNORECASE)


def _trecho(texto: str, ini: int, fim: int, margem: int = 30) -> str:
    a, b = max(0, ini - margem), min(len(texto), fim + margem)
    return ("…" if a else "") + texto[a:b].replace("\n", " ").strip() + ("…" if b < len(texto) else "")


def revisar(texto: str, regras: dict[str, dict[str, list[str]]] | None = None) -> list[Violacao]:
    regras = regras if regras is not None else carregar_regras()
    achados: list[Violacao] = []
    for nivel, grupos in regras.items():
        for nome, termos in grupos.items():
            for termo in termos:
                for m in _padrao(termo).finditer(texto):
                    achados.append(Violacao(nome, nivel, termo, _trecho(texto, m.start(), m.end())))
    return achados


def bloqueia(violacoes: list[Violacao]) -> bool:
    return any(v.nivel == "bloqueia" for v in violacoes)
