"""`record_result` (S8-B1, US-169; S8-D11, S8-D36, S8-D41; M-5, M-6, L-2, L-3). Con base real."""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import SessionCancel
from app.modules.members.exceptions import MemberNotFound
from app.modules.results import service
from app.modules.results.events import WodResultRecorded, WodResultValidated
from tests.conftest import CapturarEventos
from tests.factories.wods import make_movement, make_wod
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _falla(coro: Any) -> DomainError:
    with pytest.raises(DomainError) as info:
        await coro
    return info.value


async def test_201_validated_con_recorded_y_validated_by(session: AsyncSession) -> None:
    e = await escena(session)
    assert e.clase is not None
    salida = await registrar(session, e)
    assert (salida.status, salida.is_current, salida.source) == ("validated", True, "desk")
    assert salida.recorded_by == e.coach and salida.validated_by == e.coach
    assert salida.validated_at is not None and salida.seconds == 300
    assert salida.wod_date.isoformat() == "2026-10-21" and salida.session_id == e.clase.id


async def test_source_desk_por_defecto(session: AsyncSession) -> None:
    e = await escena(session)
    fila = await registrar(session, e)
    guardado = await session.scalar(
        text("SELECT source FROM results.wod_results WHERE id = :i"), {"i": fila.id}
    )
    assert guardado == "desk"


async def test_409_result_exists_con_existing_id(session: AsyncSession) -> None:
    e = await escena(session)
    primero = await registrar(session, e)
    error = await _falla(registrar(session, e, seconds=200))
    assert (error.status, error.code, error.existing_id) == (409, "result_exists", primero.id)


async def test_asistencia_viva_exigida(session: AsyncSession) -> None:
    e = await escena(session, asistencia=False)
    error = await _falla(registrar(session, e))
    assert (error.status, error.field) == (422, "session_id")


async def test_wod_efectivo_distinto_422_session_id(session: AsyncSession) -> None:
    e = await escena(session)
    otro_mov = await make_movement(session, e.coach, name="Otro mov", unit="kg")
    otro = await make_wod(session, e.coach, [otro_mov.id], date="2026-10-20", title="Ayer")
    error = await _falla(registrar(session, e, wod_id=otro.id))
    assert (error.status, error.field) == (422, "session_id")


async def test_sesion_cancelada_con_asistencia_409_session_cancelled(
    session: AsyncSession,
) -> None:
    """M-6: cancelar no quita asistencias, pero la sesión cancelada no admite resultados."""
    e = await escena(session)
    assert e.clase is not None
    with actor_scope(e.coach):
        await classes_service.cancel_session(
            session, e.clase.id, SessionCancel.model_validate({"reason": "Lluvia"}), by=e.coach
        )
    vivas = await session.scalar(
        text(
            "SELECT count(*) FROM classes.attendance WHERE session_id = :s AND removed_at IS NULL"
        ),
        {"s": e.clase.id},
    )
    assert vivas == 1
    error = await _falla(registrar(session, e))
    assert (error.status, error.code) == (409, "session_cancelled")


async def test_wod_futuro_sin_sesion_422_wod_id(session: AsyncSession) -> None:
    """L-3: sin `session_id`, un WOD de fecha futura no admite marca."""
    e = await escena(session, fecha="2026-10-25", con_clase=False)
    error = await _falla(registrar(session, e))
    assert (error.status, error.field) == (422, "wod_id")
    ayer = await escena(session, fecha="2026-10-20", con_clase=False)
    assert (await registrar(session, ayer)).wod_date.isoformat() == "2026-10-20"


async def test_baja_entre_ensure_y_lock_da_404(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-3: la baja entre el primer `ensure_exists` y el candado la ve el segundo."""
    from app.modules.members import service as members_service

    e = await escena(session)
    original = members_service.ensure_exists
    llamadas: list[int] = []

    async def con_baja(sesion: AsyncSession, member_id: UUID, **kw: Any) -> None:
        await original(sesion, member_id, **kw)
        llamadas.append(1)
        if len(llamadas) == 1:
            await sesion.execute(
                text("UPDATE members.members SET deleted_at = now() WHERE id = :i"),
                {"i": member_id},
            )

    monkeypatch.setattr(members_service, "ensure_exists", con_baja)
    with pytest.raises(MemberNotFound):
        await registrar(session, e)
    assert len(llamadas) == 1  # la segunda llamada levantó MemberNotFound antes de anotar


async def test_wod_not_scored(session: AsyncSession) -> None:
    e = await escena(session, score_type="none", time_cap_s=None)
    error = await _falla(registrar(session, e, seconds=None))
    assert (error.status, error.code) == (422, "wod_not_scored")


async def test_scaled_movement_ids_subconjunto_del_wod_y_solo_con_scaled(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    ok = await registrar(session, e, level="scaled", scaled_movement_ids=[e.movimientos[0]])
    assert ok.scaled_movement_ids == [e.movimientos[0]]
    otro = await escena(session, fecha="2026-10-20", con_clase=False)
    ajeno = await _falla(
        registrar(session, otro, level="scaled", scaled_movement_ids=[e.movimientos[0]])
    )
    assert (ajeno.status, ajeno.field) == (422, "scaled_movement_ids")
    con_rx = await _falla(
        registrar(session, otro, level="rx", scaled_movement_ids=[otro.movimientos[0]])
    )
    assert con_rx.field == "scaled_movement_ids"


async def test_eventos_sin_pii(session: AsyncSession, capturar_eventos: CapturarEventos) -> None:
    e = await escena(session)
    recibidos = capturar_eventos(WodResultRecorded, WodResultValidated)
    salida = await registrar(session, e, level="scaled", seconds=250)
    assert {type(x).__name__ for x in recibidos} == {"WodResultRecorded", "WodResultValidated"}
    registrado = next(x for x in recibidos if isinstance(x, WodResultRecorded))
    assert registrado.result_id == salida.id
    assert registrado.primary_movement_id == e.movimientos[0]
    assert {f.name for f in dataclasses.fields(registrado)} <= {
        "result_id", "member_id", "wod_id", "level", "load_g", "primary_movement_id",
        "occurred_at",
    }  # fmt: skip


async def test_suscriptor_que_falla_revierte_el_resultado(session: AsyncSession) -> None:
    async def malo(_e: Any, _s: AsyncSession) -> None:
        raise RuntimeError("falla")

    e = await escena(session)
    events.subscribe(WodResultValidated, malo)
    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await registrar(session, e)
    n = await session.scalar(text("SELECT count(*) FROM results.wod_results"))
    assert n == 0


async def test_load_g_entero_y_auditoria_sin_canonical_error(session: AsyncSession) -> None:
    e = await escena(session, score_type="load", time_cap_s=None)
    salida = await registrar(session, e, seconds=None, load_g=102_500)
    assert salida.load_g == 102_500
    filas = await session.execute(
        text(
            "SELECT action, after->>'load_g', subject_member_id::text FROM audit.audit_log "
            "WHERE table_name = 'results.wod_results' AND record_id = :i"
        ),
        {"i": salida.id},
    )
    assert [tuple(f) for f in filas.all()] == [("insert", "102500", str(e.socio_id))]


async def test_socio_inexistente_404(session: AsyncSession) -> None:
    e = await escena(session)
    with pytest.raises(MemberNotFound):
        await registrar(session, e, member_id=uuid4())


async def test_corregir_apaga_el_anterior_y_encadena(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    dos = await registrar(session, e, seconds=280, supersedes_id=uno.id)
    assert dos.supersedes_id == uno.id and dos.is_current
    vigentes = await session.scalar(
        text("SELECT count(*) FROM results.wod_results WHERE is_current")
    )
    assert vigentes == 1
    de_otro = await _falla(registrar(session, e, seconds=270, supersedes_id=uno.id))
    assert (de_otro.status, de_otro.code) == (409, "invalid_supersedes")


async def test_el_puerto_de_wods_cuenta_los_vigentes(session: AsyncSession) -> None:
    e = await escena(session)
    assert await service.results_probe.result_counts(session, [e.wod_id]) == {}
    await registrar(session, e)
    assert await service.results_probe.result_counts(session, [e.wod_id]) == {e.wod_id: 1}
