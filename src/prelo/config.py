"""Configuración central de Prelo (variables de entorno)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_bloqueia(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_secret(value: object) -> SecretStr | str:
    if value is None:
        return SecretStr("")
    if isinstance(value, SecretStr):
        return value
    return SecretStr(str(value))


SecretToken = Annotated[SecretStr, BeforeValidator(_coerce_secret)]
ListaBloqueia = Annotated[list[str], NoDecode, BeforeValidator(_parse_bloqueia)]


class Settings(BaseSettings):
    """Configuración cargada desde variables de entorno o archivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str = ""

    ANTHROPIC_API_KEY: SecretToken = SecretStr("")
    FAL_KEY: SecretToken = SecretStr("")
    FAL_MODELO_IMAGEN: str = "fal-ai/flux/schnell"
    FAL_USD_POR_IMAGEN: Decimal = Decimal("0.003")
    TAVILY_API_KEY: SecretToken = SecretStr("")
    TYPESAFE_API_KEY: SecretToken = SecretStr("")

    SLACK_BOT_TOKEN: SecretToken = SecretStr("")
    SLACK_APP_TOKEN: SecretToken = SecretStr("")
    SLACK_CANAL: str = ""

    LINKEDIN_TOKEN: SecretToken = SecretStr("")
    LINKEDIN_AUTHOR_URN: str = ""
    LINKEDIN_TOKEN_EXPIRES_AT: str = ""

    GITHUB_TOKEN: SecretToken = SecretStr("")
    GITHUB_WEBHOOK_SECRET: SecretToken = SecretStr("")
    GITHUB_REPO: str = "hectorcanaimero/site-guria"

    IG_TOKEN: SecretToken = SecretStr("")
    IG_USER_ID: str = ""

    R2_ACCOUNT_ID: str = ""
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: SecretToken = SecretStr("")
    R2_SECRET_ACCESS_KEY: SecretToken = SecretStr("")
    R2_BUCKET: str = ""
    R2_PUBLIC_URL: str = ""

    LANGFUSE_PUBLIC_KEY: SecretToken = SecretStr("")
    LANGFUSE_SECRET_KEY: SecretToken = SecretStr("")
    LANGFUSE_HOST: str = "http://localhost:3000"

    PRELO_API_TOKEN: SecretToken = SecretStr("")
    PRELO_BLOQUEIA: ListaBloqueia = Field(default_factory=list)
    PRELO_UMBRAL_APROVACAO: float = 0.6
