"""Tests para el buscador Tavily (`prelo.buscador`) y el agente `investigador` (`prelo.agentes.investigador`)."""

from __future__ import annotations

from typing import Any

import pytest

from prelo.agentes.investigador import SemFontesError, criar_investigador, investigar
from prelo.buscador import BuscadorTavily
from prelo.interfaces import Buscador


class ModeloFalso:
    """Doble de `Modelo` que devuelve consultas predefinidas y registra llamadas."""

    def __init__(self, resposta: str = "langgraph checkpointer postgres\nagentes ia producao") -> None:
        self.resposta = resposta
        self.chamadas: list[dict[str, str]] = []

    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str:
        self.chamadas.append({"prompt": prompt, "agente": agente, "post_id": post_id})
        return self.resposta


class ClienteTavilyFalso:
    """Doble del cliente `TavilyClient` que devuelve respuestas por consulta o globales."""

    def __init__(self, resultados: list[dict[str, Any]] | dict[str, list[dict[str, Any]]]) -> None:
        self.resultados = resultados
        self.consultas: list[tuple[str, int]] = []

    def search(self, query: str, *, max_results: int = 5, **kwargs: Any) -> dict[str, Any]:
        self.consultas.append((query, max_results))
        if isinstance(self.resultados, dict):
            itens = self.resultados.get(query, [])
        else:
            itens = self.resultados
        return {"results": itens}


def test_tema_devuelve_al_menos_una_fonte_con_los_tres_campos() -> None:
    """Un tema arma consultas con el Modelo y devuelve al menos una Fonte con url, titulo y trecho no vacíos."""
    modelo = ModeloFalso("LangGraph checkpointer Postgres")
    cliente_tavily = ClienteTavilyFalso(
        [
            {
                "url": "https://langchain-ai.github.io/langgraph/how-tos/persistence/",
                "title": "LangGraph Persistence",
                "content": "PostgresSaver permite persistir el estado de un grafo en Postgres.",
            }
        ]
    )
    buscador = BuscadorTavily(cliente_tavily)

    fontes = investigar("Persistencia en LangGraph", modelo=modelo, buscador=buscador, post_id="post-1")

    assert len(fontes) >= 1
    fonte = fontes[0]
    assert set(fonte.keys()) == {"url", "titulo", "trecho"}
    assert fonte["url"] == "https://langchain-ai.github.io/langgraph/how-tos/persistence/"
    assert fonte["titulo"] == "LangGraph Persistence"
    assert fonte["trecho"] == "PostgresSaver permite persistir el estado de un grafo en Postgres."
    assert len(modelo.chamadas) == 1
    assert "Persistencia en LangGraph" in modelo.chamadas[0]["prompt"]
    assert modelo.chamadas[0]["agente"] == "investigador"
    assert modelo.chamadas[0]["post_id"] == "post-1"
    assert cliente_tavily.consultas == [("LangGraph checkpointer Postgres", 5)]


def test_dos_resultados_con_la_misma_url_quedan_en_una_sola_fuente() -> None:
    """Dos resultados con la misma URL (en la misma búsqueda o entre consultas) se deduplican en una sola Fonte."""
    modelo = ModeloFalso("consulta uno\nconsulta dos")
    cliente_tavily = ClienteTavilyFalso(
        {
            "consulta uno": [
                {
                    "url": "https://example.com/artigo",
                    "title": "Artigo Original",
                    "content": "Primer fragmento citado de la fuente.",
                },
                {
                    "url": "https://example.com/artigo",
                    "title": "Artigo Duplicado Misma Busqueda",
                    "content": "Segundo fragmento duplicado en la misma consulta.",
                },
            ],
            "consulta dos": [
                {
                    "url": "https://example.com/artigo",
                    "title": "Artigo Duplicado Otra Busqueda",
                    "content": "Fragmento repetido en la segunda consulta.",
                },
                {
                    "url": "https://example.com/outro",
                    "title": "Outro Artigo",
                    "content": "Contenido distinto de otra URL.",
                },
            ],
        }
    )
    buscador = BuscadorTavily(cliente_tavily)

    fontes = investigar("Agentes con memoria", modelo=modelo, buscador=buscador, post_id="post-2")

    assert [f["url"] for f in fontes] == [
        "https://example.com/artigo",
        "https://example.com/outro",
    ]
    assert fontes[0]["titulo"] == "Artigo Original"
    assert fontes[0]["trecho"] == "Primer fragmento citado de la fuente."


def test_resultado_sin_contenido_se_descarta() -> None:
    """Resultados sin contenido (vacío, espacios o None) o sin título/URL se descartan."""
    modelo = ModeloFalso("consulta de prueba")
    cliente_tavily = ClienteTavilyFalso(
        [
            {"url": "https://example.com/vacio", "title": "Sin Contenido", "content": ""},
            {"url": "https://example.com/espacios", "title": "Solo Espacios", "content": "   \n\t  "},
            {"url": "https://example.com/none", "title": "Contenido None", "content": None},
            {"url": "https://example.com/sin-titulo", "title": "   ", "content": "Tiene contenido pero no título"},
            {"url": "   ", "title": "Sin URL", "content": "Tiene contenido pero no URL"},
            {
                "url": "https://example.com/valido",
                "title": "Resultado Válido",
                "content": "Contenido útil con un dato del 42%.",
            },
        ]
    )
    buscador = BuscadorTavily(cliente_tavily)

    fontes = investigar("Datos verificables", modelo=modelo, buscador=buscador, post_id="post-3")

    assert fontes == [
        {
            "url": "https://example.com/valido",
            "titulo": "Resultado Válido",
            "trecho": "Contenido útil con un dato del 42%.",
        }
    ]


def test_sin_ninguna_fuente_levanta_error_con_motivo_legible() -> None:
    """Si tras buscar no queda ninguna fuente válida, levanta un error con un motivo legible para Slack (FR-1)."""
    modelo = ModeloFalso("tema oscuro sin resultados")
    cliente_tavily = ClienteTavilyFalso(
        [
            {"url": "https://example.com/vacio", "title": "Vacío", "content": ""},
        ]
    )
    buscador = BuscadorTavily(cliente_tavily)

    with pytest.raises(ValueError) as exc_info:
        investigar("Tema sin fuentes", modelo=modelo, buscador=buscador, post_id="post-4")

    motivo = str(exc_info.value)
    assert motivo.strip()
    assert "Tema sin fuentes" in motivo
    assert "fuente" in motivo.lower()


def test_buscador_tavily_respeta_max_resultados_y_cumple_contrato() -> None:
    """BuscadorTavily respeta max_resultados, deduplica y filtra vacíos directamente en buscar()."""
    cliente_tavily = ClienteTavilyFalso(
        [
            {"url": "https://example.com/1", "title": "Uno", "content": "Trecho 1"},
            {"url": "https://example.com/1", "title": "Uno dup", "content": "Trecho 1 dup"},
            {"url": "https://example.com/vacio", "title": "Vacío", "content": ""},
            {"url": "https://example.com/2", "title": "Dos", "content": "Trecho 2"},
            {"url": "https://example.com/3", "title": "Tres", "content": "Trecho 3"},
        ]
    )
    buscador: Buscador = BuscadorTavily(cliente_tavily)

    fontes = buscador.buscar("consulta", max_resultados=2)

    assert len(fontes) == 2
    assert [f["url"] for f in fontes] == ["https://example.com/1", "https://example.com/2"]
    assert buscador.buscar("   ", max_resultados=5) == []
    assert buscador.buscar("consulta", max_resultados=0) == []


def test_criar_investigador_produce_callable_para_dependencias() -> None:
    """criar_investigador devuelve un callable (tema, *, post_id) -> list[Fonte] apto para Dependencias.investigar."""
    modelo = ModeloFalso("1. primera consulta\n- segunda consulta")
    cliente_tavily = ClienteTavilyFalso(
        {
            "primera consulta": [
                {"url": "https://example.com/a", "title": "A", "content": "Contenido A"},
            ],
            "segunda consulta": [
                {"url": "https://example.com/b", "title": "B", "content": "Contenido B"},
            ],
        }
    )
    fn_investigar = criar_investigador(modelo, BuscadorTavily(cliente_tavily))

    fontes = fn_investigar("Observabilidad con Langfuse", post_id="post-5")

    assert [f["url"] for f in fontes] == ["https://example.com/a", "https://example.com/b"]
    assert cliente_tavily.consultas == [("primera consulta", 5), ("segunda consulta", 5)]

    with pytest.raises(SemFontesError):
        fn_investigar("   ", post_id="post-vacio")



