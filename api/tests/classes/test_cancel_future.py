"""`classes.service.cancel_future_sessions` con base real (S7-B3, US-158; S7-D26, M-1). Rojo B3.

Reloj `T0`: miércoles 21 de octubre de 2026, 10:00 en Bogotá (15:00Z). La franja de fábrica es
lunes y miércoles a las 06:00: el miércoles 21 ya pasó; quedan el lunes 26, el miércoles 28 y el
lunes 2 (tres sesiones futuras al generar 14 días).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.classes import service
from app.modules.classes.exceptions import SlotNotFound
from app.modules.classes.schemas import SessionCancel
from app.modules.classes.sessions import GENERATE_SESSIONS_LOCK_KEY
from tests.conftest import CrearUsuario
from tests.factories.classes import make_session, make_slot
from tests.factories.users import make_user

HOY = date(2026, 10, 21)
PASADA = datetime(2026, 10, 21, 11, 0, tzinfo=UTC)  # hoy 06:00 Bogotá, ya empezó

pytestmark = pytest.mark.usefixtures("reloj")


def _motivo(texto: str = "Cierre por festivo") -> SessionCancel:
    return SessionCancel.model_validate({"reason": texto})


async def _cancelar(session: AsyncSession, actor: UUID, slot_id: UUID) -> Any:
    with actor_scope(actor):
        salida = await service.cancel_future_sessions(session, slot_id, _motivo(), by=actor)
        await session.commit()
    return salida


async def _estados(session: AsyncSession) -> dict[datetime, str]:
    filas = await session.execute(
        text("SELECT starts_at, status FROM classes.class_sessions ORDER BY starts_at")
    )
    return {inicio: estado for inicio, estado in filas.all()}


async def test_pasadas_canceladas_y_extras_intactas(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    otra = await make_slot(session, name="Otra")
    pasada = await make_session(session, slot_id=franja.id, starts_at=PASADA)
    # S7-B3b (LOW 2): en curso (09:30 Bogotá, 60 min, reloj 10:00): ya empezó, sigue `scheduled`.
    en_curso = await make_session(
        session, slot_id=franja.id, starts_at=datetime(2026, 10, 21, 14, 30, tzinfo=UTC)
    )
    ya_cancelada = await make_session(
        session,
        slot_id=franja.id,
        starts_at=datetime(2026, 10, 27, 11, 0, tzinfo=UTC),
        status="cancelled",
        cancel_reason="Antes",
        cancelled_by=SYSTEM_USER_ID,
        cancelled_at=PASADA,
    )
    extra = await make_session(session, starts_at=datetime(2026, 10, 28, 11, 0, tzinfo=UTC))
    de_otra = await make_session(
        session, slot_id=otra.id, starts_at=datetime(2026, 10, 29, 11, 0, tzinfo=UTC)
    )
    futuras = [
        await make_session(
            session, slot_id=franja.id, starts_at=datetime(2026, 10, d, 12, 0, tzinfo=UTC)
        )
        for d in (30, 31)
    ]
    salida = await _cancelar(session, admin.id, franja.id)
    assert salida.cancelled_count == 2
    estados = await _estados(session)
    assert estados[pasada.starts_at] == "scheduled"
    assert estados[en_curso.starts_at] == "scheduled"
    assert estados[extra.starts_at] == "scheduled" and estados[de_otra.starts_at] == "scheduled"
    assert estados[ya_cancelada.starts_at] == "cancelled"
    assert all(estados[f.starts_at] == "cancelled" for f in futuras)
    fila = (
        await session.execute(
            text(
                "SELECT cancel_reason, cancelled_by, cancelled_at FROM classes.class_sessions "
                "WHERE id = :i"
            ),
            {"i": futuras[0].id},
        )
    ).one()
    assert fila.cancel_reason == "Cierre por festivo" and fila.cancelled_by == admin.id
    assert fila.cancelled_at is not None
    auditoria = await session.scalar(
        text(
            "SELECT count(*) FROM audit.audit_log WHERE table_name = 'classes.class_sessions' "
            "AND action = 'update' AND user_id = :u"
        ),
        {"u": admin.id},
    )
    assert auditoria == 2


async def test_un_evento_por_sesion_sin_el_motivo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    creadas = [
        await make_session(
            session, slot_id=franja.id, starts_at=datetime(2026, 10, d, 11, 0, tzinfo=UTC)
        )
        for d in (26, 28)
    ]
    vistos: list[service.SessionCancelled] = []

    async def anotar(evento: service.SessionCancelled, _: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(service.SessionCancelled, anotar)  # `restaurar_bus` lo quita
    await _cancelar(session, admin.id, franja.id)
    assert [(e.session_id, e.slot_id) for e in vistos] == [(c.id, franja.id) for c in creadas]
    assert "festivo" not in repr(vistos)


async def test_sin_futuras_200_con_0(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    await make_session(session, slot_id=franja.id, starts_at=PASADA)
    salida = await _cancelar(session, admin.id, franja.id)
    assert salida.cancelled_count == 0
    assert set((await _estados(session)).values()) == {"scheduled"}


async def test_franja_inexistente_404(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    with actor_scope(admin.id), pytest.raises(SlotNotFound):
        await service.cancel_future_sessions(
            session, UUID("00000000-0000-0000-0000-0000000000aa"), _motivo(), by=admin.id
        )


async def test_fallo_a_mitad_revierte_todo(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    sesion, _ = dos_sesiones
    admin = await make_user(sesion, role="admin")
    franja = await make_slot(sesion)
    with actor_scope(SYSTEM_USER_ID):
        await service.generate_sessions(sesion, today=HOY, slot_ids=[franja.id])
        await sesion.commit()
    antes = await _estados(sesion)
    assert len(antes) == 3 and set(antes.values()) == {"scheduled"}
    vistos = 0

    async def fallar_en_la_segunda(_: service.SessionCancelled, __: AsyncSession) -> None:
        nonlocal vistos
        vistos += 1
        if vistos == 2:
            raise RuntimeError("falla a mitad")

    events.subscribe(service.SessionCancelled, fallar_en_la_segunda)
    with actor_scope(admin.id), pytest.raises(RuntimeError, match="a mitad"):
        await service.cancel_future_sessions(sesion, franja.id, _motivo(), by=admin.id)
    await sesion.rollback()
    assert await _estados(sesion) == antes


async def test_toma_el_candado_de_generacion_antes_de_bloquear(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """El candado 4_270_006 va primero; luego un único `SELECT ... FOR UPDATE ORDER BY`; recién
    después el primer `UPDATE` (flush auditado)."""
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    for dia in (26, 28):
        await make_session(
            session, slot_id=franja.id, starts_at=datetime(2026, 10, dia, 11, 0, tzinfo=UTC)
        )
    vistas: list[str] = []
    motor = session.get_bind()  # la conexión síncrona del savepoint

    def anotar(_c: Any, _cur: Any, sentencia: str, *_: Any) -> None:
        vistas.append(sentencia)

    event.listen(motor, "before_cursor_execute", anotar)
    try:
        await _cancelar(session, admin.id, franja.id)
    finally:
        event.remove(motor, "before_cursor_execute", anotar)
    candado = [i for i, s in enumerate(vistas) if "pg_advisory_xact_lock" in s]
    bloqueos = [i for i, s in enumerate(vistas) if "FOR UPDATE" in s and "class_sessions" in s]
    cambios = [i for i, s in enumerate(vistas) if s.startswith("UPDATE classes.class_sessions")]
    assert candado and len(bloqueos) == 1 and cambios
    assert candado[0] < bloqueos[0] < cambios[0]
    assert (
        "ORDER BY classes.class_sessions.starts_at, classes.class_sessions.id"
        in vistas[bloqueos[0]]
    )


async def test_concurrente_con_generate_sessions_sin_quedar_scheduled(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """El job toma 006 y duerme; la cancelación espera ese candado y, al liberarse, ve las sesiones
    que el job creó y las cancela: nada queda `scheduled` y no hay interbloqueo (40P01)."""
    del_job, de_la_cancelacion = dos_sesiones
    admin = await make_user(de_la_cancelacion, role="admin")
    franja = await make_slot(del_job, weekdays=[0])

    async def job() -> int:
        with actor_scope(SYSTEM_USER_ID):
            await del_job.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": GENERATE_SESSIONS_LOCK_KEY}
            )
            await asyncio.sleep(1.5)
            resultado = await service.generate_sessions(del_job, today=HOY)
            await del_job.commit()
        return resultado.created

    async def cancelar() -> int:
        await asyncio.sleep(0.3)
        with actor_scope(admin.id):
            salida = await service.cancel_future_sessions(
                de_la_cancelacion, franja.id, _motivo(), by=admin.id
            )
            await de_la_cancelacion.commit()
        return salida.cancelled_count

    creadas, canceladas = await asyncio.wait_for(asyncio.gather(job(), cancelar()), timeout=30)
    assert creadas == 2 and canceladas == 2
    assert set((await _estados(del_job)).values()) == {"cancelled"}
