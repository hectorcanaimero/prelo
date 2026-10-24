import base64
from types import SimpleNamespace

import pytest

from prelo.imagens import gerar_imagem
from prelo.r2 import subir

PNG = b"\x89PNG-fake"


class FakeOpenAI:
    def __init__(self, error=None):
        self.llamadas = []
        self.error = error
        self.images = self

    def generate(self, **kw):
        self.llamadas.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(PNG).decode())])


class FakeRepo:
    def __init__(self):
        self.custos = []

    def registrar_custo(self, custo):
        self.custos.append(custo)


class FakeS3:
    def __init__(self):
        self.puestos = []

    def put_object(self, **kw):
        self.puestos.append(kw)


def test_prompt_lleva_la_prohibicion_de_texto():
    ia = FakeOpenAI()
    assert gerar_imagem("un faro al amanecer", post_id="p1", openai=ia, repo=FakeRepo()) == PNG
    enviado = ia.llamadas[0]["prompt"].lower()
    assert ia.llamadas[0]["model"] == "gpt-image-1"
    assert "un faro al amanecer" in enviado
    assert "text" in enviado and "letters" in enviado and "numbers" in enviado


def test_registra_costo_con_agente_imagem():
    repo = FakeRepo()
    gerar_imagem("x", post_id="p1", openai=FakeOpenAI(), repo=repo)
    assert len(repo.custos) == 1
    assert repo.custos[0].agente == "imagem"
    assert repo.custos[0].post_id == "p1"
    assert repo.custos[0].usd > 0


def test_error_del_cliente_es_legible():
    repo = FakeRepo()
    with pytest.raises(RuntimeError, match="imagen.*p1"):
        gerar_imagem("x", post_id="p1", openai=FakeOpenAI(ValueError("boom")), repo=repo)
    assert repo.custos == []


def test_subir_devuelve_url_publica():
    s3 = FakeS3()
    url = subir("carrossel/a.png", PNG, "image/png", s3=s3, bucket="b", url_publica="https://cdn.x.com/")
    assert url == "https://cdn.x.com/carrossel/a.png"
    assert s3.puestos == [{"Bucket": "b", "Key": "carrossel/a.png", "Body": PNG, "ContentType": "image/png"}]
