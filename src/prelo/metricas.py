"""Worker diario de métricas (FR-15): reacciones y comentarios de cada publicación de LinkedIn e Instagram."""

from __future__ import annotations

from typing import Any, Protocol

from prelo.interfaces import Publicacao

CANAIS = ("linkedin", "instagram")


class Leitor(Protocol):
    canal: str

    def ler(self, publicacao: Publicacao) -> dict[str, Any]:
        """Devuelve `{"reacoes": int, "comentarios": list}`."""
        ...


def coletar(leitores: list[Leitor], repo: Any) -> int:
    """Guarda una fila por publicación; salta las que no tienen lector de su canal. Devuelve las filas guardadas."""
    por_canal = {leitor.canal: leitor for leitor in leitores}
    n = 0
    for pub in repo.listar_publicacoes(canais=CANAIS):
        leitor = por_canal.get(pub.canal)
        if leitor is None:
            continue
        m = leitor.ler(pub)
        repo.salvar_metrica(pub.id, reacoes=m["reacoes"], comentarios=m["comentarios"])
        n += 1
    return n
