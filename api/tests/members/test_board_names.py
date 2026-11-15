"""`members.service.board_names` (S8-C2, S8-D34, M-4): nombres de la TV sin bajas ni socios sin
autorización de datos vigente. Base real."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members import service
from app.modules.members.models import Member
from tests.factories.members import make_members
from tests.tv._apoyo import CONSENTIDO, dar_de_baja

pytestmark = pytest.mark.usefixtures("bus_listo")


async def test_sin_bajas(session: AsyncSession) -> None:
    vivo, baja = await make_members(session, 2, data_consent_at=CONSENTIDO)
    await dar_de_baja(session, baja)
    nombres = await service.board_names(session, [vivo.id, baja.id])
    assert set(nombres) == {vivo.id}
    assert nombres[vivo.id].first_name == vivo.first_name
    assert baja.id in await service.names_for(session, [baja.id])  # `names_for` sí incluye bajas


async def test_regla_igual_a_count_without_consent(session: AsyncSession) -> None:
    con, sin_a, sin_b, baja_sin = await make_members(session, 4, data_consent_at=CONSENTIDO)
    for socio in (sin_a, sin_b, baja_sin):
        await session.execute(
            update(Member).where(Member.id == socio.id).values(data_consent_at=None)
        )
    await dar_de_baja(session, baja_sin)
    nombres = await service.board_names(session, [con.id, sin_a.id, sin_b.id, baja_sin.id])
    assert set(nombres) == {con.id}
    # `count_without_consent` cuenta a los vivos sin autorización: los dos que la TV deja fuera.
    assert await service.count_without_consent(session) == 2


async def test_sin_ids_o_ids_inexistentes(session: AsyncSession) -> None:
    assert await service.board_names(session, []) == {}
    assert await service.board_names(session, [uuid4()]) == {}


async def test_una_consulta(session: AsyncSession) -> None:
    socios = await make_members(session, 5, data_consent_at=CONSENTIDO)
    motor = session.get_bind()
    sobre_socios: list[str] = []

    def _anota(conn: object, cursor: object, statement: str, *args: object) -> None:
        if "members.members" in statement:
            sobre_socios.append(statement)

    event.listen(motor, "before_cursor_execute", _anota)
    try:
        nombres = await service.board_names(session, [s.id for s in socios])
    finally:
        event.remove(motor, "before_cursor_execute", _anota)
    assert len(sobre_socios) == 1 and len(nombres) == 5
    for campo in ("document", "phone", "email", "birth_date", "emergency_contact"):
        assert f"members.{campo}" not in sobre_socios[0].lower()
