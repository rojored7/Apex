"""Correcciones de la revisión de A4 (S8-A4b): ventana del filtro `wod_id`, auditoría del actor,
sesión terminada, quiosco y la carrera entre cancelar y asignar (L-1, L-3, L-4)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.errors import DomainError
from app.core.security import create_access_token
from app.modules.classes import service
from app.modules.classes.exceptions import SessionCancelledError
from app.modules.classes.schemas import SessionCancel, SessionPatch
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

SESIONES = "/api/v1/class-sessions"
DICIEMBRE = datetime(2026, 12, 1, 15, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj")


async def _wod(session: AsyncSession, actor: UUID, fecha: str, titulo: str = "Fran") -> UUID:
    mov = await make_movement(session, actor, name=f"Mov a4b {titulo} {fecha}")
    return (await make_wod(session, actor, [mov.id], date=fecha, title=titulo)).id


async def test_filtro_wod_id_sin_ventana_usa_la_fecha_del_wod(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """L-1: sin `week`, `from` ni `to`, el filtro por WOD no se limita a la semana actual."""
    admin = await usuario_real("admin")
    wod = await _wod(session, admin.id, "2026-12-01", "Diciembre")
    hereda = await make_session(session, starts_at=DICIEMBRE)
    ajena = await make_session(session, starts_at=datetime(2026, 12, 2, 15, 0, tzinfo=UTC))
    r = await app_http.get(SESIONES, params={"wod_id": str(wod)}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert {i["id"] for i in r.json()["items"]} == {str(hereda.id)}
    assert str(ajena.id) not in {i["id"] for i in r.json()["items"]}


async def test_la_auditoria_lleva_al_actor_y_el_log_tambien(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L-3 y L-4: el `update` queda a nombre de quien asignó; el log trae `actor`."""
    coach = await usuario_real("coach")
    wod = await _wod(session, coach.id, "2026-10-22")
    sesion = await make_session(session)
    with caplog.at_level(logging.INFO, logger="app.classes"):
        r = await app_http.patch(
            f"{SESIONES}/{sesion.id}", json={"wod_id": str(wod)}, headers=cabeceras(coach)
        )
    assert r.status_code == 200
    filas = await session.execute(
        text(
            "SELECT action, user_id::text FROM audit.audit_log "
            "WHERE table_name = 'classes.class_sessions' AND record_id = :i ORDER BY seq"
        ),
        {"i": sesion.id},
    )
    assert [tuple(f) for f in filas.all()][-1] == ("update", str(coach.id))
    registros = [x for x in caplog.records if x.getMessage().startswith("classes: wod de la sesi")]
    assert registros and getattr(registros[-1], "actor", None) == str(coach.id)


async def test_asignar_en_una_sesion_terminada_da_200(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """L-4: una sesión `done` (terminó antes de `reloj`) admite asignar un WOD (S8-D9)."""
    admin = await usuario_real("admin")
    wod = await _wod(session, admin.id, "2026-10-20", "Ayer")
    pasada = await make_session(session, starts_at=datetime(2026, 10, 20, 11, 0, tzinfo=UTC))
    r = await app_http.patch(
        f"{SESIONES}/{pasada.id}", json={"wod_id": str(wod)}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done" and r.json()["wod_id"] == str(wod)


async def test_el_quiosco_no_puede_asignar_wod_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    """L-4: `PATCH /class-sessions/{id}` no está en la lista blanca del quiosco."""
    coach = await usuario_real("coach")
    sesion = await make_session(session)
    token = create_access_token(coach.id, "coach", None, reloj, kiosk=True)  # type: ignore[arg-type]
    r = await app_http.patch(
        f"{SESIONES}/{sesion.id}",
        json={"wod_id": None},
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGEN},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode"


async def test_cancelar_y_asignar_a_la_vez_el_segundo_recibe_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """L-4: la cancelación y la asignación piden la sesión `FOR UPDATE`; quien llega segundo ve el
    estado confirmado por el primero (`populate_existing`) y responde 409 `session_cancelled`."""
    una, otra = dos_sesiones
    admin = await make_user(una, role="admin")
    wod = await _wod(una, admin.id, "2026-10-22")
    sesion = await make_session(una)
    with actor_scope(admin.id):
        datos = SessionCancel.model_validate({"reason": "Lluvia"})
        await service.cancel_session(una, sesion.id, datos, by=admin.id)  # sin confirmar

        async def asignar() -> object:
            try:
                return await service.assign_wod(
                    otra, sesion.id, SessionPatch.model_validate({"wod_id": wod}), by=admin.id
                )
            finally:
                await otra.rollback()

        tarea = asyncio.create_task(asignar())
        await asyncio.sleep(0.5)
        assert not tarea.done(), "la asignación debe esperar al FOR UPDATE de la cancelación"
        await una.commit()
        with pytest.raises(DomainError) as info:
            await asyncio.wait_for(tarea, timeout=30)
    assert isinstance(info.value, SessionCancelledError) and info.value.status == 409
