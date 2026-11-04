"""Rotación frente a otros procesos: candado por clase y escrituras en curso (S4B-B3b; D39, D40).

- Con el candado `pg_try_advisory_lock(hashtext('apex:rotate:member.document'))` tomado en otra
  conexión, `start_rotation` lanza `RotationInProgress` sin crear llave ni job.
- Una escritura con `FOR SHARE` sobre la llave activa (la del listener de `Encrypted`) hace
  esperar al `FOR UPDATE` de `start_rotation`; su fila termina con la llave nueva.
- Si el `FOR UPDATE` vence por `lock_timeout`, `start_rotation` lanza `DatabaseBusy` (el comando
  reintenta, ver `tests/cli/test_rotate_key_cli.py`).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select, text

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.models import CryptoJob
from app.core.crypto.secret import Secret
from app.core.crypto.service import RotationInProgress, start_rotation
from app.core.db import DatabaseBusy
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    Fabrica,
    blobs_de_rotacion,
    filas_rotacion,
    llaves_de,
)
from tests.crypto._rotacion_flujo import ACTOR, MOTIVO, cerrar, iniciar, leer, un_lote
from tests.crypto.models_fixture import CryptoTestPerson

pytestmark = pytest.mark.usefixtures("reloj")

FOR_SHARE = (
    "SELECT id FROM crypto.crypto_keys WHERE purpose = 'encrypt' "
    "AND data_class = 'member.document' AND state = 'active' FOR SHARE"
)


async def test_con_el_candado_tomado_la_segunda_falla_sin_crear_llave(
    rotacion_lista: Fabrica, candado_rotacion_tomado: None
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 10)

    with pytest.raises(RotationInProgress):
        async with rotacion_lista() as sesion, sesion.begin():
            await start_rotation(sesion, CLASE_ROTADA, MOTIVO, ACTOR)

    async with rotacion_lista() as sesion:
        assert [(k.version, k.state) for k in await llaves_de(sesion)] == [(1, "active")]
        assert await sesion.scalar(select(func.count()).select_from(CryptoJob)) == 0


async def test_un_job_running_sin_candado_se_reanuda(rotacion_lista: Fabrica) -> None:
    """Un proceso caído deja el job `running` y suelta el candado: el siguiente lo reanuda."""
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 60)
    primero = await iniciar(rotacion_lista)
    await un_lote(rotacion_lista, primero, 20)

    segundo = await iniciar(rotacion_lista)

    assert segundo == primero


async def test_una_escritura_con_for_share_hace_esperar_a_start_rotation(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 20)
    escritora = rotacion_lista()
    rotadora = rotacion_lista()
    try:
        # La escritura toma FOR SHARE (como el listener) y cifra con la llave vigente (v1).
        await escritora.begin()
        await escritora.execute(text(FOR_SHARE))
        with actor_scope(SYSTEM_USER_ID):
            nueva = CryptoTestPerson(name="tardía", document=Secret.from_plain("doc-tardio"))
            escritora.add(nueva)
            await escritora.flush()
        nueva_id = nueva.id

        async def rotar() -> None:
            with actor_scope(ACTOR):
                async with rotadora.begin():
                    await start_rotation(rotadora, CLASE_ROTADA, MOTIVO, ACTOR)

        tarea = asyncio.create_task(rotar())
        await asyncio.sleep(0.6)
        assert not tarea.done(), "start_rotation no debió pasar mientras hay un FOR SHARE vivo"

        with actor_scope(SYSTEM_USER_ID):
            await escritora.commit()
        await asyncio.wait_for(tarea, timeout=15)
    finally:
        await escritora.close()
        await rotadora.close()

    job_id = await iniciar(rotacion_lista)  # reanuda el job que abrió la tarea
    while await un_lote(rotacion_lista, job_id) == 500:
        pass
    assert await cerrar(rotacion_lista, job_id) is True
    async with rotacion_lista() as sesion:
        v1, v2 = await llaves_de(sesion)
        blobs = await blobs_de_rotacion(sesion)
        assert blobs[nueva_id].split(".")[1] == str(v2.id), "la fila tardía quedó con la vieja"
        assert leer(blobs[nueva_id], nueva_id) == "doc-tardio"
        assert len(ids) == 20
        assert all(b.split(".")[1] == str(v2.id) for b in blobs.values())
        assert v1.state == "decrypt_only"


async def test_lock_timeout_vencido_lanza_database_busy(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 5)
    escritora = rotacion_lista()
    rotadora = rotacion_lista()
    try:
        await escritora.begin()
        await escritora.execute(text(FOR_SHARE))

        with pytest.raises(DatabaseBusy):
            async with rotadora.begin():
                await rotadora.execute(text("SET LOCAL lock_timeout = '300ms'"))
                await start_rotation(rotadora, CLASE_ROTADA, MOTIVO, ACTOR)
    finally:
        await escritora.rollback()
        await escritora.close()
        await rotadora.close()

    async with rotacion_lista() as sesion:
        assert [(k.version, k.state) for k in await llaves_de(sesion)] == [(1, "active")]
        assert await sesion.scalar(select(func.count()).select_from(CryptoJob)) == 0


async def test_tras_un_database_busy_la_rotacion_se_puede_repetir(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 5)
    escritora = rotacion_lista()
    try:
        await escritora.begin()
        await escritora.execute(text(FOR_SHARE))
        rotadora = rotacion_lista()
        with pytest.raises(DatabaseBusy):
            async with rotadora.begin():
                await rotadora.execute(text("SET LOCAL lock_timeout = '200ms'"))
                await start_rotation(rotadora, CLASE_ROTADA, MOTIVO, ACTOR)
        await rotadora.close()
    finally:
        await escritora.rollback()
        await escritora.close()

    job_id = await iniciar(rotacion_lista)

    assert await un_lote(rotacion_lista, job_id) == 5
    assert await cerrar(rotacion_lista, job_id) is True


async def test_una_fila_bloqueada_no_detiene_el_lote_y_se_migra_en_la_pasada_siguiente(
    rotacion_lista: Fabrica,
) -> None:
    """S4B-D150 (M2): `skip_locked` en el lote; lo saltado lo recoge la pasada siguiente."""
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 30)
    job_id = await iniciar(rotacion_lista)
    bloqueadora = rotacion_lista()
    try:
        await bloqueadora.begin()
        await bloqueadora.execute(
            text("SELECT id FROM test_crypto.crypto_test_person WHERE id = :i FOR SHARE"),
            {"i": ids[0]},
        )
        assert await un_lote(rotacion_lista, job_id) == 29, "la fila bloqueada no debe frenar"
        assert await cerrar(rotacion_lista, job_id) is False, "queda una fila con la llave vieja"
    finally:
        await bloqueadora.rollback()
        await bloqueadora.close()

    assert await un_lote(rotacion_lista, job_id) == 1
    assert await cerrar(rotacion_lista, job_id) is True
    async with rotacion_lista() as sesion:
        _, v2 = await llaves_de(sesion)
        blobs = await blobs_de_rotacion(sesion)
    assert all(b.split(".")[1] == str(v2.id) for b in blobs.values())
    assert leer(blobs[ids[0]], ids[0]) == "doc-00000"
