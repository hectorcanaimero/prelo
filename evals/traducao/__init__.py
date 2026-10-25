"""Suite de evals de traducción (F2.5.T2): agente, verificación de preservación y modelo local de respaldo."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any

from prelo.agentes.tradutor import tradutor
from prelo.interfaces import Texto, Violacao
from prelo.marca import Regras

_RE_CODIGO = re.compile(r"```[\s\S]*?```")
_RE_LINK = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)")


def formatar_traducao(traduzido: Mapping[str, Texto]) -> str:
    pt = traduzido["pt"]
    en = traduzido["en"]
    return f"[PT]\n{pt['titulo']}\n{pt['resumo']}\n{pt['corpo']}\n\n[EN]\n{en['titulo']}\n{en['resumo']}\n{en['corpo']}"


def _extraer_cifras(texto: str, padroes: list[str]) -> list[str]:
    vistos: list[tuple[int, int]] = []
    cifras: list[str] = []
    for padrao in padroes:
        for m in re.finditer(padrao, texto):
            if any(m.start() < e and s < m.end() for s, e in vistos):
                continue
            vistos.append((m.start(), m.end()))
            cifras.append(m.group())
    return cifras


def verificar_intacto(original: Mapping[str, str], texto_traducido: str, regras: Regras) -> list[Violacao]:
    """Verifica que cifras, links y bloques de código del original estén intactos en pt y en."""
    orig_completo = f"{original.get('titulo', '')}\n{original.get('resumo', '')}\n{original.get('corpo', '')}"
    secciones = (
        texto_traducido.split("\n\n[EN]\n", 1)
        if "[PT]\n" in texto_traducido and "\n\n[EN]\n" in texto_traducido
        else [texto_traducido]
    )
    vs: list[Violacao] = []

    esperadas = Counter(_extraer_cifras(orig_completo, regras.padroes))
    for cifra, cuenta in esperadas.items():
        if any(Counter(_extraer_cifras(sec, regras.padroes))[cifra] < cuenta for sec in secciones):
            vs.append({"regra": "cifra_sem_fonte", "trecho": cifra, "detalhe": "cifra original ausente o alterada"})

    for url in _RE_LINK.findall(orig_completo):
        if any(url not in sec for sec in secciones):
            vs.append({"regra": "cifra_sem_fonte", "trecho": url, "detalhe": "link original ausente o alterado"})

    for bloque in _RE_CODIGO.findall(original.get("corpo", "")):
        if any(bloque not in sec for sec in secciones):
            vs.append({"regra": "cifra_sem_fonte", "trecho": bloque[:40], "detalhe": "código original alterado"})

    return vs


def criar_agente(modelo_o_tradutor: Any) -> Callable[[dict[str, Any]], str]:
    """Construye el agente de `evals/traducao` a partir de un `Modelo` o de una función `traduzir`."""

    def correr(caso: dict[str, Any]) -> str:
        pid = f"eval-{caso['id']}"
        es: Texto = caso.get("texto") or {
            "titulo": str(caso.get("tema", "")),
            "resumo": str(caso.get("tema", "")),
            "corpo": "\n".join(f["trecho"] for f in caso.get("fontes", [])),
        }
        if hasattr(modelo_o_tradutor, "gerar"):
            res = tradutor(modelo_o_tradutor, es, post_id=pid)
        else:
            res = modelo_o_tradutor(es, post_id=pid)
        if isinstance(res, str):
            return res
        return formatar_traducao(res)

    return correr


class ModeloLocalDeterminista:
    """Doble determinista usado cuando `ROUTER_API_KEY` no está definido en el entorno local."""

    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str:
        if agente == "juiz":
            return json.dumps({"nota": 1.0})
        if agente == "tradutor" and "<texto>\n" in prompt and "\n</texto>" in prompt:
            bloque = prompt.split("<texto>\n", 1)[1].rsplit("\n</texto>", 1)[0]
            lineas = bloque.splitlines()
            titulo = lineas[0].removeprefix("titulo: ")
            resumo = lineas[1].removeprefix("resumo: ")
            corpo = "\n".join(lineas[3:])
            trad: Texto = {"titulo": titulo, "resumo": resumo, "corpo": corpo}
            return json.dumps({"pt": trad, "en": trad})
        if agente == "redator":
            trechos = re.findall(r"<fonte>([\s\S]*?)</fonte>", prompt)
            corpo = "\n".join(t.strip() for t in trechos) or "Contenido de prueba."
            return json.dumps({"titulo": f"Post {post_id}", "resumo": "Resumen técnico.", "corpo": corpo})
        return "Texto adaptado en português do Brasil."
