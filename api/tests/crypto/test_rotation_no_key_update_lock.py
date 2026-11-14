"""M-6 (S7-D3, `0025`): con la FK `fk_attachments_key_id`, cada `INSERT` de adjunto toma
`FOR KEY SHARE` sobre su llave. Los candados de fila de la rotación que solo cambian `state` o
`rotated_*` deben ser `FOR NO KEY UPDATE`, que no choca con ese candado; un `FOR UPDATE` haría
esperar la subida (503) mientras rota `attachment.sensitive`."""

# ruff: noqa: F811
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import service
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    Fabrica,
    llave_activa,
    rotacion_lista,  # noqa: F401
)
from tests.crypto._rotacion_flujo import ACTOR, MOTIVO, iniciar

pytestmark = pytest.mark.usefixtures("reloj")

FK_EXISTE = "SELECT count(*) FROM pg_constraint WHERE conname = 'fk_attachments_key_id'"
INSERTAR = text(
    "INSERT INTO attachments.attachments (id, owner_table, owner_id, kind, filename_random, mime, "
    "size_bytes, sensitive, key_id, storage_provider, uploaded_by, created_by) VALUES "
    "(:id, 'members', gen_random_uuid(), 'consent', :nombre, 'application/pdf', 10, true, :k, "
    "'local', :u, :u)"
)


async def _subida_no_espera(fabrica: Fabrica, key_id: UUID) -> None:
    """Otra conexión inserta un adjunto con esa llave (queda sin confirmar) con tope de 1,5 s."""
    async with fabrica() as sesion:
        assert await sesion.scalar(text(FK_EXISTE)) == 1, "falta la FK de 0025"
        await sesion.execute(text("SET LOCAL lock_timeout = '1500ms'"))
        try:
            await sesion.execute(
                INSERTAR,
                {"id": uuid4(), "nombre": uuid4().hex, "k": key_id, "u": SYSTEM_USER_ID},
            )
        except DBAPIError as error:  # lock_not_available
            pytest.fail(f"la subida esperó el candado de la llave: {type(error.orig).__name__}")
        finally:
            await sesion.rollback()


async def test_subida_de_adjunto_durante_rotacion_no_espera(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        vieja = (await llave_activa(sesion)).id
    with actor_scope(ACTOR):
        async with rotacion_lista() as rotando, rotando.begin():
            await service.start_rotation(rotando, CLASE_ROTADA, MOTIVO, ACTOR)
            await _subida_no_espera(rotacion_lista, vieja)  # transacción abierta de la rotación


async def test_cierre_de_rotacion_no_bloquea_la_subida(rotacion_lista: Fabrica) -> None:
    await iniciar(rotacion_lista)
    with actor_scope(ACTOR):
        async with rotacion_lista() as sesion:
            activa = (await llave_activa(sesion)).id
        async with rotacion_lista() as cerrando, cerrando.begin():
            job = await service_job(cerrando)
            await service.finish_rotation(cerrando, job)
            await _subida_no_espera(rotacion_lista, activa)


async def service_job(sesion):  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.core.crypto.models import CryptoJob

    return (await sesion.scalars(select(CryptoJob).order_by(CryptoJob.created_at.desc()))).first()


async def test_candado_de_retiro_no_bloquea_la_subida(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        activa = (await llave_activa(sesion)).id
    with actor_scope(ACTOR):
        async with rotacion_lista() as reteniendo, reteniendo.begin():
            await service._lock_key(reteniendo, activa)
            await _subida_no_espera(rotacion_lista, activa)
