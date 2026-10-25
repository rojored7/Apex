"""`GET /api/v1/payments/{payment_id}` por HTTP (S3-B8, US-099; D27, L-2, S3-D57).

- admin y coach: 200 `PaymentDetail` (claves exactas), montos enteros y
  `Cache-Control: no-store`; el anulado trae `void_reason`, `voided_at` y `voided_by_name`
  parcial (`m•••@test.apex`), nunca el correo completo;
- inexistente: 404 `payment_not_found`; `no-es-uuid`: 422 `validation_error` con
  `field="payment_id"`;
- `member` 403 `forbidden`; sin token 401 `unauthorized`;
- `/payments/summary` y `/payments/methods` no caen en `{payment_id}` (responden su contrato, no
  422); el orden de los `GET` del router es `summary`, `methods`, lista y `{payment_id}` (D27).

Datos: un pago de 60.000 en efectivo y uno de 40.000 por Nequi anulado por el admin
`mario.admin@test.apex` con el motivo "Monto mal digitado"; "hoy" 2026-10-21.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import effective_routes
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import (
    CAMPOS_DETAIL,
    CAMPOS_METODO,
    CAMPOS_RESUMEN,
    METODOS,
    PAYMENTS,
    RESUMEN,
    ruta_pago,
)

CORREO_ADMIN = "mario.admin@test.apex"
MOTIVO = "Monto mal digitado"


async def _pagos(session: AsyncSession, admin_id: UUID) -> dict[str, UUID]:
    plan = await make_plan(session)
    socio = await make_member(session)
    membresia = await make_membership(session, socio, plan, status="active")
    vigente = await make_payment(
        session, membresia, amount=60_000, paid_at=datetime(2026, 10, 10, 15, tzinfo=UTC)
    )
    anulado = await make_payment(
        session,
        membresia,
        amount=40_000,
        method="nequi",
        paid_at=datetime(2026, 10, 12, 15, tzinfo=UTC),
        voided=True,
        void_reason=MOTIVO,
        voided_by=admin_id,
        voided_at=datetime(2026, 10, 13, 15, tzinfo=UTC),
    )
    return {"vigente": vigente.id, "anulado": anulado.id}


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_el_detalle(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    admin = await usuario_real("admin", email=CORREO_ADMIN)
    quien = admin if rol == "admin" else await usuario_real("coach")
    ids = await _pagos(session, admin.id)
    r = await app_http.get(ruta_pago(ids["vigente"]), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == CAMPOS_DETAIL
    assert (datos["id"], datos["amount_cop"], datos["voided"]) == (
        str(ids["vigente"]),
        60_000,
        False,
    )
    assert type(datos["amount_cop"]) is int
    assert (datos["voided_by"], datos["voided_by_name"], datos["voided_at"]) == (None, None, None)


async def test_el_detalle_de_un_anulado_trae_el_motivo_y_el_correo_parcial(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin", email=CORREO_ADMIN)
    coach = await usuario_real("coach")
    ids = await _pagos(session, admin.id)
    r = await app_http.get(ruta_pago(ids["anulado"]), headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert (datos["voided"], datos["void_reason"], datos["voided_by"]) == (
        True,
        MOTIVO,
        str(admin.id),
    )
    assert datos["voided_by_name"] == "m•••@test.apex"
    assert datos["voided_at"] is not None
    assert CORREO_ADMIN not in r.text


async def test_un_pago_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_pago(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "payment_not_found"


async def test_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_pago("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "payment_id")


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(ruta_pago(uuid4()), headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(ruta_pago(uuid4()))
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


async def test_summary_y_methods_no_caen_en_el_detalle(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    resumen = await app_http.get(RESUMEN, headers=cabeceras(coach))
    assert resumen.status_code == 200, resumen.text
    assert set(resumen.json()) == CAMPOS_RESUMEN
    metodos = await app_http.get(METODOS, headers=cabeceras(coach))
    assert metodos.status_code == 200, metodos.text
    assert {frozenset(m) for m in metodos.json()["items"]} == {CAMPOS_METODO}


def test_los_get_de_pagos_se_declaran_en_orden_fijo(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    rutas = [
        ruta.path
        for ruta in effective_routes(app)[0]
        if "GET" in (ruta.methods or ()) and ruta.path.startswith(PAYMENTS)
    ]
    assert rutas == [
        f"{PAYMENTS}/summary",
        f"{PAYMENTS}/methods",
        PAYMENTS,
        f"{PAYMENTS}/{{payment_id}}",
    ]
