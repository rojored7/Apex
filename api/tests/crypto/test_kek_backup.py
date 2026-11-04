"""`core/crypto/kek_backup.py` (S4B-B3a, US-116; S4B-D58, S4B-D62).

- `verify_wrapped` con la misma KEK: `ok`, `total` = DEK `active` + `decrypt_only` (3), las
  `retired` no cuentan; con otra KEK todas las contadas fallan; el `bytearray` queda en ceros;
- `load_wrapped` solo lee: una sola sentencia `SELECT` sobre `crypto.crypto_keys`;
- `kek.backup` y el propósito `restore` de la bitácora (S4B-D74, S4B-D85).
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import kek_backup
from app.core.crypto.archive import VerifyKekResult
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.kek_backup import WrappedDek, load_wrapped, verify_wrapped
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import OP_PURPOSES
from tests.conftest import ContadorDeConsultas


def test_verify_wrapped_con_la_misma_kek_es_ok_y_cuenta_active_y_decrypt_only(
    kek_tmp: Path, wrapped_de_prueba: list[WrappedDek]
) -> None:
    resultado = verify_wrapped(bytearray(kek_tmp.read_bytes()), wrapped_de_prueba)

    assert resultado == VerifyKekResult(total=3, failed_key_ids=())
    assert resultado.ok is True


def test_verify_wrapped_excluye_las_retired(
    kek_tmp: Path, wrapped_de_prueba: list[WrappedDek]
) -> None:
    solo_retired = [d for d in wrapped_de_prueba if d.state == "retired"]

    resultado = verify_wrapped(bytearray(kek_tmp.read_bytes()), solo_retired)

    assert resultado.total == 0 and resultado.failed_key_ids == ()


def test_verify_wrapped_con_otra_kek_falla_en_todas_las_contadas(
    wrapped_de_prueba: list[WrappedDek],
) -> None:
    resultado = verify_wrapped(bytearray(os.urandom(32)), wrapped_de_prueba)

    contadas = [d.key_id for d in wrapped_de_prueba if d.state != "retired"]
    assert resultado.total == 3
    assert sorted(resultado.failed_key_ids) == sorted(contadas)
    assert resultado.ok is False


def test_verify_wrapped_con_una_sola_dek_ajena_falla_solo_en_esa(
    kek_tmp: Path, wrapped_de_prueba: list[WrappedDek]
) -> None:
    ajena = wrapped_de_prueba[3]  # `retired` con otra KEK, reetiquetada como `active`
    mezcla = [*wrapped_de_prueba[:2], WrappedDek(ajena.key_id, 1, "active", ajena.wrapped_material)]

    resultado = verify_wrapped(bytearray(kek_tmp.read_bytes()), mezcla)

    assert resultado.total == 3 and resultado.failed_key_ids == (ajena.key_id,)


def test_verify_wrapped_deja_el_bytearray_en_ceros(
    kek_tmp: Path, wrapped_de_prueba: list[WrappedDek]
) -> None:
    kek = bytearray(kek_tmp.read_bytes())

    verify_wrapped(kek, wrapped_de_prueba)

    assert len(kek) == 32 and kek == bytearray(32)


def test_verify_wrapped_deja_el_bytearray_en_ceros_aunque_falle(
    wrapped_de_prueba: list[WrappedDek],
) -> None:
    kek = bytearray(os.urandom(32))

    verify_wrapped(kek, wrapped_de_prueba)

    assert kek == bytearray(32)


def test_verify_wrapped_no_deja_la_kek_en_el_resultado_ni_en_su_repr(
    kek_tmp: Path, wrapped_de_prueba: list[WrappedDek]
) -> None:
    kek_bytes = kek_tmp.read_bytes()

    resultado = verify_wrapped(bytearray(kek_bytes), wrapped_de_prueba)

    assert kek_bytes.hex() not in repr(resultado)


def test_el_modulo_no_expone_un_lector_publico_de_la_kek() -> None:
    publicos = {n for n in dir(kek_backup) if not n.startswith("_")}
    assert not {n for n in publicos if "read_kek" in n or n == "get_kek"}


async def test_load_wrapped_devuelve_las_llaves_envueltas_con_un_solo_select(
    sin_llaves: AsyncSession,
    proveedor_local: LocalFileProvider,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local)

    with contador_de_consultas.midiendo():
        filas = await load_wrapped(sin_llaves)

    sentencias = [s for s in contador_de_consultas.sentencias if "crypto_keys" in s]
    assert len(sentencias) == 1 and sentencias[0].lstrip().upper().startswith("SELECT")
    assert len(filas) == 8  # cinco DEK y tres llaves de índice (documento, teléfono, correo)
    assert all(isinstance(f, WrappedDek) and f.wrapped_material.startswith(b"apxw1") for f in filas)
    assert {f.state for f in filas} == {"active"}


async def test_load_wrapped_no_escribe_nada(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local)
        await sin_llaves.flush()

    await load_wrapped(sin_llaves)

    assert not sin_llaves.new and not sin_llaves.dirty and not sin_llaves.deleted


def test_el_proposito_restore_existe_en_la_bitacora() -> None:
    """S4B-D74: `restore-kek` registra `export` con `purpose="restore"`; `oplog.record` rechaza
    los propósitos que no están en `OP_PURPOSES` (hoy no incluye `restore`)."""
    assert "restore" in OP_PURPOSES
