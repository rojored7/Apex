"""Rendimiento de la lista de socios y del login fallido bajo el candado de la cadena (S2-B8;
US-070 criterios 5 y 9; S2-D27, C1; L-11).

Marcado `perf` (S2-D27): los gates corren `-m "not perf"` salvo el de B8 y V5 (E8, E9).

- 1.000 socios sembrados con `make_members` dentro de la transacción de la prueba (`session`:
  todo se revierte al salir, la tabla no queda llena entre archivos).
- Tras un calentamiento, `GET /members?q=<documento con puntos>` responde en menos de 500 ms
  (`time.perf_counter`).
- `EXPLAIN (FORMAT JSON)` de la consulta que el service envía en la búsqueda por documento
  (capturada con un listener de SQLAlchemy) usa `uq_members_document_idx_alive`.
- L-11: 20 logins fallidos concurrentes de 20 cuentas (cada uno escribe su fila de auditoría
  bajo el candado de la cadena) con sesiones de commit real; el p95 de la latencia de cada uno
  queda por debajo de 2 s. Es informativa (imprime las latencias), pero con aserción.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.modules.auth import service as auth_service
from app.modules.auth.exceptions import InvalidCredentials
from tests.auth._sesion import politica
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario
from tests.factories.members import make_member, make_members
from tests.members._apoyo import MEMBERS

pytestmark = pytest.mark.perf

SOCIOS = 1000
LIMITE_MS = 500
INDICE_DOCUMENTO = "uq_members_document_idx_alive"
LOGINS_CONCURRENTES = 20
P95_MAXIMO_S = 2.0
DOCUMENTO = "1.020.304"


async def _sembrar(session: AsyncSession) -> None:
    await make_members(session, SOCIOS - 1, last_name="Carga")
    await make_member(
        session,
        first_name="Laura",
        last_name="Gómez",
        document="1020304",
        phone="3001234567",
        email="laura.gomez@correo.co",
    )
    await session.execute(text("ANALYZE members.members"))


def _usa_indice(plan: Any, indice: str) -> bool:
    if isinstance(plan, dict):
        if plan.get("Index Name") == indice:
            return True
        return any(_usa_indice(v, indice) for v in plan.values())
    if isinstance(plan, list):
        return any(_usa_indice(v, indice) for v in plan)
    return False


async def test_con_mil_socios_buscar_por_documento_tarda_menos_de_500_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _sembrar(session)
    coach = await usuario_real("coach")
    calentamiento = await app_http.get(MEMBERS, params={"q": "1.111.111"}, headers=cabeceras(coach))
    assert calentamiento.status_code == 200, calentamiento.text
    inicio = time.perf_counter()
    r = await app_http.get(MEMBERS, params={"q": DOCUMENTO}, headers=cabeceras(coach))
    transcurrido_ms = (time.perf_counter() - inicio) * 1000
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 1 and r.json()["items"][0]["first_name"] == "Laura"
    print(f"\nbúsqueda por documento con {SOCIOS} socios: {transcurrido_ms:.1f} ms")
    assert transcurrido_ms < LIMITE_MS


async def test_la_rama_de_documento_usa_el_indice_unico_parcial(
    session: AsyncSession, engine: AsyncEngine, bus_listo: object
) -> None:
    from app.core.context import SYSTEM_USER_ID, actor_scope
    from app.core.pagination import PageParams
    from app.modules.members import service
    from app.modules.members.schemas import MemberListQuery

    await _sembrar(session)
    capturadas: list[tuple[str, Any]] = []

    def anotar(_c: Any, _cur: Any, sql: str, parametros: Any, *_a: Any) -> None:
        if "document_idx" in sql and sql.lstrip().upper().startswith(("SELECT", "WITH")):
            capturadas.append((sql, parametros))

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    try:
        with actor_scope(SYSTEM_USER_ID):
            pagina = await service.list(session, MemberListQuery(q=DOCUMENTO), PageParams())
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)
    assert pagina.total == 1
    assert capturadas, "el service no envió una consulta con document_idx"
    conexion = await session.connection()
    for sql, parametros in capturadas:
        resultado = await conexion.exec_driver_sql("EXPLAIN (FORMAT JSON) " + sql, parametros)
        plan = resultado.scalar_one()
        plan = json.loads(plan) if isinstance(plan, str) else plan
        assert _usa_indice(plan, INDICE_DOCUMENTO), json.dumps(plan)[:2000]


@pytest.fixture
async def motor_amplio(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    """Un motor con pool para 20 sesiones a la vez (el de `engine` tiene 5 + 10)."""
    motor = create_async_engine(
        migrated_database, hide_parameters=True, pool_size=LOGINS_CONCURRENTES + 2
    )
    try:
        yield motor
    finally:
        await motor.dispose()


async def test_l11_veinte_logins_fallidos_concurrentes_bajo_el_candado_p95_menor_a_2_s(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    motor_amplio: AsyncEngine,
    seguridad: object,
) -> None:
    """`dos_sesiones` siembra y, al salir, borra las cuentas `@test.apex` y la cola de la
    cadena de auditoría; cada login corre en su propia sesión con commit real."""
    from tests.factories.users import make_user

    primera, _ = dos_sesiones
    correos: list[str] = []
    for _ in range(LOGINS_CONCURRENTES):
        usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
        correos.append(usuario.email)
    fabrica = async_sessionmaker(motor_amplio, expire_on_commit=False)

    async def fallar(numero: int, correo: str) -> float:
        async with fabrica() as sesion:
            inicio = time.perf_counter()
            try:
                await auth_service.login(
                    sesion,
                    correo,
                    "Clave-Equivocada-1",
                    ip=f"198.51.100.{numero + 1}",
                    user_agent="perf",
                    policy=politica(),
                )
            except InvalidCredentials:
                await sesion.rollback()  # lo que hace `get_session` ante la excepción
            else:
                raise AssertionError("una contraseña equivocada no puede iniciar sesión")
            return time.perf_counter() - inicio

    latencias = sorted(await asyncio.gather(*(fallar(n, c) for n, c in enumerate(correos))))
    p95 = latencias[math.ceil(0.95 * len(latencias)) - 1]
    print(
        f"\nL-11 login fallido x{LOGINS_CONCURRENTES}: p50 {latencias[len(latencias) // 2]:.3f} s,"
        f" p95 {p95:.3f} s, máx {latencias[-1]:.3f} s"
    )
    await primera.rollback()
    registrados = await primera.scalar(
        text(
            "SELECT count(*) FROM auth.users WHERE email = ANY(:correos) AND failed_login_count = 1"
        ),
        {"correos": correos},
    )
    assert registrados == LOGINS_CONCURRENTES  # cada fallo pasó por su registro
    assert p95 < P95_MAXIMO_S
