"""Tests para src/prelo/config.py."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from prelo.config import Settings


def test_prelo_bloqueia_separa_por_comas_y_limpia_espacios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRELO_BLOQUEIA", "Acme, Foo ,")
    settings = Settings(_env_file=None)
    assert settings.PRELO_BLOQUEIA == ["Acme", "Foo"]


def test_sin_prelo_bloqueia_la_lista_es_vacia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRELO_BLOQUEIA", raising=False)
    settings = Settings(_env_file=None)
    assert settings.PRELO_BLOQUEIA == []


def test_repr_no_contiene_valor_de_slack_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    secreto = "xoxb-super-secreto-12345"
    monkeypatch.setenv("SLACK_BOT_TOKEN", secreto)
    settings = Settings(_env_file=None)
    assert isinstance(settings.SLACK_BOT_TOKEN, SecretStr)
    assert settings.SLACK_BOT_TOKEN.get_secret_value() == secreto
    assert secreto not in repr(settings)
    assert secreto not in str(settings)


def test_tokens_son_secret_str_y_no_salen_en_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = {
        "ANTHROPIC_API_KEY": "sk-ant-secreto",
        "TAVILY_API_KEY": "tvly-secreto",
        "SLACK_BOT_TOKEN": "xoxb-secreto",
        "SLACK_APP_TOKEN": "xapp-secreto",
        "LINKEDIN_TOKEN": "li-secreto",
        "GITHUB_TOKEN": "ghp-secreto",
        "GITHUB_WEBHOOK_SECRET": "whsec-secreto",
        "IG_TOKEN": "ig-secreto",
        "R2_ACCESS_KEY_ID": "r2-key-secreto",
        "R2_SECRET_ACCESS_KEY": "r2-secret-secreto",
        "LANGFUSE_PUBLIC_KEY": "pk-lf-secreto",
        "LANGFUSE_SECRET_KEY": "sk-lf-secreto",
        "PRELO_API_TOKEN": "prelo-api-secreto",
    }
    for clave, valor in tokens.items():
        monkeypatch.setenv(clave, valor)

    settings = Settings(_env_file=None)
    texto_repr = repr(settings)
    for clave, valor in tokens.items():
        campo = getattr(settings, clave)
        assert isinstance(campo, SecretStr)
        assert campo.get_secret_value() == valor
        assert valor not in texto_repr
