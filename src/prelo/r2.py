"""Subida de imágenes a Cloudflare R2 (S3 compatible, boto3)."""

from __future__ import annotations

from typing import Any


def subir(nome: str, dados: bytes, tipo: str, *, s3: Any, bucket: str, url_publica: str) -> str:
    """Sube `dados` como `nome` y devuelve su URL pública. `s3` es un cliente boto3 (R2_*)."""
    s3.put_object(Bucket=bucket, Key=nome, Body=dados, ContentType=tipo)
    return f"{url_publica.rstrip('/')}/{nome}"


def cliente_s3(settings: Any) -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID.get_secret_value(),
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY.get_secret_value(),
        region_name="auto",
    )
