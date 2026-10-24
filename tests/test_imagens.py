from decimal import Decimal
from types import SimpleNamespace

import pytest

from prelo.imagens import gerar_imagem
from prelo.r2 import subir

PNG = b"\x89PNG-fake"


class FakeHttp:
    def __init__(self, error=None):
        self.posts = []
        self.gets = []
        self.error = error

    def post(self, url, **kw):
        self.posts.append((url, kw))
        if self.error:
            raise self.error
        return SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"images": [{"url": "https://fal.media/x.png"}]}
        )

    def get(self, url, **kw):
        self.gets.append(url)
        return SimpleNamespace(raise_for_status=lambda: None, content=PNG)


def gerar(http, repo=None, **kw):
    return gerar_imagem("x", post_id="p1", http=http, fal_key="k-secreta", repo=repo or FakeRepo(), **kw)


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
    http = FakeHttp()
    assert gerar_imagem("un faro al amanecer", post_id="p1", http=http, fal_key="k", repo=FakeRepo()) == PNG
    url, kw = http.posts[0]
    assert url == "https://fal.run/fal-ai/flux/schnell"
    assert kw["headers"] == {"Authorization": "Key k"}
    enviado = kw["json"]["prompt"].lower()
    assert "un faro al amanecer" in enviado
    assert "text" in enviado and "letters" in enviado and "numbers" in enviado
    assert http.gets == ["https://fal.media/x.png"]


def test_cualquier_modelo_de_fal_con_su_costo():
    http, repo = FakeHttp(), FakeRepo()
    gerar(http, repo, modelo="fal-ai/flux-pro/v1.1", usd=Decimal("0.04"))
    assert http.posts[0][0] == "https://fal.run/fal-ai/flux-pro/v1.1"
    assert repo.custos[0].modelo == "fal-ai/flux-pro/v1.1"
    assert repo.custos[0].usd == Decimal("0.04")


def test_registra_costo_con_agente_imagem():
    repo = FakeRepo()
    gerar(FakeHttp(), repo)
    assert len(repo.custos) == 1
    assert repo.custos[0].agente == "imagem"
    assert repo.custos[0].post_id == "p1"
    assert repo.custos[0].usd > 0


def test_error_del_cliente_es_legible_y_sin_la_clave():
    repo = FakeRepo()
    with pytest.raises(RuntimeError, match="imagen.*p1") as e:
        gerar(FakeHttp(ValueError("Authorization: Key k-secreta")), repo)
    assert "k-secreta" not in str(e.value)
    assert repo.custos == []


def test_subir_devuelve_url_publica():
    s3 = FakeS3()
    url = subir("carrossel/a.png", PNG, "image/png", s3=s3, bucket="b", url_publica="https://cdn.x.com/")
    assert url == "https://cdn.x.com/carrossel/a.png"
    assert s3.puestos == [{"Bucket": "b", "Key": "carrossel/a.png", "Body": PNG, "ContentType": "image/png"}]
