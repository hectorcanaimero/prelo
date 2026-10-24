"""Cliente de búsqueda web sobre Tavily (D13)."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import SecretStr
from tavily import TavilyClient  # type: ignore[import-untyped]

from prelo.interfaces import Buscador, Fonte


class ClienteTavily(Protocol):
    """Protocolo mínimo del cliente de Tavily que consume `BuscadorTavily`."""

    def search(self, query: str, **kwargs: Any) -> Any:
        """Ejecuta una búsqueda en Tavily y devuelve un diccionario con `results`."""
        ...


def _extrair_chave(api_key: str | SecretStr | None) -> str | None:
    if api_key is None:
        return None
    if isinstance(api_key, SecretStr):
        return api_key.get_secret_value()
    return str(api_key)


class BuscadorTavily:
    """Implementación del protocolo `Buscador` de `prelo.interfaces` sobre Tavily."""

    def __init__(
        self,
        cliente: ClienteTavily | str | SecretStr | None = None,
        *,
        api_key: str | SecretStr | None = None,
    ) -> None:
        if cliente is not None and callable(getattr(cliente, "search", None)):
            self._cliente: Any = cliente
        else:
            chave = _extrair_chave(api_key if api_key is not None else cliente)  # type: ignore[arg-type]
            self._cliente = TavilyClient(api_key=chave)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    def buscar(self, consulta: str, *, max_resultados: int = 5) -> list[Fonte]:
        """Devuelve hasta `max_resultados` fuentes para `consulta`."""
        consulta_limpa = consulta.strip()
        if not consulta_limpa or max_resultados <= 0:
            return []

        resposta = self._executar_busca(consulta_limpa, max_resultados=max_resultados)
        itens = self._extrair_itens(resposta)

        fontes: list[Fonte] = []
        urls_vistas: set[str] = set()
        for item in itens:
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url") or "").strip()
            titulo = str(item.get("title") or item.get("titulo") or "").strip()
            trecho = str(item.get("content") or item.get("trecho") or "").strip()
            if not url or not titulo or not trecho:
                continue
            if url in urls_vistas:
                continue
            urls_vistas.add(url)
            fontes.append(Fonte(url=url, titulo=titulo, trecho=trecho))
            if len(fontes) >= max_resultados:
                break
        return fontes

    def _executar_busca(self, consulta: str, *, max_resultados: int) -> Any:
        try:
            sig = inspect.signature(self._cliente.search)
            aceita_max = "max_results" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
        except (TypeError, ValueError):
            aceita_max = True

        if aceita_max:
            return self._cliente.search(consulta, max_results=max_resultados)
        return self._cliente.search(consulta)

    @staticmethod
    def _extrair_itens(resposta: Any) -> Sequence[Any]:
        if isinstance(resposta, Mapping):
            resultados = resposta.get("results", [])
            if isinstance(resultados, Sequence) and not isinstance(resultados, (str, bytes)):
                return resultados
            return []
        if isinstance(resposta, Sequence) and not isinstance(resposta, (str, bytes)):
            return resposta
        return []


TavilyBuscador = BuscadorTavily


def criar_buscador(
    cliente: ClienteTavily | str | SecretStr | None = None,
    *,
    api_key: str | SecretStr | None = None,
) -> Buscador:
    """Construye un `Buscador` respaldado por Tavily."""
    return BuscadorTavily(cliente, api_key=api_key)


__all__ = ["BuscadorTavily", "ClienteTavily", "TavilyBuscador", "criar_buscador"]
