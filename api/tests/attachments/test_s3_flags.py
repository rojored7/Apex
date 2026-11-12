"""Banderas del almacenamiento S3 en `storage_from_settings` (S6-C1, US-147; S6-D21, M-9).

S3 está apagado por defecto. `Settings` ya valida estas reglas al cargarse (W0-5); aquí se prueba
la SEGUNDA línea: `storage_from_settings` las vuelve a exigir sobre una copia sin validar
(`model_copy` no corre los validadores), porque el almacén es lo último que un error de
configuración podría saltarse. Contrato: errores de configuración = `ValueError` que nombra la
variable (nunca su valor, ni el secreto).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.attachments.storage import storage_from_settings
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo_s3 import ACCESO, SECRETO, settings_s3


def test_por_omision_el_almacen_es_local_bajo_uploads_dir_attachments(
    settings_prueba: Settings, tmp_path: Path
) -> None:
    ajustes = settings_prueba.model_copy(update={"UPLOADS_DIR": tmp_path / "uploads"})

    almacen = storage_from_settings(ajustes)

    assert isinstance(almacen, LocalDiskStorage)
    assert almacen.root == tmp_path / "uploads" / "attachments"


def test_s3_en_produccion_sin_s3_enable_production_falla_nombrando_la_variable(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
) -> None:
    ajustes = settings_s3(settings_prueba, ENV="production", S3_ENABLE_PRODUCTION=False)

    with pytest.raises(ValueError, match="S3_ENABLE_PRODUCTION") as error:
        storage_from_settings(ajustes)

    assert SECRETO not in str(error.value) and ACCESO not in str(error.value)
    assert cliente_s3_espiado["llamadas"] == []  # ni siquiera se intentó construir el cliente


def test_s3_en_produccion_con_la_bandera_y_https_se_construye(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
) -> None:
    ajustes = settings_s3(settings_prueba, ENV="production", S3_ENABLE_PRODUCTION=True)

    almacen = storage_from_settings(ajustes)

    assert type(almacen).__name__ == "S3CompatibleStorage"
    assert len(cliente_s3_espiado["llamadas"]) == 1


@pytest.mark.parametrize("env", ["production"])
def test_un_endpoint_http_fuera_de_dev_falla_nombrando_la_variable(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
    env: str,
) -> None:
    ajustes = settings_s3(
        settings_prueba,
        ENV=env,
        S3_ENABLE_PRODUCTION=True,
        S3_ENDPOINT_URL="http://s3.interno:9000",
    )

    with pytest.raises(ValueError, match="S3_ENDPOINT_URL"):
        storage_from_settings(ajustes)

    assert cliente_s3_espiado["llamadas"] == []


def test_un_endpoint_http_en_dev_se_acepta(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
) -> None:
    ajustes = settings_s3(settings_prueba, ENV="dev", S3_ENDPOINT_URL="http://localhost:9000")

    assert type(storage_from_settings(ajustes)).__name__ == "S3CompatibleStorage"


@pytest.mark.parametrize("endpoint", ["ftp://s3.prueba.example", "s3.prueba.example", "//x/y"])
def test_un_endpoint_sin_esquema_http_o_https_falla(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
    endpoint: str,
) -> None:
    with pytest.raises(ValueError, match="S3_ENDPOINT_URL"):
        storage_from_settings(settings_s3(settings_prueba, S3_ENDPOINT_URL=endpoint))


def test_un_endpoint_con_credenciales_dentro_de_la_url_falla_sin_repetirlas(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
) -> None:
    ajustes = settings_s3(
        settings_prueba, S3_ENDPOINT_URL="https://usuario:clave-url@s3.prueba.example"
    )

    with pytest.raises(ValueError, match="S3_ENDPOINT_URL") as error:
        storage_from_settings(ajustes)

    assert "clave-url" not in str(error.value)


@pytest.mark.parametrize(
    "faltante",
    ["S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"],
)
def test_con_s3_las_cinco_variables_son_todo_o_nada(
    settings_prueba: Settings,
    cliente_s3_espiado: dict[str, Any],
    faltante: str,
) -> None:
    ajustes = settings_s3(settings_prueba, **{faltante: None})

    with pytest.raises(ValueError, match=faltante):
        storage_from_settings(ajustes)

    assert cliente_s3_espiado["llamadas"] == []


def test_sin_boto3_el_mensaje_dice_instale_el_extra_s3(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)  # `import boto3` falla con ImportError
    monkeypatch.setitem(sys.modules, "botocore", None)

    with pytest.raises(ValueError, match="instale el extra s3"):
        storage_from_settings(settings_s3(settings_prueba))


def test_el_modulo_s3_se_importa_sin_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    """La importación es perezosa (S6-D21): con `boto3` ausente el módulo, y con él `service`,
    se importan igual; solo construir el almacén S3 falla."""
    import importlib

    monkeypatch.setitem(sys.modules, "boto3", None)
    monkeypatch.setitem(sys.modules, "botocore", None)
    sys.modules.pop("app.modules.attachments.storage.s3", None)
    try:
        modulo = importlib.import_module("app.modules.attachments.storage.s3")
        assert hasattr(modulo, "S3CompatibleStorage")
    finally:
        sys.modules.pop("app.modules.attachments.storage.s3", None)
