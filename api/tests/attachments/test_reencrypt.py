"""Recifrado de `attachment.sensitive` por el puerto `Reencryptor` (S6-C1, US-147; S6-D26, S6-D107,
G-09, L-3).

El puerto cuenta por la columna `key_id` (sin leer archivos) y `reencrypt_batch` toma las filas
sensibles con otra llave, con `FOR UPDATE SKIP LOCKED`, descifra con la llave `decrypt_only`, cifra
con la activa, REEMPLAZA el objeto de forma atómica (misma clave) y después actualiza `key_id`. Un
corte entre el objeto y el `UPDATE` es inocuo: el siguiente lote lo recifra otra vez.

Contratos que el Rojo asume (el Verde puede discutirlos):
- `count_total` = filas sensibles; `count_pending(activa)` = sensibles con `key_id` distinto de la
  activa; `count_by_key(k)` = filas con `key_id = k`; la foto (sin llave) no cuenta en ninguno;
- `reencrypt_batch` procesa como máximo `reencrypt.BATCH_SIZE` (10, S6-D111) aunque se pida más
  (cada elemento ocupa memoria: 5 MiB + el blob, y sostiene su candado de fila durante la E/S);
- las operaciones `decrypt`/`encrypt` del lote salen con el MISMO `batch_id` (una fila agregada
  por verbo, `count` = filas migradas).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from app.core.context import actor_scope
from app.core.crypto import bus, reencryptor
from app.core.crypto import service as core_service
from app.core.crypto.blob import parse_blob
from app.core.crypto.reencryptor import Reencryptor, get_reencryptor
from app.modules.attachments import reencrypt, service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, subir_real
from tests.attachments.conftest import Fabrica
from tests.crypto._rotacion import llave_activa, llaves_de
from tests.crypto._rotacion_flujo import ACTOR, cerrar, iniciar, job_de, un_lote
from tests.factories import files

CLASE = "attachment.sensitive"
PDF = files.pdf(3000)


@pytest.fixture
def puerto() -> Iterator[Reencryptor]:
    """El puerto REAL del módulo, registrado como lo hacen `create_app` y `cli_runtime`."""
    reencryptor._reset_for_tests()
    service.register_reencryptor()
    registrado = get_reencryptor(CLASE)
    assert registrado is not None, "service.register_reencryptor() no registró el puerto"
    try:
        yield registrado
    finally:
        reencryptor._reset_for_tests()


class CorteTrasPut(LocalDiskStorage):
    """Escribe el objeto y luego falla (el UPDATE de `key_id` no llega a ocurrir)."""

    def __init__(self, raiz: Path) -> None:
        super().__init__(raiz)
        self.cortar = False

    async def put(self, key: str, data: bytes) -> None:
        await super().put(key, data)
        if self.cortar:
            raise RuntimeError("corte entre el objeto y el UPDATE")


async def _sembrar(real: Fabrica, por: UUID, n: int, kind: str = "consent") -> list[UUID]:
    cuerpo = files.jpeg(3000) if kind == "photo" else PDF  # la foto solo admite imagen
    return [(await subir_real(real, por, kind, cuerpo)).id for _ in range(n)]


async def _activa(real: Fabrica) -> UUID:
    async with real() as sesion:
        return (await llave_activa(sesion, CLASE)).id


async def _contar(real: Fabrica, puerto: Reencryptor, activa: UUID) -> tuple[int, int, int]:
    async with real() as sesion:
        return (
            await puerto.count_total(sesion),
            await puerto.count_pending(sesion, activa),
            await puerto.count_by_key(sesion, activa),
        )


def _leer_blob(almacen: LocalDiskStorage, row: dict[str, Any]) -> str:
    return (almacen.root / row["filename_random"]).read_bytes().decode("ascii")


# Conteos por key_id ------------------------------------------------------------------------------


async def test_los_conteos_salen_de_key_id_y_la_foto_no_cuenta(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 3)
    await _sembrar(real, por, 2, kind="photo")
    activa = await _activa(real)

    total, pendientes, de_la_activa = await _contar(real, puerto, activa)

    assert (total, pendientes, de_la_activa) == (3, 0, 3)
    async with real() as sesion:
        assert await puerto.count_by_key(sesion, UUID(int=1234)) == 0


async def test_tras_rotar_la_llave_todo_queda_pendiente_y_by_key_separa_vieja_y_nueva(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 3)
    vieja = await _activa(real)

    await iniciar(real, CLASE)

    nueva = await _activa(real)
    assert nueva != vieja
    assert await _contar(real, puerto, nueva) == (3, 3, 0)
    async with real() as sesion:
        assert await puerto.count_by_key(sesion, vieja) == 3
        estados = [(k.version, k.state) for k in await llaves_de(sesion, "encrypt", CLASE)]
    assert estados == [(1, "decrypt_only"), (2, "active")]


async def test_la_rotacion_ya_no_responde_rotation_not_supported(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 1)
    job_id = await iniciar(real, CLASE)  # antes: CryptoError("rotation_not_supported")
    job = await job_de(real, job_id)
    assert (job.status, job.data_class, job.total) == ("running", CLASE, 1)


# Lote --------------------------------------------------------------------------------------------


async def test_un_lote_recifra_con_la_activa_reemplaza_el_objeto_y_actualiza_key_id(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    ids = await _sembrar(real, por, 3)
    async with real() as sesion:
        antes = {i: await fila(sesion, i) for i in ids}
    job_id = await iniciar(real, CLASE)
    nueva = await _activa(real)
    nombres = {i: antes[i]["filename_random"] for i in ids}

    migradas = await un_lote(real, job_id)

    assert migradas == 3
    async with real() as sesion:
        for i in ids:
            despues = await fila(sesion, i)
            assert despues["key_id"] == nueva != antes[i]["key_id"]
            assert despues["filename_random"] == nombres[i]  # misma clave de objeto
            blob = _leer_blob(almacen, despues)
            assert parse_blob(blob).key_id == nueva
            assert bus.decrypt(blob, bus.aad_for(i)) == PDF  # el AAD sigue siendo el id
            assert despues["updated_at"] >= antes[i]["updated_at"]
    assert sorted(p.name for p in almacen.root.iterdir()) == sorted(nombres.values())  # sin sobras


async def test_cero_pendientes_al_terminar_y_la_llave_vieja_se_puede_retirar_solo_entonces(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 2)
    vieja = await _activa(real)
    job_id = await iniciar(real, CLASE)
    nueva = await _activa(real)

    # S6-D107: mientras queden objetos con la llave vieja, `retire_key` se niega.
    async with real() as sesion:
        blobs = await core_service.count_audit_blobs(sesion, vieja)
        with pytest.raises(ValueError, match="quedan 2"):
            await core_service.retire_key(sesion, vieja, confirmed_audit_blobs=blobs, actor=ACTOR)
        await sesion.rollback()

    assert await un_lote(real, job_id) == 2
    assert await un_lote(real, job_id) == 0
    assert await cerrar(real, job_id) is True
    assert await _contar(real, puerto, nueva) == (2, 0, 2)
    async with real() as sesion:
        assert await puerto.count_by_key(sesion, vieja) == 0
        blobs = await core_service.count_audit_blobs(sesion, vieja)
        with actor_scope(ACTOR):  # `retire_key` anota `crypto_ops`: el commit exige actor
            await core_service.retire_key(sesion, vieja, confirmed_audit_blobs=blobs, actor=ACTOR)
            await sesion.commit()
    job = await job_de(real, job_id)
    assert job.status == "done"


async def test_un_lote_toma_como_maximo_10_aunque_se_pidan_mas(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    assert reencrypt.BATCH_SIZE == 10  # S6-D111
    await _sembrar(real, por, 23)
    job_id = await iniciar(real, CLASE)

    primero = await un_lote(real, job_id, 500)
    segundo = await un_lote(real, job_id, 500)
    tercero = await un_lote(real, job_id, 500)
    cuarto = await un_lote(real, job_id, 500)

    assert (primero, segundo, tercero, cuarto) == (10, 10, 3, 0)
    assert await _contar(real, puerto, await _activa(real)) == (23, 0, 23)


async def test_un_lote_pedido_de_a_10_respeta_el_tamano_pedido(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 12)
    job_id = await iniciar(real, CLASE)
    assert [await un_lote(real, job_id, 10), await un_lote(real, job_id, 10)] == [10, 2]


async def test_las_operaciones_del_lote_comparten_un_batch_id(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    await _sembrar(real, por, 3)
    job_id = await iniciar(real, CLASE)
    async with real() as sesion:
        await sesion.execute(text("SELECT 1"))
        previas = {
            f["id"]
            for f in (await sesion.execute(text("SELECT id FROM crypto.crypto_ops"))).mappings()
        }

    await un_lote(real, job_id)

    async with real() as sesion:
        filas = (
            (
                await sesion.execute(
                    text(
                        "SELECT id, verb, batch_id, count FROM crypto.crypto_ops "
                        "WHERE data_class = :c AND verb IN ('decrypt', 'encrypt')"
                    ),
                    {"c": CLASE},
                )
            )
            .mappings()
            .all()
        )
    nuevas = [f for f in filas if f["id"] not in previas]
    assert {f["verb"] for f in nuevas} == {"decrypt", "encrypt"}
    assert len({f["batch_id"] for f in nuevas}) == 1 and nuevas[0]["batch_id"] is not None
    assert {f["verb"]: f["count"] for f in nuevas} == {"decrypt": 3, "encrypt": 3}


# Concurrencia y cortes -------------------------------------------------------------------------


async def test_el_lote_salta_las_filas_bloqueadas_con_skip_locked(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    ids = await _sembrar(real, por, 3)
    job_id = await iniciar(real, CLASE)
    bloqueada = ids[0]

    async with real() as retenedora:
        await retenedora.execute(
            text("SELECT id FROM attachments.attachments WHERE id = :i FOR UPDATE"),
            {"i": bloqueada},
        )
        migradas = await asyncio.wait_for(un_lote(real, job_id), timeout=15)  # no espera el candado
        await retenedora.rollback()

    assert migradas == 2
    assert await un_lote(real, job_id) == 1  # liberada: el siguiente lote la toma
    assert await un_lote(real, job_id) == 0


async def test_un_corte_entre_el_objeto_y_el_update_se_recifra_otra_vez_sin_error(
    real: Fabrica, tmp_path: Path, por: UUID, puerto: Reencryptor
) -> None:
    raiz = tmp_path / "corte"
    raiz.mkdir()
    almacen = CorteTrasPut(raiz)
    service.configure_storage(almacen)
    try:
        (adjunto_id,) = await _sembrar(real, por, 1)
        async with real() as sesion:
            vieja = (await fila(sesion, adjunto_id))["key_id"]
        job_id = await iniciar(real, CLASE)
        nueva = await _activa(real)

        almacen.cortar = True
        with pytest.raises(RuntimeError, match="corte"):
            await un_lote(real, job_id)
        almacen.cortar = False

        async with real() as sesion:
            parcial = await fila(sesion, adjunto_id)
        assert parcial["key_id"] == vieja  # el UPDATE se revirtió...
        assert parse_blob(_leer_blob(almacen, parcial)).key_id == nueva  # ...el objeto ya es nuevo
        assert bus.decrypt(_leer_blob(almacen, parcial), bus.aad_for(adjunto_id)) == PDF

        assert await un_lote(real, job_id) == 1  # idempotente: se recifra otra vez sin error
        async with real() as sesion:
            final = await fila(sesion, adjunto_id)
        assert final["key_id"] == nueva
        assert bus.decrypt(_leer_blob(almacen, final), bus.aad_for(adjunto_id)) == PDF
        assert await un_lote(real, job_id) == 0
        assert await cerrar(real, job_id) is True
    finally:
        service.configure_storage(None)


async def test_las_fotos_no_se_tocan_al_rotar(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Reencryptor
) -> None:
    (foto_id,) = await _sembrar(real, por, 1, kind="photo")
    await _sembrar(real, por, 1)
    async with real() as sesion:
        antes = await fila(sesion, foto_id)
    objeto = (almacen.root / antes["filename_random"]).read_bytes()
    job_id = await iniciar(real, CLASE)

    assert await un_lote(real, job_id) == 1

    async with real() as sesion:
        despues = await fila(sesion, foto_id)
    assert despues["key_id"] is None and despues["updated_at"] == antes["updated_at"]
    assert (almacen.root / antes["filename_random"]).read_bytes() == objeto
