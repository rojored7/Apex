"""Ayudas de S3 para las pruebas de `attachments` (S6-C1): constantes y `settings_s3`."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from app.core.config import Settings

BUCKET = "bucket-prueba"
ENDPOINT = "https://s3.prueba.example"
ACCESO, SECRETO = "AKIAPRUEBA0123456789", "secreto-de-prueba-0123456789-abcdefgh"


def settings_s3(base: Settings, **cambios: Any) -> Settings:
    ajustes: dict[str, Any] = {
        "STORAGE_PROVIDER": "s3",
        "S3_ENDPOINT_URL": ENDPOINT,
        "S3_BUCKET": BUCKET,
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": ACCESO,
        "S3_SECRET_ACCESS_KEY": SecretStr(SECRETO),
    }
    ajustes.update(cambios)
    return base.model_copy(update=ajustes)
