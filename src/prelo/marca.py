"""Revisión de marca determinista (D3): empleadores, frases de IA, cifras sin fuente."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from prelo.config import Settings
from prelo.interfaces import Fonte, Violacao

MARCA_TOML = Path(__file__).resolve().parents[2] / "marca.toml"


@dataclass(frozen=True)
class Regras:
    bloqueia: list[str]
    frases: list[str]
    padroes: list[str]


def _norm(s: str) -> str:
    # Un carácter por carácter, para mapear posiciones al texto original.
    return "".join((unicodedata.normalize("NFKD", c)[0]).casefold()[:1] for c in s)


def carregar_regras(settings: Settings, ruta: Path = MARCA_TOML) -> Regras:
    dados = tomllib.loads(ruta.read_text(encoding="utf-8"))
    return Regras(
        bloqueia=list(settings.PRELO_BLOQUEIA),
        frases=list(dados["frases"]),
        padroes=list(dados["padroes"]),
    )


def _achar(texto: str, termo: str) -> list[str]:
    pat = rf"(?<!\w){re.escape(_norm(termo))}(?!\w)"
    return [texto[m.start() : m.end()] for m in re.finditer(pat, _norm(texto))]


def revisar(texto: str, fontes: list[Fonte], regras: Regras) -> list[Violacao]:
    vs: list[Violacao] = []
    for nome in regras.bloqueia:
        for trecho in _achar(texto, nome):
            vs.append({"regra": "empregador", "trecho": trecho, "detalhe": "nombre bloqueado"})
    for frase in regras.frases:
        for trecho in _achar(texto, frase):
            vs.append({"regra": "frase_ia", "trecho": trecho, "detalhe": f"frase: {frase}"})
    # ponytail: contención por subcadena; "40%" aceptaría "140%" en la fuente.
    fuentes = " ".join(f["trecho"] for f in fontes)
    vistos: list[tuple[int, int]] = []
    for padrao in regras.padroes:
        for m in re.finditer(padrao, texto):
            if any(m.start() < e and s < m.end() for s, e in vistos):
                continue
            vistos.append((m.start(), m.end()))
            if m.group() not in fuentes:
                vs.append({"regra": "cifra_sem_fonte", "trecho": m.group(), "detalhe": "sin fuente"})
    return vs
