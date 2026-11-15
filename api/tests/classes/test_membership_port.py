"""El puerto REAL de `memberships` que `classes` usa en el check-in (S7-C2, US-160; S7-D6, S7-D14).

El puerto se registra al importar `memberships.service` (como el gate de pagos) y cierra la
ventana C1 a C2, en la que `POST /attendance` habría dado 500 `MembershipPortNotRegistered`.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.context import actor_scope
from app.main import create_app
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import AttendanceCreate
from tests.factories.classes import make_session
from tests.factories.members import make_member, make_members
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.factories.users import make_user

EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
API_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def _tiquetera(session: AsyncSession, socio: Any, restantes: int = 12) -> Any:
    plan = await make_plan(session, name=f"Tiquetera {uuid4()}", kind="classes", class_count=12)
    return await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 30),
        classes_remaining=restantes,
    )


async def _entrar(session: AsyncSession, actor: UUID, session_id: UUID, member_id: UUID) -> Any:
    with actor_scope(actor):
        datos = AttendanceCreate.model_validate({"session_id": session_id, "member_id": member_id})
        salida = await classes_service.check_in(session, datos, by=actor)
        await session.commit()
    return salida


async def test_bloquea_la_fila_antes_del_flush(session: AsyncSession) -> None:
    """La membresía se bloquea `FOR UPDATE` antes del primer `INSERT` auditado de la asistencia
    (orden de candados: socio, sesión, membresía, pago, cadena)."""
    coach = await make_user(session, role="coach")
    socio = await make_member(session)
    await _tiquetera(session, socio)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    sentencias: list[str] = []

    def anotar(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        sentencias.append(statement)

    destino = session.get_bind()
    event.listen(destino, "before_cursor_execute", anotar)
    try:
        await _entrar(session, coach.id, sesion.id, socio.id)
    finally:
        event.remove(destino, "before_cursor_execute", anotar)
    bloqueo = next(
        i for i, s in enumerate(sentencias) if "FOR UPDATE" in s and "memberships.memberships" in s
    )
    insercion = next(i for i, s in enumerate(sentencias) if "INSERT INTO classes.attendance" in s)
    assert bloqueo < insercion


async def test_dos_check_ins_del_mismo_socio_se_serializan(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """Dos tablets registran al mismo socio en dos sesiones a la vez: el candado del socio y el
    de la membresía los serializan y la tiquetera pierde exactamente dos clases."""
    una, otra = dos_sesiones
    coach = await make_user(una, role="coach")
    (socio,) = await make_members(una, 1)
    tiquetera = await _tiquetera(una, socio)
    primera = await make_session(una, starts_at=EN_VENTANA)
    segunda = await make_session(una, starts_at=datetime(2026, 10, 21, 15, 20, tzinfo=UTC))
    await asyncio.wait_for(
        asyncio.gather(
            _entrar(una, coach.id, primera.id, socio.id),
            _entrar(otra, coach.id, segunda.id, socio.id),
        ),
        timeout=30,
    )
    restantes = await una.scalar(
        text("SELECT classes_remaining FROM memberships.memberships WHERE id = :i"),
        {"i": tiquetera.id},
    )
    assert restantes == 10


def test_create_app_deja_el_puerto_registrado(settings_prueba: Settings) -> None:
    """Hallazgo 10 de la crítica 1: tras el arranque (`create_app` importa los `service.py` de
    `main.MODULES`) el puerto no es `None`, así `POST /attendance` nunca da 500."""
    create_app(settings_prueba, run_migrations_on_startup=False)
    assert classes_service.membership_port() is not None


def test_el_arranque_en_un_proceso_limpio_registra_el_puerto() -> None:
    """Igual que arriba, en un subproceso sin nada importado de antemano."""
    codigo = (
        "from app.main import load_module_services; load_module_services(); "
        "from app.modules.classes import service; "
        "assert service.membership_port() is not None"
    )
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", codigo],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(API_ROOT / "src"), "SYSTEMROOT": "C:\\Windows"},
    )
    assert resultado.returncode == 0, resultado.stderr[-500:]
