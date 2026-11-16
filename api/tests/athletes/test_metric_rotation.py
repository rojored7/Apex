"""Rotación de la llave `athlete.metric` (S9-A1, US-178; S9-D5 (6), S9-D31, E3). Rojo A1.

La clase se rota por las columnas del registro (sin puerto `Reencryptor`): el flujo de
`rotate-key` (`start_rotation`, `reencrypt_batch`, `finish_rotation`) recifra las CUATRO columnas de
cada medición, también la anulada (si no, `retire-key` quedaría bloqueado, S9-D31 (5)); el valor se
conserva, la llave anterior queda `decrypt_only` y `count_rows_by_key` cuenta por columna. El
recifrado pasa por las guardas de la base: llave activa y distinta, mismo ancho, sin anular.
Con commit real: cada paso en su propia sesión, como el comando.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core import db
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus, oplog
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.service import count_rows_by_key
from app.core.crypto.types import install_crypto_type_listeners
from tests.athletes._apoyo import CLASE, ENCRIPTADAS, fila_cruda
from tests.conftest import LIMPIAR_ATHLETES, LIMPIAR_LLAVES, LIMPIAR_MEMBERS
from tests.crypto._rotacion import (
    BORRADOS,
    Fabrica,
    _limpiar_auditoria_desde,
    _ultima_seq,
    llave_activa,
    llaves_de,
)
from tests.crypto._rotacion_flujo import cerrar, iniciar, un_lote
from tests.factories.athletes import make_metric
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj")

PESO_VIVA = 62_500
PESO_ANULADA = 80_000
CLAROS = {
    "weight_g": "w062500",
    "height_cm": "h165",
    "body_fat_pct": "f22",
}


@pytest.fixture
async def medidas_listas(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Fabrica]:
    """Bus con commit real (todas las clases del registro, incluida `athlete.metric`)."""
    install_crypto_type_listeners()
    oplog.install_oplog_listeners()
    configure_keyring(None)
    ultima_seq = await _ultima_seq(engine)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for sql in (LIMPIAR_ATHLETES, LIMPIAR_MEMBERS, *LIMPIAR_LLAVES):
            await conn.execute(text(sql))
    oplog.reset_buffer()
    db.configure_engine(engine)
    try:
        async with fabrica() as sesion, sesion.begin():
            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)
        yield fabrica
    finally:
        db.configure_engine(None)
        oplog.reset_buffer()
        configure_keyring(None)
        async with engine.begin() as conn:
            await conn.execute(text(LIMPIAR_ATHLETES))
            await conn.execute(text(LIMPIAR_MEMBERS))
            for tabla, borrar in BORRADOS:
                await conn.execute(text(disable_user_sql(tabla)))
                await conn.execute(text(borrar))
                await conn.execute(text(rearm_always_sql(tabla)))
            for sql in LIMPIAR_LLAVES:
                await conn.execute(text(sql))
        await _limpiar_auditoria_desde(engine, ultima_seq)


async def _sembrar(fabrica: Fabrica) -> tuple[UUID, UUID]:
    """Una medición viva y una anulada del mismo socio, confirmadas."""
    async with fabrica() as sesion:
        miembro = await socio(sesion, consentido=True)
        viva = await make_metric(sesion, miembro.id, weight_g=PESO_VIVA)
        anulada = await make_metric(sesion, miembro.id, weight_g=PESO_ANULADA, voided=True)
        return viva.id, anulada.id


async def _filas(fabrica: Fabrica, ids: tuple[UUID, ...]) -> dict[UUID, dict[str, object]]:
    async with fabrica() as sesion:
        return {i: await fila_cruda(sesion, i) for i in ids}


async def _vacias_y_llenas(fabrica: Fabrica, i: UUID) -> list[str]:
    async with fabrica() as sesion:
        fila = await fila_cruda(sesion, i)
    return [c for c in ENCRIPTADAS if fila[c] is not None]


async def test_la_rotacion_recifra_las_cuatro_columnas_de_la_viva_y_de_la_anulada(
    medidas_listas: Fabrica,
) -> None:
    viva, anulada = await _sembrar(medidas_listas)
    async with medidas_listas() as sesion:
        vieja = (await llave_activa(sesion, CLASE)).id
    antes = await _filas(medidas_listas, (viva, anulada))
    assert {fila[c].split(".")[1] for fila in antes.values() for c in ENCRIPTADAS} == {str(vieja)}

    job_id = await iniciar(medidas_listas, CLASE)
    migradas = await un_lote(medidas_listas, job_id)
    # `reencrypt_batch` cuenta blobs (columna por fila): 2 filas (viva y anulada) x 4 columnas.
    assert migradas == 8
    assert await un_lote(medidas_listas, job_id) == 0
    assert await cerrar(medidas_listas, job_id) is True

    async with medidas_listas() as sesion:
        v1, v2 = await llaves_de(sesion, "encrypt", CLASE)
        assert (v1.id, v1.state, v2.state) == (vieja, "decrypt_only", "active")
    despues = await _filas(medidas_listas, (viva, anulada))
    for i, fila in despues.items():
        for campo in ENCRIPTADAS:
            assert fila[campo].split(".")[1] == str(v2.id), (i, campo)
            assert fila[campo] != antes[i][campo]
            assert len(fila[campo]) == len(antes[i][campo]), (i, campo)  # el ancho se conserva
        assert (fila["voided_at"] is None) == (i == viva)  # la anulación no se toca
        assert fila["updated_at"] == antes[i]["updated_at"]


async def test_el_valor_se_conserva_tras_rotar(medidas_listas: Fabrica) -> None:
    viva, anulada = await _sembrar(medidas_listas)
    job_id = await iniciar(medidas_listas, CLASE)
    while await un_lote(medidas_listas, job_id):
        pass
    await cerrar(medidas_listas, job_id)

    filas = await _filas(medidas_listas, (viva, anulada))
    for i, peso in ((viva, "w062500"), (anulada, "w080000")):
        aad = bus.aad_for(i)
        assert bus.decrypt(filas[i]["weight_g"], aad).decode("utf-8") == peso
        assert bus.decrypt(filas[i]["height_cm"], aad).decode("utf-8") == CLAROS["height_cm"]
        assert bus.decrypt(filas[i]["body_fat_pct"], aad).decode("utf-8") == CLAROS["body_fat_pct"]
        notas = bus.decrypt(filas[i]["notes"], aad).decode("utf-8")
        # "Medición de prueba": 19 bytes UTF-8 ("ó" ocupa 2) en la cabecera `n0019`.
        assert notas.startswith("n0019Medición de prueba") and len(notas.encode()) % 128 == 0


async def test_count_rows_by_key_cuenta_por_columna_antes_y_despues(
    medidas_listas: Fabrica,
) -> None:
    """`retire-key` cuenta bien: 2 filas (viva y anulada) en cada una de las cuatro columnas."""
    await _sembrar(medidas_listas)
    async with medidas_listas() as sesion:
        vieja = (await llave_activa(sesion, CLASE)).id
        antes = await count_rows_by_key(sesion, vieja)
    assert antes == {f"athletes.body_metrics.{c}": 2 for c in ENCRIPTADAS}

    job_id = await iniciar(medidas_listas, CLASE)
    while await un_lote(medidas_listas, job_id):
        pass
    await cerrar(medidas_listas, job_id)

    async with medidas_listas() as sesion:
        despues = await count_rows_by_key(sesion, vieja)
        assert despues == {f"athletes.body_metrics.{c}": 0 for c in ENCRIPTADAS}
        (nueva,) = [k for k in await llaves_de(sesion, "encrypt", CLASE) if k.state == "active"]
        assert await count_rows_by_key(sesion, nueva.id) == {
            f"athletes.body_metrics.{c}": 2 for c in ENCRIPTADAS
        }


async def test_una_medicion_con_columnas_vacias_conserva_la_nulidad_al_rotar(
    medidas_listas: Fabrica,
) -> None:
    async with medidas_listas() as sesion:
        miembro = await socio(sesion, consentido=True)
        parcial = await make_metric(
            sesion, miembro.id, height_cm=170, weight_g=None, body_fat_pct=None, notes=None
        )
    job_id = await iniciar(medidas_listas, CLASE)
    while await un_lote(medidas_listas, job_id):
        pass
    await cerrar(medidas_listas, job_id)

    assert await _vacias_y_llenas(medidas_listas, parcial.id) == ["height_cm"]


async def test_la_rotacion_no_deja_filas_de_auditoria_por_las_mediciones(
    medidas_listas: Fabrica,
) -> None:
    """E3: `reencrypt_batch` escribe con Core: sin fila `update` en `audit_log`."""
    await _sembrar(medidas_listas)
    async with medidas_listas() as sesion:
        antes = await sesion.scalar(
            text("SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.body_metrics'")
        )
    job_id = await iniciar(medidas_listas, CLASE)
    while await un_lote(medidas_listas, job_id):
        pass
    await cerrar(medidas_listas, job_id)

    async with medidas_listas() as sesion:
        despues = await sesion.scalar(
            text("SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.body_metrics'")
        )
    assert despues == antes
