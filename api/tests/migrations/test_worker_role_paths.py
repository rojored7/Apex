"""Los caminos del worker corren como `apex_worker` sobre `apex_roles` (S5-W0-3, E6; S5-D34, D204).

Cuando `members.members` pase a `SELECT` por columna, cualquier `select(Member)` completo en un
camino del worker fallaría con `42501`. Estas pruebas ejecutan el código REAL del api con el rol
`apex_worker` (conexión SQLAlchemy asincrónica hacia `apex_roles`) para detectarlo:
- `memberships.expirations.recompute_statuses` (el job `expirations`);
- `members.service.names_for` (nombres de los avisos);
- la carga de `contact_for_notification` con `load_only` (el descifrado llega en B5; aquí solo la
  carga del socio).
Las filas se siembran como propietario y se borran al terminar cada prueba.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import load_only

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.members import service as members_service
from app.modules.members.models import Member
from app.modules.memberships import expirations
from tests.migrations.conftest import RolesDb, url_por_rol
from tests.migrations.test_db_grants import propietario

SYSTEM = str(SYSTEM_USER_ID)
SRC = Path(__file__).resolve().parents[2] / "src" / "app"


def _como_worker[T](
    apex: RolesDb, trabajo: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]
) -> T:
    async def correr() -> T:
        motor: AsyncEngine = create_async_engine(url_por_rol(apex, "apex_worker"))
        try:
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            with actor_scope(SYSTEM_USER_ID):
                return await trabajo(fabrica)
        finally:
            await motor.dispose()

    return asyncio.run(correr())


@pytest.fixture
def socio_con_membresia_vencida(apex_roles: RolesDb) -> dict[str, Any]:
    """Un socio activo con una membresía guardada `active` cuyo `end_date` ya pasó."""
    socio, plan, membresia = str(uuid4()), str(uuid4()), str(uuid4())
    hoy = date.today()
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "  # noqa: S608
        "document_idx, phone, phone_idx, email, email_idx) "
        f"VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Worker', "
        f"'apx1.doc', 'idx-{socio}', 'apx1.fono', 'pidx-{socio}', 'apx1.correo', 'eidx-{socio}')",
        "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days) "  # noqa: S608
        f"VALUES ('{plan}', '{SYSTEM}', 'Plan {plan}', 100000, 'days', 30)",
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "  # noqa: S608
        "agreed_price_cop, start_date, end_date, status) "
        f"VALUES ('{membresia}', '{SYSTEM}', '{socio}', '{plan}', 100000, "
        f"'{hoy - timedelta(days=60)}', '{hoy - timedelta(days=30)}', 'active')",
    )
    # Sin limpieza: una membresía no se borra (trigger `memberships_no_delete`) y `apex_roles`
    # se descarta entera al terminar la sesión.
    return {"socio": UUID(socio), "plan": plan, "membresia": membresia, "hoy": hoy}


def test_recompute_statuses_corre_como_apex_worker_y_vence_la_membresia(
    apex_roles: RolesDb, socio_con_membresia_vencida: dict[str, Any]
) -> None:
    datos = socio_con_membresia_vencida

    async def trabajo(fabrica: async_sessionmaker[AsyncSession]) -> expirations.RecomputeSummary:
        return await expirations.recompute_statuses(fabrica, today=datos["hoy"])

    resumen = _como_worker(apex_roles, trabajo)
    assert resumen.errores == 0, f"el job falló como apex_worker: {resumen}"
    assert resumen.vencidas >= 1

    async def leer(fabrica: async_sessionmaker[AsyncSession]) -> str:
        async with fabrica() as sesion:
            fila = await sesion.execute(
                select(expirations.Membership.status).where(
                    expirations.Membership.id == UUID(datos["membresia"])
                )
            )
            return str(fila.scalar_one())

    assert _como_worker(apex_roles, leer) == "expired"


def test_names_for_corre_como_apex_worker(
    apex_roles: RolesDb, socio_con_membresia_vencida: dict[str, Any]
) -> None:
    socio: UUID = socio_con_membresia_vencida["socio"]

    async def trabajo(fabrica: async_sessionmaker[AsyncSession]) -> Any:
        async with fabrica() as sesion:
            return await members_service.names_for(sesion, [socio])

    nombres = _como_worker(apex_roles, trabajo)
    assert nombres[socio].first_name == "Ana" and nombres[socio].last_name == "Worker"


def test_la_carga_de_contact_for_notification_con_load_only_corre_como_apex_worker(
    apex_roles: RolesDb, socio_con_membresia_vencida: dict[str, Any]
) -> None:
    socio: UUID = socio_con_membresia_vencida["socio"]

    async def trabajo(fabrica: async_sessionmaker[AsyncSession]) -> Member | None:
        async with fabrica() as sesion:
            return await sesion.scalar(
                select(Member)
                .options(
                    load_only(
                        Member.first_name,
                        Member.phone,
                        Member.email,
                        Member.deleted_at,
                    )
                )
                .where(Member.id == socio)
            )

    cargado = _como_worker(apex_roles, trabajo)
    assert cargado is not None and cargado.first_name == "Ana" and cargado.deleted_at is None


def test_un_select_de_member_completo_falla_como_apex_worker(
    apex_roles: RolesDb, socio_con_membresia_vencida: dict[str, Any]
) -> None:
    """Control del arnés (S5-D204): con el `SELECT` por columna, la entidad completa trae
    `document` y PostgreSQL responde `42501`; hoy (tabla completa) esta prueba falla."""
    socio: UUID = socio_con_membresia_vencida["socio"]

    async def trabajo(fabrica: async_sessionmaker[AsyncSession]) -> str:
        async with fabrica() as sesion:
            try:
                await sesion.scalar(select(Member).where(Member.id == socio))
            except Exception as error:  # DBAPIError con el 42501 de asyncpg
                return type(error.__cause__ or error).__name__ + ":" + str(error.__cause__ or error)
            return "sin error"

    resultado = _como_worker(apex_roles, trabajo)
    assert resultado != "sin error", "apex_worker aún puede leer la entidad Member completa"
    assert re.search(r"InsufficientPrivilege|permission denied", resultado), resultado


def test_los_caminos_del_worker_que_cargan_member_usan_load_only() -> None:
    """S5-D32 / D204: `contact_for_notification` carga el socio con `load_only` (nunca la fila
    completa); `names_for` selecciona columnas, no la entidad."""
    contacto = (SRC / "modules" / "members" / "contact.py").read_text(encoding="utf-8")
    assert "load_only" in contacto, "contact.py hace select(Member) completo"
    servicio = (SRC / "modules" / "members" / "service.py").read_text(encoding="utf-8")
    cuerpo = servicio.split("async def names_for", 1)[1].split("\nasync def ", 1)[0]
    assert "select(Member)" not in cuerpo and "Member.id" in cuerpo
