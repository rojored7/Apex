"""`GET /api/v1/members/{member_id}` por HTTP (S3-B9b; US-073 criterios 1 a 6; D20, D27, M-2,
S3-D45, N-01, N-20).

- admin y coach: 200 con la ficha enmascarada (`CAMPOS_DETALLE`, las máscaras de `KNOWN`, el
  estado de membresía, `warnings == []`); el coach también sobre un dado de baja (N-20);
- `member` 403 `forbidden`; sin token 401 `unauthorized`; un id inexistente 404
  `member_not_found`; un id que no es UUID 422 `validation_error` con `field="member_id"`;
- `Cache-Control: no-store` en el 200 (los errores salen por el handler, sin la cabecera de la
  dependencia: decisión de S3-B5);
- la respuesta no lleva ningún valor de `KNOWN` en claro ni normalizado, ni blobs `apx1.`;
- ni el stdout JSON ni `caplog` contienen esos valores ni las máscaras;
- M-2: la ficha 121 de un usuario en un minuto da 429 `rate_limited` con `Retry-After` (la cubeta
  es `members-detail`: el registro del 429 la nombra) y la de otro usuario pasa; la lista del
  mismo usuario sigue respondiendo (otra cubeta); un 404 también consume la cubeta.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from app.core.logging import configure_logging
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN_NORMALIZED, make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import CAMPOS_DETALLE, MASCARAS_KNOWN, MEMBERS, ruta_socio

LIMITE_DE_FICHAS = 120


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_ficha_enmascarada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    rol: str,
) -> None:
    mensual = await make_plan(session, name="Mensual")
    socio = await make_member(session)
    await make_membership(
        session, socio, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    quien = await usuario_real(rol)
    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_DETALLE
    assert datos["id"] == str(socio.id)
    for campo, mascara in MASCARAS_KNOWN.items():
        assert datos[campo] == mascara, campo
    assert (datos["membership_status"], datos["plan_name"], datos["membership_end_date"]) == (
        "active",
        "Mensual",
        "2026-11-30",
    )
    assert datos["warnings"] == []
    assert r.headers["cache-control"] == "no-store"


async def test_el_coach_ve_la_ficha_de_un_dado_de_baja(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None
    assert r.json()["document"] == MASCARAS_KNOWN["document"]
    assert r.json()["membership_status"] == "none"


async def test_la_respuesta_no_lleva_ningun_valor_en_claro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    admin = await usuario_real("admin")
    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    for valor in (*KNOWN_NORMALIZED, "apx1."):
        assert valor not in r.text, valor
    for campo in r.json():
        assert not campo.endswith(("_idx", "_hint")), campo


async def test_el_rol_member_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    miembro = await usuario_real("member")
    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(miembro))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert MASCARAS_KNOWN["document"] not in r.text


async def test_sin_token_recibe_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    r = await app_http.get(ruta_socio(socio.id))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(
        ruta_socio("00000000-0000-4000-8000-000000000999"), headers=cabeceras(coach)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


@pytest.mark.parametrize("valor", ["no-es-uuid", "123", "00000000-0000-0000-0000"])
async def test_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, valor: str
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(f"{MEMBERS}/{valor}", headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "member_id")


async def test_los_logs_no_llevan_valores_ni_mascaras(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    configure_logging(api_prueba.state.settings)  # el handler escribe en el stdout de capsys
    caplog.set_level(logging.DEBUG)
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    for valor in (*KNOWN_NORMALIZED, *MASCARAS_KNOWN.values(), "apx1."):
        assert valor not in texto, valor


# M-2: `members-detail` 120 por minuto ------------------------------------------------------


async def test_la_ficha_121_en_un_minuto_da_429_y_otro_usuario_pasa(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El reloj está congelado: las 121 caen en la misma ventana."""
    socio = await make_member(
        session, phone=None, email=None, birth_date=None, emergency_contact=None
    )
    ruta = ruta_socio(socio.id)  # el 429 revierte la sesión y expira el objeto
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    for numero in range(LIMITE_DE_FICHAS):
        r = await app_http.get(ruta, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    caplog.set_level(logging.WARNING)
    r = await app_http.get(ruta, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    cubetas = [getattr(rec, "bucket", None) for rec in caplog.records]
    assert "members-detail" in cubetas, cubetas
    r = await app_http.get(ruta, headers=cabeceras(otro))
    assert r.status_code == 200, r.text
    lista = await app_http.get(MEMBERS, headers=cabeceras(coach))
    assert lista.status_code == 200, lista.text


async def test_un_404_tambien_consume_la_cubeta(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """M-2: recorrer ids inexistentes no es un barrido gratis."""
    coach = await usuario_real("coach")
    inexistente = ruta_socio("00000000-0000-4000-8000-000000000999")
    for numero in range(LIMITE_DE_FICHAS):
        r = await app_http.get(inexistente, headers=cabeceras(coach))
        assert r.status_code == 404, (numero, r.text)
    r = await app_http.get(inexistente, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
