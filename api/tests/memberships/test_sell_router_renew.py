"""`renew=true` por HTTP antes de S3-B6 (revisión de seguridad de S3-B1, hallazgo M1).

El service todavía lanza `NotImplementedError` con `renew=True` (lo fija
`test_sell_service.py`); por HTTP eso sería un 500 que cualquier admin o coach podría disparar.
`SellMembershipIn` lo rechaza antes con un 422 de forma (`validation_error`, `field="renew"`) y no
crea nada. B6 quita el validador y este archivo.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.plans import make_plan
from tests.memberships._apoyo import cuerpo_venta, membresias_del_socio, ruta_venta


async def test_renew_true_da_422_y_no_500_hasta_b6(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    socio_id, plan_id = socio.id, plan.id  # tras el 422 la sesión revierte y el ORM expira
    r = await app_http.post(
        ruta_venta(socio_id), json=cuerpo_venta(plan_id, renew=True), headers=cabeceras(coach)
    )
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "renew")
    assert await membresias_del_socio(session, socio_id) == []


async def test_renew_false_explicito_sigue_vendiendo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id, renew=False), headers=cabeceras(admin)
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending_payment"
