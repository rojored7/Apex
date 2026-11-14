"""`kek_backup.local_kek_present`: hay KEK local si hay filas `encrypt|index` `local` o `kek.bin`.

Las filas `sign` locales no cuentan (no se envuelven con la KEK). Lo usa `cli_manifest` para decidir
si la prueba de custodia pide el `verify-kek-backup` o solo el manifiesto con instantánea.
"""

from __future__ import annotations

import pytest

from app.core.crypto.kek_backup import local_kek_present
from tests.crypto._migracion import Entorno, migracion_lista, migrar_a_mano
from tests.crypto.conftest import fila_sign

__all__ = ["migracion_lista"]


async def _hay(e: Entorno, *, archivo: bool = False) -> bool:
    async with e.fabrica() as sesion:
        return await local_kek_present(sesion, file_present=archivo)


async def test_con_filas_locales_de_cifrado_hay_kek_local_aunque_falte_el_archivo(
    migracion_lista: Entorno,
) -> None:
    assert await _hay(migracion_lista) is True


async def test_sin_filas_locales_y_sin_archivo_no_hay_kek_local(migracion_lista: Entorno) -> None:
    await migrar_a_mano(migracion_lista)

    assert await _hay(migracion_lista) is False


async def test_el_archivo_presente_cuenta_aunque_todas_las_filas_esten_en_openbao(
    migracion_lista: Entorno,
) -> None:
    await migrar_a_mano(migracion_lista)

    assert await _hay(migracion_lista, archivo=True) is True


@pytest.mark.usefixtures("reloj")
async def test_una_fila_sign_local_no_cuenta_como_kek_local(migracion_lista: Entorno) -> None:
    from app.core.context import SYSTEM_USER_ID, actor_scope

    await migrar_a_mano(migracion_lista)
    async with migracion_lista.fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await fila_sign(sesion, migracion_lista.local)
            await sesion.commit()

    assert await _hay(migracion_lista) is False
