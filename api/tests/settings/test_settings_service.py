"""Casos de uso de settings con PostgreSQL real (US-054 T8; N-17; flujo 7.3 del blueprint).

Primer guardado inserta con versión 1 y auditoría `insert`; el segundo sube a 2 con `update`
y `before`/`after`; una versión vieja da `VersionConflict` sin tocar la fila; un valor inválido
no cambia la fila ni crea auditoría; dos primeros guardados concurrentes dejan una fila y un
409 (`dos_sesiones`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.exceptions import (
    SectionNotAvailable,
    SettingsValidationError,
    VersionConflict,
)
from app.modules.settings.schemas import GymView, SectionKey, SectionOut
from app.modules.settings.service import get, get_section, gym_name, update_section
from tests.settings._apoyo import (
    ADMIN_ID,
    GYM_DEFAULTS,
    GYM_OK,
    NO_HABILITADAS,
    TABLA,
    contar_filas,
    fila,
    filas_de_auditoria,
)


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


async def _guardar(
    db: AsyncSession, valor: dict[str, object], version: int, key: str = "gym"
) -> SectionOut:
    return await update_section(db, key, valor, version, ADMIN_ID)


async def test_sin_fila_get_section_devuelve_defaults_en_version_0(db: AsyncSession) -> None:
    salida = await get_section(db, "gym")
    assert salida.key == SectionKey.gym
    assert salida.value == GYM_DEFAULTS
    assert salida.version == 0
    assert salida.updated_at is None and salida.updated_by is None
    assert await fila(db, "gym") is None  # leer no siembra filas


async def test_primer_guardado_inserta_en_version_1_y_audita_insert(db: AsyncSession) -> None:
    salida = await _guardar(db, GYM_OK, 0)
    assert salida.version == 1 and salida.value == GYM_OK
    assert salida.updated_by == ADMIN_ID and salida.updated_at is not None

    guardada = await fila(db, "gym")
    assert guardada is not None
    assert guardada["version"] == 1 and guardada["value"] == GYM_OK
    assert guardada["created_by"] == ADMIN_ID and guardada["updated_by"] == ADMIN_ID

    auditoria = await filas_de_auditoria(db)
    assert [f["action"] for f in auditoria] == ["insert"]
    insert = auditoria[0]
    assert insert["table_name"] == TABLA
    assert insert["user_id"] == ADMIN_ID
    assert insert["subject_member_id"] is None  # la configuración no es de un socio
    assert insert["before"] is None
    assert insert["after"]["key"] == "gym"
    assert insert["after"]["version"] == 1
    assert insert["after"]["value"] == GYM_OK


async def test_segundo_guardado_sube_a_2_y_audita_update_con_before_y_after(
    db: AsyncSession,
) -> None:
    await _guardar(db, GYM_OK, 0)
    nuevo = {**GYM_OK, "name": "APEX Sabaneta"}
    salida = await _guardar(db, nuevo, 1)
    assert salida.version == 2 and salida.value == nuevo

    guardada = await fila(db, "gym")
    assert guardada is not None and guardada["version"] == 2 and guardada["value"] == nuevo
    auditoria = await filas_de_auditoria(db)
    assert [f["action"] for f in auditoria] == ["insert", "update"]
    update = auditoria[1]
    assert update["subject_member_id"] is None and update["user_id"] == ADMIN_ID
    assert update["before"]["version"] == 1 and update["after"]["version"] == 2
    assert update["before"]["value"] == GYM_OK
    assert update["after"]["value"] == nuevo


async def test_version_vieja_da_conflicto_sin_cambiar_la_fila_ni_auditar(
    db: AsyncSession,
) -> None:
    await _guardar(db, GYM_OK, 0)
    await _guardar(db, {**GYM_OK, "city": "Sabaneta"}, 1)
    auditadas = len(await filas_de_auditoria(db))

    with pytest.raises(VersionConflict) as excinfo:
        await _guardar(db, {**GYM_OK, "city": "Itagüí"}, 1)
    assert excinfo.value.status == 409 and excinfo.value.code == "version_conflict"

    guardada = await fila(db, "gym")
    assert guardada is not None and guardada["version"] == 2
    assert guardada["value"]["city"] == "Sabaneta"
    assert len(await filas_de_auditoria(db)) == auditadas


async def test_primer_guardado_con_version_distinta_de_0_da_conflicto(db: AsyncSession) -> None:
    with pytest.raises(VersionConflict):
        await _guardar(db, GYM_OK, 3)
    assert await fila(db, "gym") is None
    assert await filas_de_auditoria(db) == []


async def test_valor_invalido_sin_fila_no_crea_fila_ni_auditoria(db: AsyncSession) -> None:
    with pytest.raises(SettingsValidationError) as excinfo:
        await _guardar(db, {**GYM_OK, "name": ""}, 0)
    assert excinfo.value.field == "value.name"
    assert await fila(db, "gym") is None
    assert await filas_de_auditoria(db) == []


async def test_valor_invalido_con_fila_no_cambia_la_fila_ni_audita(db: AsyncSession) -> None:
    await _guardar(db, GYM_OK, 0)
    with pytest.raises(SettingsValidationError) as excinfo:
        await _guardar(db, {**GYM_OK, "email": "no-es-correo"}, 1)
    assert excinfo.value.field == "value.email"
    guardada = await fila(db, "gym")
    assert guardada is not None and guardada["version"] == 1 and guardada["value"] == GYM_OK
    assert [f["action"] for f in await filas_de_auditoria(db)] == ["insert"]


async def test_patch_reemplaza_la_seccion_completa_sin_merge(db: AsyncSession) -> None:
    await _guardar(db, GYM_OK, 0)
    salida = await _guardar(db, {"name": "Solo nombre"}, 1)
    assert salida.value == {**GYM_DEFAULTS, "name": "Solo nombre"}
    guardada = await fila(db, "gym")
    assert guardada is not None and guardada["value"]["nit"] is None


@pytest.mark.parametrize("clave", [*NO_HABILITADAS, "inexistente"])
async def test_secciones_no_habilitadas_dan_section_not_available(
    db: AsyncSession, clave: str
) -> None:
    with pytest.raises(SectionNotAvailable):
        await get_section(db, clave)
    with pytest.raises(SectionNotAvailable):
        await _guardar(db, {}, 0, key=clave)
    assert await contar_filas(db) == 0


async def test_get_interno_devuelve_el_modelo_con_defaults_y_luego_lo_guardado(
    db: AsyncSession,
) -> None:
    """La lectura interna usa el esquema de salida (`GymView`, sin el texto seguro de N-2)."""
    antes = await get(db, SectionKey.gym)
    assert isinstance(antes, GymView) and antes.model_dump(mode="json") == GYM_DEFAULTS
    await _guardar(db, GYM_OK, 0)
    despues = await get(db, SectionKey.gym)
    assert isinstance(despues, GymView) and despues.model_dump(mode="json") == GYM_OK


async def test_gym_name_tiene_respaldo_apex_y_luego_el_nombre_guardado(db: AsyncSession) -> None:
    assert await gym_name(db) == "APEX"
    await _guardar(db, GYM_OK, 0)
    assert await gym_name(db) == "CrossFit Envigado"


async def test_el_log_no_lleva_el_valor_de_la_seccion(
    db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await _guardar(db, GYM_OK, 0)
    assert "CrossFit Envigado" not in caplog.text
    assert "901234567-8" not in caplog.text


async def test_dos_primeros_guardados_concurrentes_dejan_una_fila_y_un_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones

    async def guardar(sesion: AsyncSession, nombre: str) -> SectionOut | VersionConflict:
        try:
            async with sesion.begin():
                return await update_section(sesion, "gym", {**GYM_OK, "name": nombre}, 0, ADMIN_ID)
        except VersionConflict as conflicto:
            return conflicto

    with actor_scope(ADMIN_ID):
        resultados = await asyncio.gather(guardar(primera, "Uno"), guardar(segunda, "Dos"))

    exitos = [r for r in resultados if isinstance(r, SectionOut)]
    conflictos = [r for r in resultados if isinstance(r, VersionConflict)]
    assert len(exitos) == 1 and len(conflictos) == 1
    assert exitos[0].version == 1
    async with primera.begin():
        assert await contar_filas(primera) == 1
        guardada = await fila(primera, "gym")
    assert guardada is not None and guardada["version"] == 1
    assert guardada["value"]["name"] == exitos[0].value["name"]
