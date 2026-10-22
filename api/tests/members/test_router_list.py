"""`GET /api/v1/members` por HTTP (S2-B8; US-070 criterios 1, 2, 3, 6, 7 y 8; N-01, N-20, L-1,
S2-D41 del servidor).

- admin y coach: 200 `{items, total, limit, offset}` (25 por defecto); los dos ven a los dados
  de baja con `status=deleted` (N-20); `member` 403 `forbidden`; sin token 401 `unauthorized`;
- 422 `validation_error` con `field` para `limit` (0, 201, 500), `offset` (-1), `sort`,
  `status` y un `q` de 101 caracteres; `limit=200` es válido;
- las filas no traen `document`, `phone`, `email`, `birth_date`, `emergency_contact`, `*_idx`
  ni `*_hint`, ni el claro ni la máscara (N-01);
- L-1: la búsqueda 61 con `q` de un mismo usuario en un minuto da 429 `rate_limited` con
  `Retry-After`; las peticiones sin `q` no cuentan ni se frenan; otro usuario no se ve afectado;
- el `q` buscado nunca aparece en los logs (stdout JSON con `capsys` y registros con `caplog`).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.members._apoyo import MEMBERS

LIMITE_DE_BUSQUEDAS = 60
CAMPOS_FILA = {
    "id",
    "first_name",
    "last_name",
    "sex",
    "status",
    "deleted_at",
    "membership_status",
    "plan_name",
}


async def _socios(session: AsyncSession) -> dict[str, str]:
    """Un socio de `KNOWN` vivo y uno dado de baja; devuelve sus ids como texto."""
    conocida = await make_member(session)
    baja = await make_member(
        session,
        first_name="Pedro",
        last_name="Ruiz",
        document=unique_document(),
        phone=None,
        email=None,
        deleted_at=T0 - timedelta(days=1),
    )
    return {"conocida": str(conocida.id), "baja": str(baja.id)}


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_pagina_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    socios = await _socios(session)
    quien = await usuario_real(rol)
    r = await app_http.get(MEMBERS, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["limit"], datos["offset"]) == (25, 0)
    assert [f["id"] for f in datos["items"]] == [socios["conocida"]]
    assert datos["total"] == 1
    fila = datos["items"][0]
    assert set(fila) == CAMPOS_FILA
    assert fila["membership_status"] is None


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_ven_a_los_dados_de_baja_con_status_deleted(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    socios = await _socios(session)
    quien = await usuario_real(rol)
    r = await app_http.get(MEMBERS, params={"status": "deleted"}, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [socios["baja"]]
    assert r.json()["items"][0]["deleted_at"] is not None


async def test_buscar_por_documento_telefono_correo_y_nombre_por_http(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    socios = await _socios(session)
    coach = await usuario_real("coach")
    for termino in (KNOWN["document"], "300 765 4321", "LUCIA.GOMEZ@CORREO.CO", "góm"):
        r = await app_http.get(MEMBERS, params={"q": termino}, headers=cabeceras(coach))
        assert r.status_code == 200, (termino, r.text)
        assert [f["id"] for f in r.json()["items"]] == [socios["conocida"]], termino


async def test_las_filas_no_llevan_datos_sensibles_ni_mascaras(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _socios(session)
    admin = await usuario_real("admin")
    r = await app_http.get(MEMBERS, params={"q": "góm"}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    for fila in r.json()["items"]:
        for campo in fila:
            assert not campo.endswith(("_idx", "_hint")), campo
            assert campo not in {"document", "phone", "email", "birth_date", "emergency_contact"}
    for valor in (*KNOWN_NORMALIZED, "apx1.", "•"):
        assert valor not in r.text, valor


async def test_el_rol_member_recibe_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(MEMBERS, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    r = await app_http.get(MEMBERS, params={"q": "góm"}, headers=cabeceras(socio))
    assert r.status_code == 403, r.text


async def test_sin_token_recibe_401(app_http: AsyncClient) -> None:
    r = await app_http.get(MEMBERS)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("query", "campo"),
    [
        ("limit=500", "limit"),
        ("limit=201", "limit"),
        ("limit=0", "limit"),
        ("limit=-1", "limit"),
        ("offset=-1", "offset"),
        ("sort=foo", "sort"),
        ("sort=document", "sort"),
        ("status=foo", "status"),
        ("q=" + "x" * 101, "q"),
    ],
    ids=[
        "limit-500",
        "limit-201",
        "limit-0",
        "limit-negativo",
        "offset-negativo",
        "sort-desconocido",
        "sort-por-documento",
        "estado",
        "q-largo",
    ],
)
async def test_parametros_invalidos_dan_422_con_el_campo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    query: str,
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(f"{MEMBERS}?{query}", headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["field"] == campo


async def test_limit_200_y_un_q_de_100_son_validos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await _socios(session)
    admin = await usuario_real("admin")
    r = await app_http.get(MEMBERS, params={"limit": 200, "q": "x" * 100}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200 and r.json()["items"] == []


@pytest.mark.parametrize(
    "orden", ["last_name", "-last_name", "first_name", "-first_name", "created_at", "-created_at"]
)
async def test_cada_sort_permitido_responde_200(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    orden: str,
) -> None:
    await _socios(session)
    coach = await usuario_real("coach")
    r = await app_http.get(MEMBERS, params={"sort": orden}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text


async def test_la_busqueda_61_con_q_da_429_sin_q_no_cuenta_y_otro_usuario_sigue(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """L-1: `ratelimit.enforce("members-search", str(user_id), limit=60, window_s=60,
    kind="user")` solo cuando hay `q`; el reloj está congelado, así todo cae en la misma
    ventana."""
    await _socios(session)
    coach = await usuario_real("coach")
    otro = await usuario_real("admin")
    for numero in range(5):
        r = await app_http.get(MEMBERS, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    for numero in range(LIMITE_DE_BUSQUEDAS):
        r = await app_http.get(MEMBERS, params={"q": f"g{numero}"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "góm"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    sin_q = await app_http.get(MEMBERS, headers=cabeceras(coach))
    assert sin_q.status_code == 200, sin_q.text
    vacio = await app_http.get(MEMBERS, params={"q": ""}, headers=cabeceras(coach))
    assert vacio.status_code == 200, vacio.text
    ajeno = await app_http.get(MEMBERS, params={"q": "góm"}, headers=cabeceras(otro))
    assert ajeno.status_code == 200, ajeno.text


async def test_el_termino_buscado_nunca_aparece_en_los_logs(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """US-018 y T14 de US-070: el `q` puede ser un documento, un teléfono o un correo."""
    await _socios(session)
    configure_logging(api_prueba.state.settings)  # el handler escribe en el stdout de capsys
    caplog.set_level(logging.DEBUG)
    coach = await usuario_real("coach")
    buscados: list[Any] = [
        KNOWN["document"],
        "300 765 4321",
        "LUCIA.GOMEZ@CORREO.CO",
        "Buscadísimo",
    ]
    for termino in buscados:
        r = await app_http.get(MEMBERS, params={"q": termino}, headers=cabeceras(coach))
        assert r.status_code == 200, r.text
    invalido = await app_http.get(
        MEMBERS, params={"q": "Buscadísimo", "sort": "foo"}, headers=cabeceras(coach)
    )
    assert invalido.status_code == 422, invalido.text
    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    for valor in (*buscados, "300765", "lucia.gomez", "Buscad"):
        assert str(valor) not in texto, valor
