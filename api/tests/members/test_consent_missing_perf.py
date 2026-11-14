"""`GET /members?consent=missing` con 1.000 socios y su EXPLAIN (S6-C5, US-151, V8). `perf`.

600 socios sin autorizacion y 400 con ella, sembrados dentro de la transaccion de la prueba. Tras
un calentamiento, la lista (pagina de 25 con su conteo) responde en menos de 500 ms: mismo tope que
la lista de socios sin filtro (`test_list_perf.py`), porque el filtro agrega solo
`data_consent_at IS NULL` sobre una tabla de 1.000 filas y no cambia el orden de magnitud.
Imprime el `EXPLAIN (ANALYZE, BUFFERS)` de las consultas de `members.members` (conteo y pagina)
para decidir si hace falta el indice parcial de consentimiento (hoy no hay migracion `0025`).
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.explain import capturar_sql, imprimir_explain
from tests.factories.members import make_members
from tests.members._apoyo import MEMBERS
from tests.notifications._apoyo_avisos import ANTES

pytestmark = pytest.mark.perf

SIN_AUTORIZACION = 600
CON_AUTORIZACION = 400
TOPE_MS = 500


async def test_con_mil_socios_el_filtro_consent_missing_baja_de_500_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    await make_members(session, SIN_AUTORIZACION, last_name="Sin", data_consent_at=None)
    await make_members(session, CON_AUTORIZACION, last_name="Con", data_consent_at=ANTES)
    await session.execute(text("ANALYZE members.members"))
    coach = await usuario_real("coach")
    calentamiento = await app_http.get(
        MEMBERS, params={"consent": "missing"}, headers=cabeceras(coach)
    )
    assert calentamiento.status_code == 200, calentamiento.text

    with capturar_sql(session, "members.members") as capturadas:
        inicio = time.perf_counter()
        r = await app_http.get(MEMBERS, params={"consent": "missing"}, headers=cabeceras(coach))
        ms = (time.perf_counter() - inicio) * 1000

    assert r.status_code == 200, r.text
    assert r.json()["total"] == SIN_AUTORIZACION
    assert len(r.json()["items"]) == 25
    print(
        f"\nGET /members?consent=missing con {SIN_AUTORIZACION + CON_AUTORIZACION} socios: "
        f"{ms:.1f} ms (tope {TOPE_MS} ms)"
    )
    await imprimir_explain(session, "consent=missing", capturadas)
    assert ms < TOPE_MS, ms
