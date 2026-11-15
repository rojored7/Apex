"""`list_attendance` (GET /attendance) con base real (S7-R1, US-162 CA2 y CA3). Rojo R1.

La lista ya existía desde C1; R1 fija sus filtros, los nombres por `members.service.names_for`
(una consulta, nunca campos cifrados) y el rango sobre `checked_in_at`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.classes import service
from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.schemas import AttendanceListQuery, AttendanceRowOut
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members

BASE = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)
CAMPOS_CIFRADOS = {"document", "phone", "email", "birth_date", "emergency_contact"}

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _listar(session: AsyncSession, **filtros: object) -> list[AttendanceRowOut]:
    pagina = await service.list_attendance(
        session,
        AttendanceListQuery(**filtros),
        PageParams(limit=200),  # type: ignore[arg-type]
    )
    return pagina.items


async def test_filtros_de_socio_sesion_y_marca(session: AsyncSession) -> None:
    uno, otro = await make_members(session, 2)
    a = await make_session(session, starts_at=BASE)
    b = await make_session(session, starts_at=BASE + timedelta(days=1))
    await make_attendance(session, a, uno.id)
    await make_attendance(session, a, otro.id, flags=["expired"])
    await make_attendance(session, b, uno.id, flags=["other_day"])
    assert len(await _listar(session)) == 3
    assert {i.member_id for i in await _listar(session, member_id=uno.id)} == {uno.id}
    assert len(await _listar(session, session_id=a.id)) == 2
    marcadas = await _listar(session, flagged=True)
    assert len(marcadas) == 2 and all(i.flagged for i in marcadas)
    limpias = await _listar(session, flagged=False)
    assert len(limpias) == 1 and not limpias[0].flagged


async def test_rango_sobre_checked_in_at_y_orden_descendente(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)
    for dia in range(4):
        clase = await make_session(session, starts_at=BASE + timedelta(days=dia))
        await make_attendance(session, clase, socio.id)
    todas = await _listar(session)
    assert [i.checked_in_at for i in todas] == sorted(
        (i.checked_in_at for i in todas), reverse=True
    )
    desde = BASE + timedelta(days=1)
    hasta = BASE + timedelta(days=3)
    acotadas = await _listar(session, from_at=desde, to_at=hasta)
    assert len(acotadas) == 2  # `to` excluye
    assert {i.checked_in_at for i in acotadas} == {desde, desde + timedelta(days=1)}


async def test_rango_invertido_da_422(session: AsyncSession) -> None:
    with pytest.raises(ClassValidationError) as caught:
        await _listar(session, from_at=BASE + timedelta(days=1), to_at=BASE)
    assert caught.value.field == "to"


async def test_no_cuentan_las_quitadas(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, socio.id, removed_at=BASE, removed_reason="x")
    assert await _listar(session) == []


async def test_names_for_en_una_consulta_y_sin_cifrados(session: AsyncSession) -> None:
    socios = await make_members(session, 5)
    clase = await make_session(session, starts_at=BASE)
    for socio in socios:
        await make_attendance(session, clase, socio.id)
    motor = session.get_bind()
    sobre_socios: list[str] = []

    def _anota(conn: object, cursor: object, statement: str, *args: object) -> None:
        if "members.members" in statement:
            sobre_socios.append(statement)

    event.listen(motor, "before_cursor_execute", _anota)
    try:
        filas = await _listar(session)
    finally:
        event.remove(motor, "before_cursor_execute", _anota)
    assert len(sobre_socios) == 1  # un `names_for` por página, no uno por fila
    assert {f.first_name for f in filas} == {s.first_name for s in socios}
    assert CAMPOS_CIFRADOS.isdisjoint(AttendanceRowOut.model_fields)
    for sql in sobre_socios:
        for campo in ("document", "phone", "email", "birth_date", "emergency_contact"):
            assert f"members.{campo}" not in sql.lower()


async def test_busqueda_q_por_nombre_del_socio(session: AsyncSession) -> None:
    uno, otro = await make_members(session, 2)
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, uno.id)
    await make_attendance(session, clase, otro.id)
    assert {i.member_id for i in await _listar(session, q="Lucía 1")} == {otro.id}
    assert await _listar(session, q="Zzzzz") == []
