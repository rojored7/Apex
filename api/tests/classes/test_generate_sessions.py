"""`classes.service.generate_sessions` con base real (S7-B1, US-156; S7-D10). Rojo B1.

Hoy (reloj de las pruebas) es el miércoles 21 de octubre de 2026 en Bogotá: los lunes de los
próximos 14 días son el 26 de octubre y el 2 de noviembre. La franja de fábrica es lunes y
miércoles a las 06:00 (los miércoles 21 y 28, y los lunes 26 y 2: cuatro sesiones).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.classes import service
from app.modules.classes.schemas import SlotCreate, SlotPatch
from tests.conftest import CrearUsuario
from tests.factories.classes import make_slot

HOY = date(2026, 10, 21)
TABLA = "classes.class_sessions"

pytestmark = pytest.mark.usefixtures("reloj")


async def _generar(session: AsyncSession, **opciones: Any) -> service.GenerateResult:
    with actor_scope(SYSTEM_USER_ID):
        resultado = await service.generate_sessions(session, today=HOY, **opciones)
        await session.commit()
    return resultado


async def _filas(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = text(f"SELECT * FROM {TABLA} ORDER BY starts_at, slot_id")  # noqa: S608
    return [dict(f) for f in (await session.execute(consulta)).mappings().all()]


async def test_genera_las_sesiones_de_los_14_dias_con_los_datos_de_la_franja(
    session: AsyncSession,
) -> None:
    franja = await make_slot(session, weekdays=[0], capacity=12, duration_min=75, name="Fuerza")
    resultado = await _generar(session)
    assert (resultado.created, resultado.slots) == (2, 1)
    filas = await _filas(session)
    assert [f["starts_at"] for f in filas] == [
        datetime(2026, 10, 26, 11, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
    ]
    assert all(f["slot_id"] == franja.id and f["status"] == "scheduled" for f in filas)
    assert all(
        (f["capacity"], f["duration_min"], f["name"], f["coach_id"], f["wod_id"])
        == (12, 75, "Fuerza", None, None)
        for f in filas
    )
    assert [f["session_date"] for f in filas] == [date(2026, 10, 26), date(2026, 11, 2)]


async def test_dos_corridas_no_duplican(session: AsyncSession) -> None:
    await make_slot(session)
    primera = await _generar(session)
    segunda = await _generar(session)
    assert primera.created == 4 and segunda.created == 0
    assert len(await _filas(session)) == 4


async def test_dias_acota_la_ventana(session: AsyncSession) -> None:
    await make_slot(session, weekdays=[0, 1, 2, 3, 4, 5, 6])
    resultado = await _generar(session, days=3)
    assert resultado.created == 3
    assert [f["session_date"] for f in await _filas(session)] == [
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 23),
    ]


async def test_una_franja_pausada_no_genera(session: AsyncSession) -> None:
    await make_slot(session, is_active=False)
    resultado = await _generar(session)
    assert (resultado.created, resultado.slots) == (0, 0)
    assert await _filas(session) == []


async def test_slot_ids_limita_a_esas_franjas(session: AsyncSession) -> None:
    uno = await make_slot(session, weekdays=[0], start_time="06:00")
    await make_slot(session, weekdays=[0], start_time="07:00")
    resultado = await _generar(session, slot_ids=[uno.id])
    assert (resultado.created, resultado.slots) == (2, 1)
    assert {f["slot_id"] for f in await _filas(session)} == {uno.id}


async def test_una_sesion_ya_generada_no_cambia_si_la_franja_se_edita(
    session: AsyncSession,
) -> None:
    franja = await make_slot(session, weekdays=[0], capacity=15)
    await _generar(session)
    antes = await _filas(session)
    await session.execute(
        text("UPDATE classes.class_slots SET capacity = 5 WHERE id = :i"), {"i": franja.id}
    )
    await session.commit()
    resultado = await _generar(session)
    assert resultado.created == 0
    assert await _filas(session) == antes


async def test_cancelada_no_se_regenera(session: AsyncSession) -> None:
    await make_slot(session, weekdays=[0])
    await _generar(session)
    await session.execute(
        text(
            f"UPDATE {TABLA} SET status = 'cancelled', cancel_reason = 'Feriado', "  # noqa: S608
            "cancelled_by = :u, cancelled_at = now() WHERE session_date = '2026-10-26'"
        ),
        {"u": SYSTEM_USER_ID},
    )
    await session.commit()
    resultado = await _generar(session)
    assert resultado.created == 0
    estados = [f["status"] for f in await _filas(session)]
    assert estados == ["cancelled", "scheduled"]


async def test_created_by_system_y_auditoria_de_cada_alta(session: AsyncSession) -> None:
    await make_slot(session, weekdays=[0])
    await _generar(session)
    filas = await _filas(session)
    assert {f["created_by"] for f in filas} == {SYSTEM_USER_ID}
    auditoria = (
        await session.execute(
            text("SELECT action, user_id FROM audit.audit_log WHERE table_name = :t ORDER BY seq"),
            {"t": TABLA},
        )
    ).all()
    assert [(a, u) for a, u in auditoria] == [("insert", SYSTEM_USER_ID)] * 2


async def test_emite_session_generated_por_cada_sesion(session: AsyncSession) -> None:
    franja = await make_slot(session, weekdays=[0], name="Fuerza")
    vistos: list[service.SessionGenerated] = []

    async def anotar(evento: service.SessionGenerated, _: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(service.SessionGenerated, anotar)  # `restaurar_bus` lo quita
    await _generar(session)
    assert [(e.slot_id, e.starts_at) for e in vistos] == [
        (franja.id, datetime(2026, 10, 26, 11, 0, tzinfo=UTC)),
        (franja.id, datetime(2026, 11, 2, 11, 0, tzinfo=UTC)),
    ]
    assert {f["id"] for f in await _filas(session)} == {e.session_id for e in vistos}


async def test_job_y_cli_a_la_vez_una_sola_insercion(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    await make_slot(primera, weekdays=[0])

    async def correr(sesion: AsyncSession) -> int:
        with actor_scope(SYSTEM_USER_ID):
            resultado = await service.generate_sessions(sesion, today=HOY)
            await sesion.commit()
        return resultado.created

    creadas = await asyncio.gather(correr(primera), correr(segunda))
    assert sorted(creadas) == [0, 2]
    assert len(await _filas(primera)) == 2


# Alta de una franja ----


def _alta(**cambios: Any) -> SlotCreate:
    valores: dict[str, Any] = {"weekdays": [0], "start_time": "06:00", "duration_min": 60}
    valores.update(cambios)
    return SlotCreate.model_validate(valores)


async def test_crear_franja_genera_su_ventana(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with actor_scope(admin.id):
        franja = await service.create_slot(session, _alta(capacity=9), admin.id)
        await session.commit()
    filas = await _filas(session)
    assert [f["session_date"] for f in filas] == [date(2026, 10, 26), date(2026, 11, 2)]
    assert all(f["slot_id"] == franja.id and f["capacity"] == 9 for f in filas)
    assert {f["created_by"] for f in filas} == {admin.id}


async def test_crear_franja_vigente_desde_el_futuro_solo_genera_desde_esa_fecha(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with actor_scope(admin.id):
        await service.create_slot(session, _alta(valid_from="2026-11-02"), admin.id)
        await session.commit()
    assert [f["session_date"] for f in await _filas(session)] == [date(2026, 11, 2)]


async def test_patch_de_la_franja_no_toca_las_sesiones_ya_generadas(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """Q23: cambiar la franja solo afecta a las sesiones que aún no se generaron."""
    admin = await usuario_real("admin")
    with actor_scope(admin.id):
        franja = await service.create_slot(session, _alta(capacity=9), admin.id)
        await session.commit()
        antes = await _filas(session)
        await service.update_slot(
            session,
            franja.id,
            SlotPatch.model_validate({"capacity": 3, "start_time": "07:30"}),
            admin.id,
        )
        await session.commit()
    assert await _filas(session) == antes
