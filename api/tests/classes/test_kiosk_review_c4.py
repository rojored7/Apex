"""Correcciones de la revisión de C4 en asistencias y socios (S7-C4b; S7-D41). Rojo C4b.

- M-2: con la marca de quiosco la regla del coach (hoy o ayer) se aplica SIEMPRE, también a un
  admin que abrió el quiosco.
- M-3: `q` de las dos rutas de asistencias consume `PII_SEARCH_BUCKET`; la lista general nunca
  incluye bajas (solo la ficha del socio); con la marca, `GET /attendance` exige `session_id` y
  `GET /members` exige `q` y rechaza los filtros de estado, plan, consentimiento y última
  asistencia (422 con `field`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.ratelimit import PII_SEARCH_BUCKET, USER_LIMITS, usage
from app.core.security import create_access_token
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.notifications._apoyo_avisos import ANTES, socio

ASISTENCIAS = "/api/v1/attendance"
SOCIOS = "/api/v1/members"
HOY = datetime(2026, 10, 21, 11, 0, tzinfo=UTC)
HACE_3_DIAS = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _quiosco(user: Any, rol: str, reloj: FrozenClock) -> dict[str, str]:
    token = create_access_token(user.id, rol, None, reloj, kiosk=True)  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {token}", "Origin": ORIGEN}


async def _asistencia(session: AsyncSession, cuando: datetime, **cambios: Any) -> Any:
    clase = await make_session(session, starts_at=cuando)
    miembro = await socio(session)
    fila = await make_attendance(
        session, clase, miembro.id, membership_status_at_checkin="none", **cambios
    )
    return clase, miembro, fila


# M-2 · el quiosco aplica la regla del coach -----------------------------------------------------


async def test_un_admin_en_quiosco_no_quita_una_asistencia_de_hace_tres_dias(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    _, _, vieja = await _asistencia(session, HACE_3_DIAS)
    r = await app_http.delete(f"{ASISTENCIAS}/{vieja.id}", headers=_quiosco(admin, "admin", reloj))
    assert r.status_code == 403 and r.json()["error"]["code"] == "attendance_locked", r.text


async def test_un_admin_en_quiosco_si_quita_una_de_hoy_y_sin_quiosco_quita_la_vieja(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    _, _, de_hoy = await _asistencia(session, HOY)
    _, _, vieja = await _asistencia(session, HACE_3_DIAS)
    quiosco = _quiosco(admin, "admin", reloj)
    assert (await app_http.delete(f"{ASISTENCIAS}/{de_hoy.id}", headers=quiosco)).status_code == 204
    normal = await app_http.delete(f"{ASISTENCIAS}/{vieja.id}", headers=cabeceras(admin))
    assert normal.status_code == 204, normal.text


# M-3 · búsquedas acotadas ---------------------------------------------------------------------


async def _uso_pii(user: Any) -> int:
    ventana = USER_LIMITS[PII_SEARCH_BUCKET][1]
    return await usage(PII_SEARCH_BUCKET, str(user.id), window_s=ventana)


async def test_q_de_las_dos_rutas_de_asistencias_consume_la_cubeta_de_busquedas(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    coach = await usuario_real("coach")
    _, miembro, _ = await _asistencia(session, HOY)
    antes = await _uso_pii(coach)
    r = await app_http.get(f"{ASISTENCIAS}?q=Lucia", headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert await _uso_pii(coach) == antes + 1
    r = await app_http.get(f"{SOCIOS}/{miembro.id}/attendance?q=Lucia", headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert await _uso_pii(coach) == antes + 2
    await app_http.get(ASISTENCIAS, headers=cabeceras(coach))  # sin `q` no cuenta
    await app_http.get(f"{SOCIOS}/{miembro.id}/attendance", headers=cabeceras(coach))
    assert await _uso_pii(coach) == antes + 2


async def test_la_lista_general_no_incluye_bajas_aunque_se_pida_member_id_y_la_ficha_si(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    clase = await make_session(session, starts_at=HOY)
    baja = await socio(session, nombre="Zoila", apellido="Baja", deleted_at=ANTES)
    await make_attendance(session, clase, baja.id, membership_status_at_checkin="none")
    general = await app_http.get(
        f"{ASISTENCIAS}?member_id={baja.id}&q=Zoila", headers=cabeceras(admin)
    )
    assert general.status_code == 200 and general.json()["items"] == [], general.text
    ficha = await app_http.get(f"{SOCIOS}/{baja.id}/attendance?q=Zoila", headers=cabeceras(admin))
    assert ficha.status_code == 200 and len(ficha.json()["items"]) == 1, ficha.text


async def test_en_quiosco_la_lista_de_asistencias_exige_session_id(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    clase, _, _ = await _asistencia(session, HOY)
    clase_id = clase.id  # tras el 422 la sesión se revierte: no leer atributos expirados
    quiosco = _quiosco(coach, "coach", reloj)
    r = await app_http.get(ASISTENCIAS, headers=quiosco)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "session_id"
    ok = await app_http.get(f"{ASISTENCIAS}?session_id={clase_id}", headers=quiosco)
    assert ok.status_code == 200 and len(ok.json()["items"]) == 1, ok.text
    sin_quiosco = await app_http.get(ASISTENCIAS, headers=cabeceras(coach))
    assert sin_quiosco.status_code == 200  # fuera del quiosco no cambia


@pytest.mark.parametrize(
    ("consulta", "campo"),
    [
        ("", "q"),
        ("q=ana&status=inactive", "status"),
        ("q=ana&membership_status=active", "membership_status"),
        ("q=ana&plan_id=00000000-0000-0000-0000-000000000001", "plan_id"),
        ("q=ana&consent=missing", "consent"),
        ("q=ana&last_attendance=30d", "last_attendance"),
    ],
)
async def test_en_quiosco_la_lista_de_socios_exige_q_y_rechaza_los_filtros_de_situacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    consulta: str,
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(f"{SOCIOS}?{consulta}", headers=_quiosco(coach, "coach", reloj))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == campo


async def test_en_quiosco_la_lista_de_socios_con_q_funciona_y_fuera_no_exige_q(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    await socio(session, nombre="Ana", apellido="Prueba")
    ok = await app_http.get(f"{SOCIOS}?q=Ana", headers=_quiosco(coach, "coach", reloj))
    assert ok.status_code == 200 and len(ok.json()["items"]) == 1, ok.text
    fuera = await app_http.get(f"{SOCIOS}?status=inactive", headers=cabeceras(coach))
    assert fuera.status_code == 200, fuera.text
