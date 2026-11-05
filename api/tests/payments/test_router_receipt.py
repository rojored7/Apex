"""`GET /api/v1/payments/{payment_id}/receipt.pdf` por HTTP (S5-B11, US-137, S5-D40, S5-D65).

# Rojo B11

- admin y coach: 200 `application/pdf` con el recibo (frase fija, monto), `Content-Disposition:
  attachment; filename=recibo-<8 primeros hex del id>.pdf`, `Cache-Control: no-store` y
  `X-Content-Type-Options: nosniff`; cada descarga deja UNA fila `download` en la auditoría;
- `member` 403 `forbidden` y sin token 401 `unauthorized`, sin auditar; inexistente 404
  `payment_not_found` (JSON, sin auditar); `no-es-uuid` 422 con `field="payment_id"`;
- la ruta se declara ANTES de `/payments/{payment_id}` (D27);
- cubeta `staff-read` (120 por minuto): lo prueba `tests/architecture/test_user_limits_catalog.py`.

Datos: un pago de 60.000 en efectivo de Lucía Gómez (hoy 2026-10-21).
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import effective_routes
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import PAYMENTS

FRASE = "Comprobante interno de pago. No es factura electrónica."


def ruta_recibo(payment_id: UUID | str) -> str:
    return f"{PAYMENTS}/{payment_id}/receipt.pdf"


async def _pago(session: AsyncSession) -> UUID:
    plan = await make_plan(session)
    socio = await make_member(session)
    membresia = await make_membership(session, socio, plan, status="active")
    pago = await make_payment(
        session, membresia, amount=60_000, paid_at=datetime(2026, 10, 10, 15, tzinfo=UTC)
    )
    return pago.id


async def _descargas(session: AsyncSession, payment_id: UUID) -> int:
    cuenta = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE action = 'download' AND record_id = :r"),
        {"r": payment_id},
    )
    return int(cuenta or 0)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_descargan_el_recibo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    pago = await _pago(session)
    r = await app_http.get(ruta_recibo(pago), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].split(";")[0] == "application/pdf"
    assert r.headers["content-disposition"] == f"attachment; filename=recibo-{str(pago)[:8]}.pdf"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.content.startswith(b"%PDF-")
    cuerpo = "\n".join(p.extract_text() for p in PdfReader(BytesIO(r.content), strict=True).pages)
    assert FRASE in cuerpo
    assert "$ 60.000" in cuerpo


async def test_cada_descarga_deja_una_fila_download(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    pago = await _pago(session)
    assert await _descargas(session, pago) == 0
    for esperado in (1, 2):
        r = await app_http.get(ruta_recibo(pago), headers=cabeceras(coach))
        assert r.status_code == 200, r.text
        assert await _descargas(session, pago) == esperado


async def test_un_pago_inexistente_da_404_json_y_no_audita(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    inexistente = uuid4()
    r = await app_http.get(ruta_recibo(inexistente), headers=cabeceras(coach))
    assert r.status_code == 404, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "payment_not_found"
    assert await _descargas(session, inexistente) == 0


async def test_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_recibo("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "payment_id")


async def test_member_recibe_403_sin_auditar_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    socio = await usuario_real("member")
    pago = await _pago(session)
    r = await app_http.get(ruta_recibo(pago), headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert b"%PDF" not in r.content
    sin_token = await app_http.get(ruta_recibo(pago))
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"
    assert await _descargas(session, pago) == 0


def test_la_ruta_del_recibo_se_declara_antes_que_el_detalle(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    rutas = [
        ruta.path
        for ruta in effective_routes(app)[0]
        if "GET" in (ruta.methods or ()) and ruta.path.startswith(PAYMENTS)
    ]
    recibo = f"{PAYMENTS}/{{payment_id}}/receipt.pdf"
    detalle = f"{PAYMENTS}/{{payment_id}}"
    assert recibo in rutas
    assert rutas.index(recibo) < rutas.index(detalle)
