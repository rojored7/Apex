"""Cobertura de la lista sobre las tablas auditadas de v0.1 (S4A-B4, US-102; S4A-D16, S4A-D61 b).

Una escritura por los services reales en cada tabla (`members`, `plans`, `memberships`,
`payments` con `sembrar_actividad`; `auth.users` con `create_user` hecho por Ana; la sección `gym`
de `settings` guardada por Ana) y la verificación de la cadena: el filtro `table` de `GET /audit`
devuelve cada `insert` con quién (`user_id`, `user_name`) y cuándo (`at` = T0,
2026-10-21T15:00:00Z, el reloj congelado); `audit.verifications` aparece con la acción `verify`
tras `run_verification`. Toda tabla que aparece está en `AUDITABLE_TABLES`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_verify import run_verification
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.audit.queries import AUDITABLE_TABLES
from app.modules.audit.schemas import AuditListQuery, AuditRow
from app.modules.auth import service as auth_service
from app.modules.settings import service as settings_service
from tests.audit._apoyo import ANA_NOMBRE, Actividad, sembrar_actividad
from tests.audit.conftest import audit_service
from tests.conftest import UsuarioPrueba

T0 = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
GYM = {"name": "APEX Auditoría", "city": "Bogotá"}
NUEVO_COACH = "coach.nuevo@ejemplo.local"


@pytest.fixture
async def escrituras(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    settings_prueba: Settings,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    actividad = await sembrar_actividad(session, ana=ana, juan=juan)
    with actor_scope(ana.id):
        await auth_service.create_user(
            session,
            email=NUEVO_COACH,
            role="coach",
            by=ana.id,
            front_base_url=settings_prueba.FRONT_BASE_URL,
        )
        await settings_service.update_section(session, "gym", GYM, 0, ana.id)
        await session.commit()
    return actividad


async def _filas(session: AsyncSession, **datos: object) -> list[AuditRow]:
    pagina = await audit_service.list_entries(
        session,
        AuditListQuery(**datos),
        PageParams(limit=200),  # type: ignore[arg-type]
    )
    return pagina.items


@pytest.mark.parametrize(
    "tabla",
    [
        "members.members",
        "plans.plans",
        "memberships.memberships",
        "payments.payments",
        "settings.settings_sections",
    ],
)
async def test_cada_insert_aparece_con_usuario_y_fecha(
    session: AsyncSession,
    escrituras: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    tabla: str,
) -> None:
    filas = await _filas(session, table=tabla, action="insert")
    assert len(filas) == 1, filas
    [fila] = filas
    quien = juan.id if tabla == "payments.payments" else ana.id
    assert (fila.table_name, fila.action, fila.user_id, fila.at) == (tabla, "insert", quien, T0)
    assert fila.user_name is not None and fila.user_email is not None


async def test_el_usuario_creado_por_ana_aparece_a_su_nombre(
    session: AsyncSession, escrituras: Actividad, ana: UsuarioPrueba
) -> None:
    filas = await _filas(session, table="auth.users", action="insert", user_id=ana.id)
    assert [(f.user_name, f.at) for f in filas] == [(ANA_NOMBRE, T0)]


async def test_audit_verifications_aparece_tras_verificar(
    session: AsyncSession, escrituras: Actividad, ana: UsuarioPrueba
) -> None:
    assert await _filas(session, table="audit.verifications") == []
    with actor_scope(ana.id):
        vista = await run_verification(session, source="api", by=ana.id)
        await session.commit()

    [fila] = await _filas(session, table="audit.verifications")
    assert (fila.action, fila.record_id, fila.user_id, fila.user_name) == (
        "verify",
        vista.id,
        ana.id,
        ANA_NOMBRE,
    )


async def test_toda_tabla_que_aparece_es_auditable(
    session: AsyncSession, escrituras: Actividad
) -> None:
    tablas = {f.table_name for f in await _filas(session)}
    assert tablas <= AUDITABLE_TABLES, tablas - AUDITABLE_TABLES
    assert {
        "members.members",
        "plans.plans",
        "memberships.memberships",
        "payments.payments",
        "auth.users",
        "settings.settings_sections",
    } <= tablas
