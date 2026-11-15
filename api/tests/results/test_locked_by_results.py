"""Asistencia y sesión bloqueadas por resultados; corrección atada a su sesión (S8-B1d).

M-2 (S8-D46): con resultado vigente, quitar la asistencia de ese socio o cancelar la sesión da 409
`locked_by_results`. M-3: una corrección conserva la `session_id` del resultado que corrige.
Concurrencia real con dos conexiones: el registro se pausa con el candado del socio y la sesión
tomados, y se comprueba que quien quita o cancela ESPERA y luego recibe el 409.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import SessionCancel
from app.modules.wods import service as wods_service
from tests.factories.classes import make_attendance
from tests.factories.members import make_members
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def _asistencia_id(session: AsyncSession, e: Escena, member_id: UUID | None = None) -> UUID:
    fila = await session.scalar(
        text(
            "SELECT id FROM classes.attendance WHERE session_id = :s AND member_id = :m "
            "AND removed_at IS NULL"
        ),
        {"s": e.clase_id, "m": member_id or e.socio_id},
    )
    assert fila is not None
    return fila


async def _quitar(session: AsyncSession, e: Escena, attendance_id: UUID) -> None:
    with actor_scope(e.coach):
        await classes_service.remove_attendance(
            session, attendance_id, None, by=e.coach, role="admin"
        )


async def _cancelar(session: AsyncSession, e: Escena) -> None:
    assert e.clase_id is not None
    with actor_scope(e.coach):
        await classes_service.cancel_session(
            session, e.clase_id, SessionCancel(reason="Lluvia"), by=e.coach
        )


async def _falla(coro: Awaitable[Any]) -> DomainError:
    with pytest.raises(DomainError) as info:
        await coro
    return info.value


# M-2 · sin concurrencia ----------------------------------------------------------------------


async def test_quitar_la_asistencia_con_resultado_vigente_da_409(session: AsyncSession) -> None:
    e = await escena(session)
    await registrar(session, e)
    error = await _falla(_quitar(session, e, await _asistencia_id(session, e)))
    assert (error.status, error.code) == (409, "locked_by_results")
    vivas = await session.scalar(
        text("SELECT count(*) FROM classes.attendance WHERE removed_at IS NULL")
    )
    assert vivas == 1


async def test_quitar_la_asistencia_de_otro_socio_sin_resultado_pasa(session: AsyncSession) -> None:
    e = await escena(session)
    assert e.clase is not None
    otro = (await make_members(session, 2))[1]
    await make_attendance(session, e.clase, otro.id, membership_status_at_checkin="none")
    await registrar(session, e)  # el resultado es de OTRO socio
    await _quitar(session, e, await _asistencia_id(session, e, otro.id))
    vivas = await session.scalar(
        text("SELECT count(*) FROM classes.attendance WHERE removed_at IS NULL")
    )
    assert vivas == 1


async def test_cancelar_la_sesion_con_resultado_vigente_da_409(session: AsyncSession) -> None:
    e = await escena(session)
    await registrar(session, e)
    error = await _falla(_cancelar(session, e))
    assert (error.status, error.code) == (409, "locked_by_results")
    estado = await session.scalar(
        text("SELECT status FROM classes.class_sessions WHERE id = :s"), {"s": e.clase_id}
    )
    assert estado == "scheduled"


async def test_cancelar_una_sesion_sin_resultados_pasa(session: AsyncSession) -> None:
    e = await escena(session)
    await _cancelar(session, e)
    estado = await session.scalar(
        text("SELECT status FROM classes.class_sessions WHERE id = :s"), {"s": e.clase_id}
    )
    assert estado == "cancelled"


# M-3 · la corrección conserva su sesión ------------------------------------------------------


async def test_corregir_con_otra_sesion_o_sin_sesion_da_422_session_id(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    sin_sesion = await _falla(
        registrar(session, e, seconds=290, session_id=None, supersedes_id=uno.id)
    )
    assert (sin_sesion.status, sin_sesion.field) == (422, "session_id")
    vigente = await session.scalar(text("SELECT id FROM results.wod_results WHERE is_current"))
    assert vigente == uno.id
    propia = await registrar(session, e, seconds=280, supersedes_id=uno.id)
    assert propia.session_id == e.clase_id and propia.is_current


# M-2 · concurrencia --------------------------------------------------------------------------


class Pausa:
    """Detiene el PRIMER `scoring_for` (el registro ya tomó socio y sesión) hasta `seguir`."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.dentro = asyncio.Event()
        self.seguir = asyncio.Event()
        self._usada = False
        original = wods_service.scoring_for

        async def lento(*args: Any, **kwargs: Any) -> Any:
            if not self._usada:
                self._usada = True
                self.dentro.set()
                await self.seguir.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(wods_service, "scoring_for", lento)


async def _registrar_pausado(
    una: AsyncSession, e: Escena, pausa: Pausa, **cambios: Any
) -> asyncio.Task[Any]:
    async def correr() -> Any:
        try:
            salida = await registrar(una, e, **cambios)
            await una.commit()
            return salida
        except BaseException:
            await una.rollback()
            raise

    tarea = asyncio.create_task(correr())
    await asyncio.wait_for(pausa.dentro.wait(), timeout=15)
    return tarea


async def _otra_espera_y_falla(
    otra: AsyncSession,
    operacion: Callable[[AsyncSession], Awaitable[None]],
    pausa: Pausa,
    registro: asyncio.Task[Any],
) -> DomainError:
    async def correr() -> None:
        try:
            await operacion(otra)
        finally:
            await otra.rollback()

    contraria = asyncio.create_task(correr())
    await asyncio.sleep(0.5)
    assert not contraria.done(), "la operación contraria debe esperar al registro en vuelo"
    pausa.seguir.set()
    await asyncio.wait_for(registro, timeout=30)
    with pytest.raises(DomainError) as info:
        await asyncio.wait_for(contraria, timeout=30)
    return info.value


async def test_registrar_contra_quitar_asistencia_espera_y_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    una, otra = dos_sesiones
    e = await escena(una)
    asistencia = await _asistencia_id(una, e)
    pausa = Pausa(monkeypatch)
    registro = await _registrar_pausado(una, e, pausa)
    error = await _otra_espera_y_falla(otra, lambda s: _quitar(s, e, asistencia), pausa, registro)
    assert (error.status, error.code) == (409, "locked_by_results")
    vivas = await una.scalar(
        text("SELECT count(*) FROM classes.attendance WHERE removed_at IS NULL")
    )
    vigentes = await una.scalar(text("SELECT count(*) FROM results.wod_results WHERE is_current"))
    assert (vivas, vigentes) == (1, 1)


async def test_registrar_contra_cancelar_la_sesion_espera_y_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    una, otra = dos_sesiones
    e = await escena(una)
    pausa = Pausa(monkeypatch)
    registro = await _registrar_pausado(una, e, pausa)
    error = await _otra_espera_y_falla(otra, lambda s: _cancelar(s, e), pausa, registro)
    assert (error.status, error.code) == (409, "locked_by_results")
    estado = await una.scalar(
        text("SELECT status FROM classes.class_sessions WHERE id = :s"), {"s": e.clase_id}
    )
    assert estado == "scheduled"
