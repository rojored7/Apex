"""Kit de las pruebas de `attachments` (S6-C1).

- `almacen`: `LocalDiskStorage` sobre `tmp_path/attachments` ya configurado en el service
  (`configure_storage`); al salir lo vuelve a `None`.
- `por`: el UUID del usuario que sube; `con_actor` lo fija como actor del flush (`created_by`).
- `listo`: sesión con savepoint (`session`) y el bus cargado con las DEK (`bus_listo`): incluye la
  de `attachment.sensitive` (registro de C1).
- `real`: commit real para las pruebas que observan dos sesiones: DEK confirmadas, keyring
  cargado, y al salir borra los adjuntos (`LIMPIAR_ATTACHMENTS`), las llaves, `crypto_ops` y la
  cola de la cadena de auditoría.
- `sin_tempfile`: `tempfile` falla si alguien lo llama (nada de spool ni de `/tmp`, E1).
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit import AuditEntry
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.modules.attachments import service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo_s3 import ENDPOINT
from tests.conftest import LIMPIAR_ATTACHMENTS, limpiar_tras_dos_sesiones
from tests.factories.firma_real import llaves_de_firma
from tests.factories.triggers import disable_user_sql, rearm_always_sql

Fabrica = async_sessionmaker[AsyncSession]


@pytest.fixture
def almacen(tmp_path: Path) -> Iterator[LocalDiskStorage]:
    raiz = tmp_path / "attachments"
    raiz.mkdir()
    almacen = LocalDiskStorage(raiz)
    service.configure_storage(almacen)
    try:
        yield almacen
    finally:
        service.configure_storage(None)


@pytest.fixture
def por() -> UUID:
    return uuid4()


@pytest.fixture
def listo(session: AsyncSession, bus_listo: Keyring) -> AsyncSession:
    """Sesión con savepoint y el bus listo (DEK de todas las clases, la de adjuntos incluida)."""
    return session


@pytest.fixture
async def real(engine: AsyncEngine, proveedor_local: LocalFileProvider) -> AsyncIterator[Fabrica]:
    async with engine.connect() as conexion:
        ultima = int(await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0))) or 0)
    async with llaves_de_firma(engine, proveedor_local, con_fila_sign=False) as fabrica:
        async with fabrica() as sesion:
            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)
            await sesion.commit()
        try:
            yield fabrica
        finally:
            async with engine.begin() as conexion:
                await conexion.execute(text(LIMPIAR_ATTACHMENTS))
                # Un trabajo de rotación abierto por una prueba haría que la siguiente lo retome.
                await conexion.execute(text(disable_user_sql("crypto.crypto_jobs")))
                await conexion.execute(text("DELETE FROM crypto.crypto_jobs"))
                await conexion.execute(text(rearm_always_sql("crypto.crypto_jobs")))
            await limpiar_tras_dos_sesiones(engine, ultima)


@pytest.fixture
def sin_tempfile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier uso de `tempfile` (mkstemp, NamedTemporaryFile, Spooled...) falla la prueba."""

    def prohibido(*_a: object, **_k: object) -> None:
        raise AssertionError("tempfile no se usa en la subida de adjuntos (E1, S6-D59)")

    for nombre in (
        "SpooledTemporaryFile",
        "NamedTemporaryFile",
        "TemporaryFile",
        "mkstemp",
        "mkdtemp",
        "TemporaryDirectory",
    ):
        monkeypatch.setattr(tempfile, nombre, prohibido)


@pytest.fixture
def cliente_s3_espiado(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reemplaza `boto3.client`: anota los argumentos y entrega un cliente real con Stubber."""
    pytest.importorskip("botocore.stub", reason="falta el extra s3 (boto3/botocore)")
    import boto3
    from botocore.stub import Stubber

    original = boto3.client
    anotado: dict[str, Any] = {"llamadas": []}

    def falso(servicio: str, *args: Any, **kwargs: Any) -> Any:
        anotado["llamadas"].append((servicio, args, dict(kwargs)))
        with monkeypatch.context() as aislado:
            # El cliente de prueba no debe depender del perfil `AWS_PROFILE` que fija la prueba.
            aislado.delenv("AWS_PROFILE", raising=False)
            cliente = original(
                "s3",
                region_name="us-east-1",
                endpoint_url=ENDPOINT,
                aws_access_key_id=kwargs.get("aws_access_key_id", "x"),
                aws_secret_access_key=kwargs.get("aws_secret_access_key", "x"),
            )
        stubber = Stubber(cliente)
        stubber.activate()
        anotado["cliente"], anotado["stubber"] = cliente, stubber
        return cliente

    monkeypatch.setattr(boto3, "client", falso)
    return anotado
