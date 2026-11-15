"""`classes.service.attended_member_ids` y `last_attendance_for` (S7-R2, US-163). Rojo R2.

Solo asistencias vivas; el corte es el inicio del día civil de Bogotá; sin ids no consulta.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes import service
from tests.conftest import ContadorDeConsultas
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members

BASE = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def test_ultima_asistencia_es_la_mas_reciente_viva(session: AsyncSession) -> None:
    uno, dos, tres = await make_members(session, 3)
    viejo = await make_session(session, starts_at=BASE)
    nuevo = await make_session(session, starts_at=BASE + timedelta(days=3))
    quitado = await make_session(session, starts_at=BASE + timedelta(days=6))
    await make_attendance(session, viejo, uno.id)
    await make_attendance(session, nuevo, uno.id)
    await make_attendance(session, quitado, uno.id, removed_at=BASE, removed_reason="x")
    await make_attendance(session, viejo, dos.id)
    resultado = await service.last_attendance_for(session, [uno.id, dos.id, tres.id])
    assert resultado == {uno.id: nuevo.starts_at, dos.id: viejo.starts_at}


async def test_sin_ids_no_consulta(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        assert await service.last_attendance_for(session, []) == {}
    assert contador_de_consultas.sentencias == []


async def test_attended_member_ids_corta_en_el_inicio_del_dia_de_bogota(
    session: AsyncSession,
) -> None:
    antes, justo = await make_members(session, 2)
    clase_antes = await make_session(session, starts_at=datetime(2026, 10, 14, 4, 59, tzinfo=UTC))
    clase_justo = await make_session(session, starts_at=datetime(2026, 10, 14, 5, 0, tzinfo=UTC))
    await make_attendance(session, clase_antes, antes.id)
    await make_attendance(session, clase_justo, justo.id)
    desde = await service.attended_member_ids(session, date(2026, 10, 14))
    assert desde == {justo.id}
    siempre = await service.attended_member_ids(session, None)
    assert siempre == {antes.id, justo.id}


async def test_attended_member_ids_ignora_las_quitadas(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, socio.id, removed_at=BASE, removed_reason="x")
    assert await service.attended_member_ids(session, None) == set()
