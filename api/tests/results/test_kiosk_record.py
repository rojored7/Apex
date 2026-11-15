"""`PUT /results` con la marca del quiosco (S8-B3; S8-D15, S8-D31, M-1). Base real, por HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from tests.auth._sesion import ORIGEN
from tests.conftest import CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

RESULTADOS = "/api/v1/results"


async def _quiosco(usuario_real: CrearUsuario, reloj: FrozenClock) -> dict[str, str]:
    coach = await usuario_real("coach")
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    return {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}


def _json(e: Escena, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "wod_id": str(e.wod_id),
        "member_id": str(e.socio_id),
        "session_id": str(e.clase_id),
        "level": "rx",
        "seconds": 300,
    }
    valores.update(cambios)
    return {k: v for k, v in valores.items() if v is not None}


async def _poner(http: AsyncClient, cab: dict[str, str], e: Escena, **cambios: Any) -> Response:
    return await http.put(RESULTADOS, json=_json(e, **cambios), headers=cab)


async def test_session_id_obligatorio_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    e = await escena(session)
    cab = await _quiosco(usuario_real, reloj)
    r = await _poner(app_http, cab, e, session_id=None)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "session_id"
    assert await session.scalar(text("SELECT count(*) FROM results.wod_results")) == 0


@pytest.mark.parametrize(("dia", "permitida"), [(21, True), (20, True), (19, False), (22, False)])
async def test_ventana_hoy_o_ayer(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
    dia: int,
    permitida: bool,
) -> None:
    e = await escena(session, con_clase=False, fecha=f"2026-10-{dia}")
    clase = await make_session(session, starts_at=datetime(2026, 10, dia, 15, 0, tzinfo=UTC))
    socio_id = e.socio_id
    await make_attendance(session, clase, socio_id)
    cab = await _quiosco(usuario_real, reloj)
    r = await _poner(app_http, cab, e, session_id=str(clase.id))
    if permitida:
        assert r.status_code == 201, r.text
    else:
        assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
        assert await session.scalar(text("SELECT count(*) FROM results.wod_results")) == 0


async def test_source_kiosk_y_detalle_kiosk_en_la_auditoria(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    """La auditoría guarda la fila completa: `after.source = kiosk` es el detalle del origen."""
    e = await escena(session)
    cab = await _quiosco(usuario_real, reloj)
    r = await _poner(app_http, cab, e)
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "kiosk"
    origen = await session.scalar(
        text(
            "SELECT after->>'source' FROM audit.audit_log "
            "WHERE table_name = 'results.wod_results' AND record_id = :i AND action = 'insert'"
        ),
        {"i": UUID(r.json()["id"])},
    )
    assert origen == "kiosk"


async def test_corregir_resultado_de_escritorio_403_kiosk_mode(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    e = await escena(session)
    de_mesa = await registrar(session, e, source="desk")
    cab = await _quiosco(usuario_real, reloj)
    r = await _poner(app_http, cab, e, seconds=250, supersedes_id=str(de_mesa.id))
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
    vigente = await session.scalar(text("SELECT id FROM results.wod_results WHERE is_current"))
    assert vigente == de_mesa.id


async def test_corregir_resultado_de_otra_sesion_403_kiosk_mode(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    e = await escena(session)
    otra = await make_session(
        session, starts_at=datetime(2026, 10, 21, 17, 0, tzinfo=UTC), wod_id=e.wod_id
    )
    await make_attendance(session, otra, e.socio_id)
    de_la_primera = await registrar(session, e, source="kiosk")  # sesión de `e`, en tablet
    cab = await _quiosco(usuario_real, reloj)
    r = await _poner(
        app_http, cab, e, session_id=str(otra.id), seconds=250, supersedes_id=str(de_la_primera.id)
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text


async def test_corregir_el_propio_de_la_misma_sesion_pasa(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    e = await escena(session)
    cab = await _quiosco(usuario_real, reloj)
    uno = await _poner(app_http, cab, e)
    assert uno.status_code == 201, uno.text
    dos = await _poner(app_http, cab, e, seconds=250, supersedes_id=uno.json()["id"])
    assert dos.status_code == 201, dos.text
    assert dos.json()["source"] == "kiosk" and dos.json()["supersedes_id"] == uno.json()["id"]


async def test_asistencia_en_quiosco_solo_de_hoy_o_ayer(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    """L-2 (revisión de B3): `GET /class-sessions/{id}/attendance` con la marca de quiosco da
    200 para una clase de hoy y 403 `kiosk_mode` para una de anteayer."""
    e = await escena(session)
    anteayer = await make_session(session, starts_at=datetime(2026, 10, 19, 15, 0, tzinfo=UTC))
    cab = await _quiosco(usuario_real, reloj)
    de_hoy = await app_http.get(f"/api/v1/class-sessions/{e.clase_id}/attendance", headers=cab)
    assert de_hoy.status_code == 200, de_hoy.text
    vieja = await app_http.get(f"/api/v1/class-sessions/{anteayer.id}/attendance", headers=cab)
    assert vieja.status_code == 403 and vieja.json()["error"]["code"] == "kiosk_mode", vieja.text
