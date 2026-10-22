"""Estado de un post a lo largo del grafo."""

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class Fonte(BaseModel):
    url: str
    titulo: str
    trecho: str = Field(description="Fragmento que respalda una afirmación del texto")


class Rascunho(BaseModel):
    titulo: str
    resumo: str
    corpo: str = Field(description="Cuerpo en Markdown")

    def texto(self) -> str:
        return f"{self.titulo}\n\n{self.resumo}\n\n{self.corpo}"


class Decisao(BaseModel):
    decisao: Literal["aprovado", "editar", "descartar"]
    comentario: str = ""


class EstadoPost(TypedDict, total=False):
    tema: str
    idioma_base: str
    fontes: list[Fonte]
    rascunho: Rascunho
    violacoes: list[dict]
    tentativas: int
    feedback: str
    decisao: Decisao
    publicacoes: list[dict]
