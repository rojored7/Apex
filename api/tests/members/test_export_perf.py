"""Rendimiento de `GET /members/export` (S5-B12, US-138 criterio 6). Rojo B12.

Marcado `perf` (no es gate): 1.000 socios con documento, teléfono y correo se exportan en menos
de 10 s por HTTP (descifrado por lotes de 500, no uno por uno) y salen las 1.000 filas, en dos
lotes de 500 por clase en `crypto_ops`.
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from tests.conftest import Cabeceras, CrearUsuario
from tests.core._export_apoyo import ops_export, parsear, sesion_propia
from tests.factories.members import make_member, unique_document
from tests.members._apoyo import MEMBERS

pytestmark = pytest.mark.perf

SOCIOS = 1000
LIMITE_S = 10.0


async def test_mil_socios_se_exportan_en_menos_de_diez_segundos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    admin = await usuario_real("admin")
    for n in range(SOCIOS):
        await make_member(
            session,
            first_name=f"Carga {n:04d}",
            document=unique_document(),
            phone=f"3{n:09d}",
            email=f"carga{n}@correo.co",
        )
    with sesion_propia(session):
        inicio = time.perf_counter()
        r = await app_http.get(f"{MEMBERS}/export", headers=cabeceras(admin))
        duracion = time.perf_counter() - inicio
    assert r.status_code == 200, r.text
    assert len(parsear(r.content)[1]) == SOCIOS
    assert duracion < LIMITE_S, duracion
    assert await ops_export(session) == [
        ("member.document", 500),
        ("member.document", 500),
        ("member.email", 500),
        ("member.email", 500),
        ("member.phone", 500),
        ("member.phone", 500),
    ]
