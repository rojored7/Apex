"""`PATCH /class-sessions/{id}` con `wod_id` (S8-A4, US-168 CA3 a CA6; S8-D9, S8-D36)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.classes import service
from app.modules.classes.schemas import SessionCancel, SessionPatch
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session
from tests.factories.wods import make_movement, make_wod

SESIONES = "/api/v1/class-sessions"

pytestmark = pytest.mark.usefixtures("reloj")


async def _wod(session: AsyncSession, actor: UUID, fecha: str, titulo: str = "Fran") -> UUID:
    mov = await make_movement(session, actor, name=f"Mov {titulo} {fecha}")
    return (await make_wod(session, actor, [mov.id], date=fecha, title=titulo)).id


async def _auditoria(session: AsyncSession, sid: UUID) -> list[tuple[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT action, after->>'wod_id' FROM audit.audit_log "
            "WHERE table_name = 'classes.class_sessions' AND record_id = :i ORDER BY seq"
        ),
        {"i": sid},
    )
    return [(a, w) for a, w in filas.all()]


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_asignar_y_auditar(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    usuario = await usuario_real(rol)
    wod = await _wod(session, usuario.id, "2026-10-22")
    sesion = await make_session(session)
    r = await app_http.patch(
        f"{SESIONES}/{sesion.id}", json={"wod_id": str(wod)}, headers=cabeceras(usuario)
    )
    assert r.status_code == 200, r.text
    assert r.json()["wod_id"] == str(wod) and r.json()["effective_wod_id"] == str(wod)
    assert r.headers["cache-control"] == "no-store"
    auditoria = await _auditoria(session, sesion.id)
    assert [a for a, _ in auditoria] == ["insert", "update"]
    assert auditoria[1][1] == str(wod)


async def test_null_vuelve_a_heredar(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    asignado = await _wod(session, admin.id, "2026-10-23", "Otro")
    del_dia = await _wod(session, admin.id, "2026-10-22", "Del dia")
    sesion = await make_session(session)  # jueves 22 06:00 Bogotá
    url = f"{SESIONES}/{sesion.id}"
    uno = await app_http.patch(url, json={"wod_id": str(asignado)}, headers=h)
    assert uno.json()["effective_wod_id"] == str(asignado)
    dos = await app_http.patch(url, json={"wod_id": None}, headers=h)
    assert dos.status_code == 200
    assert dos.json()["wod_id"] is None and dos.json()["effective_wod_id"] == str(del_dia)
    otra_vez = await app_http.patch(url, json={"wod_id": None}, headers=h)
    assert otra_vez.status_code == 200  # sin cambio: no hay fila de auditoría extra
    acciones = [a for a, _ in await _auditoria(session, sesion.id)]
    assert acciones == ["insert", "update", "update"]


async def test_wod_inexistente_422_wod_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    sesion = await make_session(session)
    h = cabeceras(await usuario_real("coach"))
    r = await app_http.patch(f"{SESIONES}/{sesion.id}", json={"wod_id": str(uuid4())}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["field"] == "wod_id"
    inexistente = await app_http.patch(f"{SESIONES}/{uuid4()}", json={"wod_id": None}, headers=h)
    assert inexistente.status_code == 404


async def test_sesion_cancelada_409_session_cancelled(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    wod = await _wod(session, admin.id, "2026-10-22")
    sesion = await make_session(session)
    with actor_scope(admin.id):
        await service.cancel_session(
            session, sesion.id, SessionCancel.model_validate({"reason": "Lluvia"}), by=admin.id
        )
        await session.commit()
    r = await app_http.patch(
        f"{SESIONES}/{sesion.id}", json={"wod_id": str(wod)}, headers=cabeceras(admin)
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_cancelled"


async def test_extra_forbid_y_cuerpo_sin_wod_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    sid = (await make_session(session)).id  # tras un 422 la sesión de prueba expira sus filas
    h = cabeceras(await usuario_real("admin"))
    for cuerpo in ({"wod_id": None, "capacity": 3}, {"name": "x"}, {}):
        r = await app_http.patch(f"{SESIONES}/{sid}", json=cuerpo, headers=h)
        assert r.status_code == 422, cuerpo
    fila = await session.execute(
        text("SELECT capacity FROM classes.class_sessions WHERE id = :i"), {"i": sid}
    )
    assert fila.scalar_one() == 15


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    sesion = await make_session(session)
    h = cabeceras(await usuario_real("member"))
    url = f"{SESIONES}/{sesion.id}"
    assert (await app_http.patch(url, json={"wod_id": None}, headers=h)).status_code == 403
    assert (await app_http.patch(url, json={"wod_id": None})).status_code == 401


async def test_toma_for_update_de_la_sesion_antes_de_leer_el_wod(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """S8-D36 (M-6): la sesión `FOR UPDATE` va ANTES de la lectura del WOD y del `UPDATE`."""
    admin = await usuario_real("admin")
    wod = await _wod(session, admin.id, "2026-10-22")
    sesion = await make_session(session)
    vistas: list[str] = []
    motor = session.get_bind()

    def anotar(_c: Any, _cur: Any, sentencia: str, *_: Any) -> None:
        vistas.append(sentencia)

    event.listen(motor, "before_cursor_execute", anotar)
    try:
        with actor_scope(admin.id):
            await service.assign_wod(
                session, sesion.id, SessionPatch.model_validate({"wod_id": wod}), by=admin.id
            )
    finally:
        event.remove(motor, "before_cursor_execute", anotar)
    sesion_i = next(i for i, s in enumerate(vistas) if "FOR UPDATE" in s and "class_sessions" in s)
    wod_i = next(i for i, s in enumerate(vistas) if "wods.wods" in s)
    update_i = next(
        i for i, s in enumerate(vistas) if s.startswith("UPDATE classes.class_sessions")
    )
    assert sesion_i < wod_i < update_i
