"""Puerto `Reencryptor` y ramas del puerto en `core/crypto/service.py` (S6-B1; S6-D14, G-09). Rojo.

- registro: `register_reencryptor` / `get_reencryptor` / `reencryptor_registered`; registrar dos
  veces la misma clase es un error (`ValueError` o `CryptoError`);
- `start_rotation` de una clase cifrada sin columnas ni puerto:
  `CryptoError("rotation_not_supported")`
  sin crear job ni llave;
- con un puerto (`reencryptor_doble`): `start_rotation` toma el total de `count_pending` con la
  llave nueva, `reencrypt_batch` delega en `reencrypt_batch` del puerto y `finish_rotation`
  cierra con `count_pending == 0`;
- `finish_rotation` con `count_pending > 0` devuelve `False` sin marcar el job (como con columnas;
  el CLI marca `failed` al agotar las pasadas) y la anterior sigue `decrypt_only`. Nunca `done`.
Los servicios se llaman con commit real sobre `rotacion_lista` (`_rotacion_flujo`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob
from app.core.crypto.reencryptor import (
    get_reencryptor,
    reencryptor_registered,
    register_reencryptor,
)
from app.core.crypto.registry import DataClassSpec, override_registry
from tests.crypto._rotacion import Fabrica, llaves_de, registro_de_rotacion
from tests.crypto._rotacion_flujo import cerrar, iniciar, job_de, un_lote
from tests.crypto.conftest import ReencryptorDoble

pytestmark = pytest.mark.usefixtures("reloj")

ADJUNTOS = "attachment.sensitive"
SIN_COLUMNAS = DataClassSpec(ADJUNTOS, True, None, False, "str", ())


@contextmanager
def _registro_con_adjuntos() -> Iterator[None]:
    with override_registry({**registro_de_rotacion(), ADJUNTOS: SIN_COLUMNAS}):
        yield


async def _crear_llave_de_adjuntos(fabrica: Fabrica, proveedor: LocalFileProvider) -> None:
    async with fabrica() as sesion, sesion.begin():
        with actor_scope(SYSTEM_USER_ID):
            await ensure_keys(sesion, proveedor, lambda _n: proveedor)


async def _jobs(fabrica: Fabrica) -> list[CryptoJob]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(CryptoJob))).all())


async def _estados(fabrica: Fabrica) -> list[tuple[int, str]]:
    async with fabrica() as sesion:
        return [(k.version, k.state) for k in await llaves_de(sesion, "encrypt", ADJUNTOS)]


# Registro --------------------------------------------------------------------------------------


def test_register_get_y_registered(reencryptor_doble: ReencryptorDoble) -> None:
    assert not reencryptor_registered(ADJUNTOS)
    assert get_reencryptor(ADJUNTOS) is None

    register_reencryptor(ADJUNTOS, reencryptor_doble)

    assert reencryptor_registered(ADJUNTOS)
    assert get_reencryptor(ADJUNTOS) is reencryptor_doble
    assert not reencryptor_registered("member.document")


def test_registrar_dos_veces_la_misma_clase_es_un_error(
    reencryptor_doble: ReencryptorDoble,
) -> None:
    register_reencryptor(ADJUNTOS, reencryptor_doble)

    with pytest.raises((ValueError, CryptoError)):
        register_reencryptor(ADJUNTOS, ReencryptorDoble())

    assert get_reencryptor(ADJUNTOS) is reencryptor_doble


def test_registrar_clases_distintas_es_valido(reencryptor_doble: ReencryptorDoble) -> None:
    otro = ReencryptorDoble()
    register_reencryptor(ADJUNTOS, reencryptor_doble)
    register_reencryptor("member.document", otro)

    assert get_reencryptor("member.document") is otro


# Clase sin columnas ni puerto ------------------------------------------------------------------


async def test_start_rotation_sin_columnas_ni_puerto_responde_rotation_not_supported(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, reencryptor_doble: ReencryptorDoble
) -> None:
    with _registro_con_adjuntos():
        await _crear_llave_de_adjuntos(rotacion_lista, proveedor_local)

        with pytest.raises(CryptoError) as error:
            await iniciar(rotacion_lista, ADJUNTOS)

    assert error.value.code == "rotation_not_supported"
    assert await _jobs(rotacion_lista) == []
    assert await _estados(rotacion_lista) == [(1, "active")]


# Clase con puerto ------------------------------------------------------------------------------


async def test_start_rotation_con_puerto_toma_el_total_de_count_pending(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, reencryptor_doble: ReencryptorDoble
) -> None:
    reencryptor_doble.pendientes = 5
    register_reencryptor(ADJUNTOS, reencryptor_doble)
    with _registro_con_adjuntos():
        await _crear_llave_de_adjuntos(rotacion_lista, proveedor_local)

        job_id = await iniciar(rotacion_lista, ADJUNTOS)

    job = await job_de(rotacion_lista, job_id)
    assert (job.kind, job.status, job.data_class, job.total, job.done) == (
        "rotate",
        "running",
        ADJUNTOS,
        5,
        0,
    )
    assert await _estados(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
    async with rotacion_lista() as sesion:
        _, nueva = await llaves_de(sesion, "encrypt", ADJUNTOS)
    assert ("count_pending", nueva.id, None) in reencryptor_doble.llamadas


async def test_reencrypt_batch_delega_en_el_puerto_con_la_llave_activa_y_el_tamano(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, reencryptor_doble: ReencryptorDoble
) -> None:
    reencryptor_doble.pendientes = 5
    reencryptor_doble.migradas_por_lote = 3
    register_reencryptor(ADJUNTOS, reencryptor_doble)
    with _registro_con_adjuntos():
        await _crear_llave_de_adjuntos(rotacion_lista, proveedor_local)
        job_id = await iniciar(rotacion_lista, ADJUNTOS)

        migradas = await un_lote(rotacion_lista, job_id, 200)

    assert migradas == 3
    async with rotacion_lista() as sesion:
        _, nueva = await llaves_de(sesion, "encrypt", ADJUNTOS)
    assert ("reencrypt_batch", nueva.id, 200) in reencryptor_doble.llamadas
    assert (await job_de(rotacion_lista, job_id)).done == 3


async def test_finish_rotation_con_el_puerto_en_cero_cierra_en_done_y_deja_decrypt_only(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, reencryptor_doble: ReencryptorDoble
) -> None:
    reencryptor_doble.pendientes = 2
    reencryptor_doble.migradas_por_lote = 2
    register_reencryptor(ADJUNTOS, reencryptor_doble)
    with _registro_con_adjuntos():
        await _crear_llave_de_adjuntos(rotacion_lista, proveedor_local)
        job_id = await iniciar(rotacion_lista, ADJUNTOS)
        await un_lote(rotacion_lista, job_id, 500)

        cerrada = await cerrar(rotacion_lista, job_id)

    assert cerrada is True
    job = await job_de(rotacion_lista, job_id)
    assert (job.status, job.done, job.total) == ("done", 2, 2)
    assert await _estados(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
    assert "count_pending" in reencryptor_doble.nombres()


async def test_finish_rotation_con_pendientes_devuelve_false_sin_marcar_el_job(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, reencryptor_doble: ReencryptorDoble
) -> None:
    """Simétrico a las columnas (revisión de seguridad de B1): sin cerrar y sin `failed`; el CLI
    reintenta y, al agotar las pasadas, marca `failed` (`test_rotate_key_cli.py`). Nunca `done`."""
    reencryptor_doble.pendientes = 4
    reencryptor_doble.migradas_por_lote = 0  # el puerto no logra migrar nada
    register_reencryptor(ADJUNTOS, reencryptor_doble)
    with _registro_con_adjuntos():
        await _crear_llave_de_adjuntos(rotacion_lista, proveedor_local)
        job_id = await iniciar(rotacion_lista, ADJUNTOS)
        await un_lote(rotacion_lista, job_id, 500)

        resultado = await cerrar(rotacion_lista, job_id)

    assert resultado is False
    job = await job_de(rotacion_lista, job_id)
    assert (job.status, job.error) == ("running", None)
    assert await _estados(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
