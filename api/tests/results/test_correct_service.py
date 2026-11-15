"""Corregir un resultado con `supersedes_id` (S8-B2, US-170, Q18; S8-D11, S8-D35). Base real."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from tests.factories.members import make_members
from tests.factories.wods import make_movement, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _falla(coro: Any) -> DomainError:
    with pytest.raises(DomainError) as info:
        await coro
    return info.value


async def _auditoria(session: AsyncSession, record_id: Any) -> list[tuple[Any, ...]]:
    filas = await session.execute(
        text(
            "SELECT action, before->>'is_current', after->>'is_current', "
            "subject_member_id::text FROM audit.audit_log "
            "WHERE table_name = 'results.wod_results' AND record_id = :i ORDER BY seq"
        ),
        {"i": record_id},
    )
    return [tuple(f) for f in filas.all()]


async def _fila(session: AsyncSession, result_id: Any) -> dict[str, Any]:
    consulta = text("SELECT * FROM results.wod_results WHERE id = :i")
    return dict((await session.execute(consulta, {"i": result_id})).mappings().one())


async def test_dos_filas_de_auditoria_insert_y_update(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    dos = await registrar(session, e, seconds=280, supersedes_id=uno.id)
    assert await _auditoria(session, dos.id) == [("insert", None, "true", str(e.socio_id))]
    assert await _auditoria(session, uno.id) == [
        ("insert", None, "true", str(e.socio_id)),
        ("update", "true", "false", str(e.socio_id)),
    ]


async def test_anterior_intacto_salvo_is_current(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300, level="rx_plus")
    antes = await _fila(session, uno.id)
    await registrar(session, e, seconds=280, level="scaled", supersedes_id=uno.id)
    despues = await _fila(session, uno.id)
    cambiadas = {k for k in antes if antes[k] != despues[k]}
    assert cambiadas <= {"is_current", "updated_at"}
    assert despues["is_current"] is False and despues["seconds"] == 300
    assert despues["level"] == "rx_plus" and despues["status"] == "validated"


async def _con_resultado_de(session: AsyncSession, e: Escena) -> tuple[Any, Any]:
    """Un resultado de OTRO socio y uno del mismo socio en OTRO WOD."""
    otro = (await make_members(session, 2))[1]
    ajeno = await registrar(session, e, member_id=otro.id, session_id=None, seconds=250)
    mov = await make_movement(session, e.coach, name="Mov otro dia", unit="kg")
    otro_wod = await make_wod(
        session, e.coach, [mov.id], date="2026-10-19", score_type="time", time_cap_s=600
    )
    de_otro_wod = await registrar(session, e, wod_id=otro_wod.id, session_id=None, seconds=200)
    return ajeno, de_otro_wod


async def test_409_invalid_supersedes_de_otro_socio_de_otro_wod_o_no_vigente(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    propio = await registrar(session, e, seconds=300)
    ajeno, de_otro_wod = await _con_resultado_de(session, e)

    for apunta in (ajeno.id, de_otro_wod.id, uuid4()):
        error = await _falla(registrar(session, e, seconds=290, supersedes_id=apunta))
        assert (error.status, error.code) == (409, "invalid_supersedes")
        assert error.field == "supersedes_id"
    # no vigente: tras corregir, el primero ya no lo es
    nuevo = await registrar(session, e, seconds=280, supersedes_id=propio.id)
    error = await _falla(registrar(session, e, seconds=270, supersedes_id=propio.id))
    assert (error.status, error.code) == (409, "invalid_supersedes")
    vigente = await session.scalar(
        text(
            "SELECT id FROM results.wod_results WHERE wod_id = :w AND member_id = :m AND is_current"
        ),
        {"w": e.wod_id, "m": e.socio_id},
    )
    assert vigente == nuevo.id


async def test_validacion_fallida_deja_el_anterior_vigente(session: AsyncSession) -> None:
    e = await escena(session)  # time con tope de 600 s
    uno = await registrar(session, e, seconds=300)
    error = await _falla(registrar(session, e, seconds=9_999, supersedes_id=uno.id))
    assert error.status == 422
    error = await _falla(registrar(session, e, seconds=None, supersedes_id=uno.id))
    assert error.status == 422
    assert (await _fila(session, uno.id))["is_current"] is True
    assert await session.scalar(text("SELECT count(*) FROM results.wod_results")) == 1


async def test_cadena_de_tres_correcciones(session: AsyncSession) -> None:
    e = await escena(session)
    a = await registrar(session, e, seconds=300)
    b = await registrar(session, e, seconds=290, supersedes_id=a.id)
    c = await registrar(session, e, seconds=280, supersedes_id=b.id)
    d = await registrar(session, e, seconds=270, supersedes_id=c.id)
    cadena = (
        await session.execute(
            text(
                "SELECT id, supersedes_id, is_current FROM results.wod_results "
                "WHERE wod_id = :w AND member_id = :m ORDER BY seconds DESC"
            ),
            {"w": e.wod_id, "m": e.socio_id},
        )
    ).all()
    assert [f.id for f in cadena] == [a.id, b.id, c.id, d.id]
    assert [f.supersedes_id for f in cadena] == [None, a.id, b.id, c.id]
    assert [f.is_current for f in cadena] == [False, False, False, True]
    for viejo in (a, b, c):  # cada eslabón apagado se corrige una sola vez
        error = await _falla(registrar(session, e, seconds=1, supersedes_id=viejo.id))
        assert error.code == "invalid_supersedes"
