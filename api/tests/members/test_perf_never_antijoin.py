"""Rendimiento de `last_attendance=never` y `membership_status=none` con el anti-join
(S7-C4c, L-1 de la revisión de R2). Marcada `perf`: no es gate.

`!= ALL(:uuid[])` es lineal por fila con el plan genérico de asyncpg (a partir de la sexta
ejecución del mismo statement); `NOT EXISTS (SELECT 1 FROM unnest(:uuid[]) u WHERE u = id)` no.
Con 1.000 socios y 20.000 asistencias, ocho ejecuciones seguidas del mismo statement quedan todas
bajo 500 ms (las primeras cinco usan plan propio; de la sexta en adelante, el genérico).
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
EJECUCIONES = 8
LIMITE_MS = 500
BASE = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)


async def test_never_con_mil_socios_y_veinte_mil_asistencias_siete_o_mas_ejecuciones(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await make_members(session, SOCIOS, last_name="Carga")
    clases = [
        await make_session(session, starts_at=BASE - timedelta(days=3 * d)) for d in range(20)
    ]
    # Asisten 900 de los 1.000 socios: `never` deja un conjunto grande para excluir.
    await session.execute(
        text(
            "INSERT INTO classes.attendance (id, session_id, member_id, membership_id, "
            "membership_status_at_checkin, flags, checked_in_at, checked_in_by, created_by, "
            "created_at, updated_at) "
            "SELECT gen_random_uuid(), cs.id, m.id, gen_random_uuid(), 'active', "
            "ARRAY[]::text[], cs.starts_at, :u, :u, now(), now() "
            "FROM classes.class_sessions cs CROSS JOIN members.members m "
            "WHERE cs.id = ANY(CAST(:sids AS uuid[])) "
            "AND ascii(substr(m.id::text, 1, 1)) % 10 <> 0"
        ),
        {"u": SYSTEM_USER_ID, "sids": [str(c.id) for c in clases]},
    )
    admin = await usuario_real("admin")
    ruta = f"{MEMBERS}?last_attendance=never&limit=50"
    tiempos: list[float] = []
    for _ in range(EJECUCIONES):
        inicio = time.perf_counter()
        r = await app_http.get(ruta, headers=cabeceras(admin))
        tiempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, r.text
    print("never, ms por ejecución:", [f"{t:.0f}" for t in tiempos])
    assert max(tiempos) < LIMITE_MS, [f"{t:.0f}" for t in tiempos]
