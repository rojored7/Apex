"""Rendimiento del filtro `last_attendance` (S7-R2, US-163 criterio 6). Marcado `perf`.

1.000 socios y 20.000 asistencias; `GET /members?last_attendance=30d` en menos de 500 ms tras
un calentamiento.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session
from tests.factories.members import make_members
from tests.members._apoyo import MEMBERS

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

SOCIOS = 1000
ASISTENCIAS = 20
LIMITE_MS = 500
BASE = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)


async def test_filtro_con_mil_socios_y_veinte_mil_asistencias_bajo_500_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await make_members(session, SOCIOS, last_name="Carga")
    # 20 sesiones en los últimos 60 días x 1.000 socios (SQL directo: 20.000 por ORM es lento);
    # la mitad de los socios (por su id) solo asiste a las sesiones de hace más de 40 días.
    clases = [
        await make_session(session, starts_at=BASE - timedelta(days=3 * d))
        for d in range(ASISTENCIAS)
    ]
    await session.execute(
        text(
            "INSERT INTO classes.attendance (id, session_id, member_id, membership_id, "
            "membership_status_at_checkin, flags, checked_in_at, checked_in_by, created_by, "
            "created_at, updated_at) "
            "SELECT gen_random_uuid(), cs.id, m.id, gen_random_uuid(), 'active', "
            "ARRAY[]::text[], cs.starts_at, :u, :u, now(), now() "
            "FROM classes.class_sessions cs CROSS JOIN members.members m "
            "WHERE cs.id = ANY(CAST(:sids AS uuid[])) "
            "AND (cs.starts_at < :viejo OR ascii(substr(m.id::text, 1, 1)) % 2 = 0)"
        ),
        {
            "u": SYSTEM_USER_ID,
            "sids": [str(c.id) for c in clases],
            "viejo": BASE - timedelta(days=40),
        },
    )
    admin = await usuario_real("admin")
    ruta = f"{MEMBERS}?last_attendance=30d&limit=50"
    await app_http.get(ruta, headers=cabeceras(admin))  # calentamiento
    inicio = time.perf_counter()
    r = await app_http.get(ruta, headers=cabeceras(admin))
    ms = (time.perf_counter() - inicio) * 1000
    assert r.status_code == 200, r.text
    assert 300 < r.json()["total"] < 700, r.json()["total"]  # la mitad, más o menos
    print(f"last_attendance=30d con {SOCIOS} socios: {ms:.0f} ms")
    assert ms < LIMITE_MS, f"{ms:.0f} ms"
