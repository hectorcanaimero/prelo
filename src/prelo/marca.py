"""Revisión de marca determinista (D3): empleadores, frases de IA, cifras sin fuente."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from prelo.config import Settings
from prelo.interfaces import Fonte, Violacao

MARCA_TOML = Path(__file__).resolve().parents[2] / "marca.toml"


@dataclass(frozen=True)
class Regras:
    bloqueia: list[str]
    frases: list[str]
    padroes: list[str]
    linkedin: dict[str, int] = field(default_factory=dict)


def _norm(s: str) -> str:
    # Un carácter por carácter, para mapear posiciones al texto original.
    return "".join((unicodedata.normalize("NFKD", c)[0]).casefold()[:1] for c in s)


def carregar_regras(settings: Settings, ruta: Path = MARCA_TOML) -> Regras:
    dados = tomllib.loads(ruta.read_text(encoding="utf-8"))
    return Regras(
        bloqueia=list(settings.PRELO_BLOQUEIA),
        frases=list(dados["frases"]),
        padroes=list(dados["padroes"]),
        linkedin=dict(dados.get("linkedin", {})),
    )


def _achar(texto: str, termo: str) -> list[str]:
    pat = rf"(?<!\w){re.escape(_norm(termo))}(?!\w)"
    return [texto[m.start() : m.end()] for m in re.finditer(pat, _norm(texto))]


def _cifra(s: str) -> str:
    # "57,3%" (es/pt) y "57.3 %" (en) son la misma cifra: un solo separador decimal y sin espacio antes de "%"
    return re.sub(r"\s+%", "%", s.replace(",", "."))


def _item_de_lista(texto: str, m: re.Match[str]) -> bool:
    """El "4" de "4. Mide…" al empezar una línea numera una lista; no es una cifra."""
    antes = texto[: m.start()].rsplit("\n", 1)[-1]
    return not antes.strip() and re.match(r"[.)]\s", texto[m.end() : m.end() + 2]) is not None


EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff]")
HASHTAG = re.compile(r"(?<![\w#])#\w+")
LINK = re.compile(r"https?://\S+")


def formato(texto: str, regras: dict[str, int]) -> list[Violacao]:
    """Lo medible del formato de un canal (palabras, emojis, hashtags); vacío si el canal no tiene reglas."""
    vs: list[Violacao] = []
    palavras = len(re.findall(r"\w+", LINK.sub("", HASHTAG.sub("", texto))))
    if "max_palavras" in regras and palavras > regras["max_palavras"]:
        vs.append({"regra": "formato", "trecho": f"{palavras} palabras", "detalhe": f"máximo {regras['max_palavras']}"})
    emojis = EMOJI.findall(texto)
    if "max_emojis" in regras and len(emojis) > regras["max_emojis"]:
        vs.append({"regra": "formato", "trecho": "".join(emojis), "detalhe": f"máximo {regras['max_emojis']} emojis"})
    tags = HASHTAG.findall(texto)
    if "hashtags" in regras and len(tags) != regras["hashtags"]:
        vs.append(
            {
                "regra": "formato",
                "trecho": " ".join(tags) or "sin hashtags",
                "detalhe": f"exactamente {regras['hashtags']} hashtags",
            }
        )
    return vs


def revisar(texto: str, fontes: list[Fonte], regras: Regras) -> list[Violacao]:
    vs: list[Violacao] = []
    for nome in regras.bloqueia:
        for trecho in _achar(texto, nome):
            vs.append({"regra": "empregador", "trecho": trecho, "detalhe": "nombre bloqueado"})
    for frase in regras.frases:
        for trecho in _achar(texto, frase):
            vs.append({"regra": "frase_ia", "trecho": trecho, "detalhe": f"frase: {frase}"})
    # ponytail: contención por subcadena; "40%" aceptaría "140%" en la fuente.
    fuentes = _cifra(" ".join(f["trecho"] for f in fontes))
    vistos: list[tuple[int, int]] = []
    for padrao in regras.padroes:
        for m in re.finditer(padrao, texto):
            if any(m.start() < e and s < m.end() for s, e in vistos):
                continue
            vistos.append((m.start(), m.end()))
            if _item_de_lista(texto, m):
                continue
            if _cifra(m.group()) not in fuentes:
                vs.append({"regra": "cifra_sem_fonte", "trecho": m.group(), "detalhe": "sin fuente"})
    return vs
