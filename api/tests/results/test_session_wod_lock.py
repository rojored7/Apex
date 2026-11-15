"""`PATCH /class-sessions/{id}` con resultados vigentes (S8-B1; revisión de A4, M-2).

El WOD efectivo de una sesión con resultados no cambia (409 `locked_by_results`, `field = wod_id`);
fijar el mismo WOD que ya era el efectivo, o volver a heredarlo, sí se permite. Lo decide el puerto
que `results` registra en `classes`.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes import service as classes_service
from app.modules.classes.exceptions import ResultsPortNotRegistered
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.wods import make_movement, make_wod
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")
SESIONES = "/api/v1/class-sessions"


async def test_con_resultados_el_wod_efectivo_no_cambia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    assert e.clase_id is not None
    mov = await make_movement(session, e.coach, name="Otro mov M2", unit="kg")
    otro = await make_wod(session, e.coach, [mov.id], date="2026-10-20", title="Ayer")
    clase_id, wod_id = e.clase_id, e.wod_id
    await registrar(session, e)
    h = cabeceras(await usuario_real("admin"))
    url = f"{SESIONES}/{clase_id}"
    cambio = await app_http.patch(url, json={"wod_id": str(otro.id)}, headers=h)
    assert cambio.status_code == 409, cambio.text
    assert cambio.json()["error"]["code"] == "locked_by_results"
    assert cambio.json()["error"]["field"] == "wod_id"
    igual = await app_http.patch(url, json={"wod_id": str(wod_id)}, headers=h)
    assert igual.status_code == 200 and igual.json()["effective_wod_id"] == str(wod_id)
    heredar = await app_http.patch(url, json={"wod_id": None}, headers=h)
    assert heredar.status_code == 200 and heredar.json()["effective_wod_id"] == str(wod_id)


async def test_sin_puerto_de_resultados_el_cambio_falla_cerrado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    assert e.clase_id is not None
    mov = await make_movement(session, e.coach, name="Otro mov puerto", unit="kg")
    otro = (await make_wod(session, e.coach, [mov.id], date="2026-10-20", title="Ayer")).id
    clase_id = e.clase_id
    h = cabeceras(await usuario_real("admin"))
    anterior = classes_service.results_port()
    classes_service.set_results_port(None)
    try:
        with pytest.raises(ResultsPortNotRegistered):
            await app_http.patch(f"{SESIONES}/{clase_id}", json={"wod_id": str(otro)}, headers=h)
    finally:
        classes_service.set_results_port(anterior)
