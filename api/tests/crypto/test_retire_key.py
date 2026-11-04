"""`retire_key` y sus conteos (S4B-B3b, US-030; S4B-D38, D63, D86).

`retired` es una bandera irreversible: solo se llega desde `decrypt_only`, con cero filas de
negocio con ese `key_id` (conteo bajo `FOR UPDATE` de la llave) y con el conteo de blobs de
`audit.audit_log` que el operador confirmó. La auditoría `audit.record(... "retire" ...)` la
escribe el CLI (`tests/cli/test_retire_key_cli.py`); aquí se prueba el servicio.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.audit import AuditEntry
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.service import (
    InvalidTransition,
    count_audit_blobs,
    count_rows_by_key,
    recent_kek_verify,
    retire_key,
)
from app.core.db import DatabaseBusy
from tests.conftest import limpiar_tras_dos_sesiones
from tests.crypto._rotacion import (
    COLUMNA_ROTADA,
    Fabrica,
    blobs_de_rotacion,
    cuenta_de_ops,
    filas_rotacion,
    llaves_de,
    verify_reciente,
)
from tests.crypto._rotacion_flujo import (
    ACTOR,
    cerrar,
    iniciar,
    leer,
    recargar,
    registrar_blob,
    rotar,
    todo_se_lee,
    un_lote,
)

pytestmark = pytest.mark.usefixtures("reloj")

PERSONA = UUID(int=99)


@pytest.fixture
async def auditoria_limpia(engine: AsyncEngine) -> AsyncIterator[None]:
    """Las entradas de `audit_log` que agregue la prueba se borran al salir."""
    async with engine.connect() as conexion:
        ultima = int(await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0))) or 0)
    try:
        yield
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima)


async def _contar_filas(fabrica: Fabrica, key_id: UUID) -> dict[str, int]:
    async with fabrica() as sesion, sesion.begin():
        return await count_rows_by_key(sesion, key_id)


async def _contar_blobs(fabrica: Fabrica, key_id: UUID) -> int:
    async with fabrica() as sesion, sesion.begin():
        return await count_audit_blobs(sesion, key_id)


async def _retirar(fabrica: Fabrica, key_id: UUID, confirmados: int) -> int:
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            return await retire_key(sesion, key_id, confirmed_audit_blobs=confirmados, actor=ACTOR)


async def _estado(fabrica: Fabrica) -> list[tuple[int, str]]:
    async with fabrica() as sesion:
        return [(k.version, k.state) for k in await llaves_de(sesion)]


# Conteos -------------------------------------------------------------------------------------


async def test_count_rows_by_key_cuenta_por_columna_durante_y_despues_de_la_rotacion(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 600)
        v1 = (await llaves_de(sesion))[0]
    assert await _contar_filas(rotacion_lista, v1.id) == {COLUMNA_ROTADA: 600}
    job_id = await iniciar(rotacion_lista)
    await un_lote(rotacion_lista, job_id)

    async with rotacion_lista() as sesion:
        v1, v2 = await llaves_de(sesion)
    assert await _contar_filas(rotacion_lista, v1.id) == {COLUMNA_ROTADA: 100}
    assert await _contar_filas(rotacion_lista, v2.id) == {COLUMNA_ROTADA: 500}

    await un_lote(rotacion_lista, job_id)
    assert await cerrar(rotacion_lista, job_id) is True
    assert await _contar_filas(rotacion_lista, v1.id) == {COLUMNA_ROTADA: 0}
    assert await _contar_filas(rotacion_lista, v2.id) == {COLUMNA_ROTADA: 600}


async def test_count_rows_by_key_toma_for_update_de_la_llave(rotacion_lista: Fabrica) -> None:
    """Con la fila de la llave tomada por otra transacción, el conteo espera y vence por
    `lock_timeout` (`DatabaseBusy`): el recuento a cero corre bajo `FOR UPDATE`."""
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
    bloqueadora = rotacion_lista()
    contadora = rotacion_lista()
    try:
        await bloqueadora.begin()
        await bloqueadora.execute(
            text("SELECT id FROM crypto.crypto_keys WHERE id = :i FOR UPDATE"), {"i": v1.id}
        )
        with pytest.raises(DatabaseBusy):
            async with contadora.begin():
                await contadora.execute(text("SET LOCAL lock_timeout = '300ms'"))
                await count_rows_by_key(contadora, v1.id)
    finally:
        await bloqueadora.rollback()
        await bloqueadora.close()
        await contadora.close()


async def test_count_audit_blobs_cuenta_los_de_esa_llave_en_before_y_after(
    rotacion_lista: Fabrica, auditoria_limpia: None
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 3)
        v1 = (await llaves_de(sesion))[0]
        blobs = await blobs_de_rotacion(sesion)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v2 = (await llaves_de(sesion))[1]
        nuevos = await blobs_de_rotacion(sesion)
    assert await _contar_blobs(rotacion_lista, v1.id) == 0

    viejo = next(iter(blobs.values()))
    await registrar_blob(rotacion_lista, viejo, en="after")

    assert await _contar_blobs(rotacion_lista, v1.id) == 1
    await registrar_blob(rotacion_lista, viejo, en="before")
    assert await _contar_blobs(rotacion_lista, v1.id) == 2
    await registrar_blob(rotacion_lista, next(iter(nuevos.values())), en="after")
    assert await _contar_blobs(rotacion_lista, v1.id) == 2, "un blob de otra llave no cuenta"
    assert await _contar_blobs(rotacion_lista, v2.id) == 1


async def test_count_audit_blobs_no_confunde_un_texto_parecido(
    rotacion_lista: Fabrica, auditoria_limpia: None
) -> None:
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
    await registrar_blob(rotacion_lista, f"apx1-{v1.id}-A256GCM")
    await registrar_blob(rotacion_lista, f"nota sobre {v1.id} sin prefijo")

    assert await _contar_blobs(rotacion_lista, v1.id) == 0


# retire_key ----------------------------------------------------------------------------------


async def test_retire_key_con_cero_filas_y_el_conteo_correcto_deja_retired(
    rotacion_lista: Fabrica, auditoria_limpia: None
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 40)
        viejos = await blobs_de_rotacion(sesion)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
        antes = await cuenta_de_ops(sesion, "rotate")
    await registrar_blob(rotacion_lista, viejos[ids[0]])

    confirmados = await _retirar(rotacion_lista, v1.id, 1)

    assert confirmados == 1
    assert await _estado(rotacion_lista) == [(1, "retired"), (2, "active")]
    async with rotacion_lista() as sesion:
        total = await sesion.scalar(
            text("SELECT count(*) FROM crypto.crypto_ops WHERE verb = 'rotate' AND key_id = :k"),
            {"k": v1.id},
        )
        assert total is not None and total >= 1
        assert await cuenta_de_ops(sesion, "rotate") == antes + 1


async def test_tras_retired_el_blob_viejo_lanza_key_retired_y_los_de_negocio_se_leen(
    rotacion_lista: Fabrica, auditoria_limpia: None
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 30)
        viejos = await blobs_de_rotacion(sesion)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
    blob_viejo = viejos[ids[0]]
    assert leer(blob_viejo, ids[0]) == "doc-00000", "antes del retiro la vieja aún descifra"

    await _retirar(rotacion_lista, v1.id, 0)

    async with rotacion_lista() as sesion:
        await recargar(sesion)
        with pytest.raises(CryptoError) as error:
            bus.decrypt(blob_viejo, bus.aad_for(ids[0]))
        assert error.value.code == "key_retired"
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))


async def test_retire_key_con_un_conteo_distinto_lanza_value_error_sin_cambiar_nada(
    rotacion_lista: Fabrica, auditoria_limpia: None
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 10)
        viejos = await blobs_de_rotacion(sesion)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
        ops_antes = await cuenta_de_ops(sesion, "rotate")
    await registrar_blob(rotacion_lista, viejos[ids[0]])

    for equivocado in (0, 2, 99):
        with pytest.raises(ValueError) as error:
            await _retirar(rotacion_lista, v1.id, equivocado)
        assert "apx1." not in str(error.value)

    assert await _estado(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
    async with rotacion_lista() as sesion:
        assert await cuenta_de_ops(sesion, "rotate") == ops_antes


async def test_retire_key_con_filas_de_negocio_pendientes_falla_aunque_el_conteo_sea_correcto(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 600)
    job_id = await iniciar(rotacion_lista)
    await un_lote(rotacion_lista, job_id)  # quedan 100 con la llave vieja
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]

    with pytest.raises(ValueError):
        await _retirar(rotacion_lista, v1.id, 0)

    assert await _estado(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]


async def test_retire_key_sobre_la_llave_active_lanza_invalid_transition(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]

    with pytest.raises(InvalidTransition):
        await _retirar(rotacion_lista, v1.id, 0)

    assert await _estado(rotacion_lista) == [(1, "active")]


async def test_retire_key_sobre_una_llave_ya_retired_lanza_invalid_transition(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 5)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
    await _retirar(rotacion_lista, v1.id, 0)

    with pytest.raises(InvalidTransition):
        await _retirar(rotacion_lista, v1.id, 0)

    assert await _estado(rotacion_lista) == [(1, "retired"), (2, "active")]


async def test_retire_key_con_un_id_inexistente_lanza_value_error(rotacion_lista: Fabrica) -> None:
    with pytest.raises(ValueError):
        await _retirar(rotacion_lista, UUID(int=12345), 0)


async def test_una_llave_retired_no_vuelve_a_otro_estado(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 5)
    await rotar(rotacion_lista)
    async with rotacion_lista() as sesion:
        v1 = (await llaves_de(sesion))[0]
    await _retirar(rotacion_lista, v1.id, 0)

    with pytest.raises(Exception, match="transición de estado no permitida"):
        async with rotacion_lista() as sesion, sesion.begin():
            await sesion.execute(
                text("UPDATE crypto.crypto_keys SET state = 'decrypt_only' WHERE id = :i"),
                {"i": v1.id},
            )


# recent_kek_verify ---------------------------------------------------------------------------

VENTANA = timedelta(hours=24)


async def test_recent_kek_verify_sin_filas_es_falso(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        assert await recent_kek_verify(sesion, within=VENTANA) is False


async def test_recent_kek_verify_verdadero_con_un_verify_ok_de_una_persona_reciente(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await verify_reciente(sesion, PERSONA)
        assert await recent_kek_verify(sesion, within=VENTANA) is True


CASOS_FALSOS = {
    "de hace 25 horas": {"edad": timedelta(hours=25)},
    "del usuario técnico": {"actor": SYSTEM_USER_ID},
    "con resultado error": {"resultado": "error"},
    "de otro verbo": {"verbo": "export"},
    "de otra clase": {"data_class": "member.document"},
}


@pytest.mark.parametrize("caso", list(CASOS_FALSOS.values()), ids=list(CASOS_FALSOS))
async def test_recent_kek_verify_es_falso_si_la_fila_no_cumple(
    rotacion_lista: Fabrica, caso: dict[str, object]
) -> None:
    actor = caso.pop("actor", PERSONA)
    async with rotacion_lista() as sesion:
        await verify_reciente(sesion, actor, **caso)  # type: ignore[arg-type]
        assert await recent_kek_verify(sesion, within=VENTANA) is False


async def test_recent_kek_verify_respeta_la_ventana_pedida(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await verify_reciente(sesion, PERSONA, edad=timedelta(hours=3))
        assert await recent_kek_verify(sesion, within=timedelta(hours=4)) is True
        assert await recent_kek_verify(sesion, within=timedelta(hours=2)) is False


async def test_recent_kek_verify_acepta_la_fila_buena_entre_filas_malas(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await verify_reciente(sesion, SYSTEM_USER_ID)
        await verify_reciente(sesion, PERSONA, resultado="error")
        await verify_reciente(sesion, PERSONA, edad=timedelta(hours=30))
        assert await recent_kek_verify(sesion, within=VENTANA) is False
        await verify_reciente(sesion, PERSONA, edad=timedelta(minutes=5))
        assert await recent_kek_verify(sesion, within=VENTANA) is True
