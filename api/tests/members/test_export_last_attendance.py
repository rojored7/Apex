"""`GET /members/export` acepta `last_attendance` como la lista (S7-C4c, M-3 de la revisión de R2).

FastAPI ignora los parámetros desconocidos: antes el filtro se perdía y se exportaba todo en
silencio. Hoy es el 21 de octubre de 2026 (`reloj`). Con el escenario de `test_filter_last_attendance`
(Pedro asistió hace 40 días, Juan ayer, Mara hace 10, Lola nunca, Sara hace 45, los dos bordes, y
Tomás, dado de baja), el CSV con `last_attendance=30d` trae a los que NO asistieron en 30 días y
`never` solo a Lola; un valor inválido da 422 con `field`.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.core._export_apoyo import filas_export, parsear, sesion_propia
from tests.members._apoyo import MEMBERS
from tests.members.test_filter_last_attendance import escenario

__all__ = ["escenario"]

RUTA = f"{MEMBERS}/export"


async def _nombres(
    cliente: AsyncClient, session: AsyncSession, admin: object, cabeceras: Cabeceras, **params: str
) -> list[str]:
    with sesion_propia(session):
        r = await cliente.get(RUTA, params=params, headers=cabeceras(admin))  # type: ignore[arg-type]
    assert r.status_code == 200, r.text
    return sorted(f"{fila[0]} {fila[1]}" for fila in parsear(r.content)[1])


async def test_el_filtro_30d_exporta_solo_a_los_que_no_asistieron_en_treinta_dias(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    todos = await _nombres(app_http, session, admin, cabeceras)
    con_filtro = await _nombres(app_http, session, admin, cabeceras, last_attendance="30d")
    assert len(con_filtro) < len(todos), "el filtro se ignoró en silencio"
    assert con_filtro == [
        "Borde Treintaiuno",
        "Lola Paz",
        "Pedro Díaz",
        "Sara Gil",
    ]


async def test_never_exporta_solo_a_quien_no_asistio_nunca(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    assert await _nombres(app_http, session, admin, cabeceras, last_attendance="never") == [
        "Lola Paz"
    ]


async def test_un_valor_invalido_da_422_con_field(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(RUTA, params={"last_attendance": "1d"}, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "last_attendance"


async def test_la_auditoria_de_apertura_guarda_el_filtro_estructurado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    await _nombres(app_http, session, admin, cabeceras, last_attendance="never")
    apertura, _ = await filas_export(session, "members.members")
    assert apertura["after"]["filters"]["last_attendance"] == "never"
