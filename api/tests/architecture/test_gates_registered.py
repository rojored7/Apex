"""El gate de pagos queda registrado en cada proceso que carga los módulos (S3-B4, US-085; D1, L-5;
blueprint sección 7).

`memberships/service.py` registra `membership_payability` con `payments.service.set_membership_gate`
al importarse; `main.load_module_services()` lo importa en `create_app` (api), en el CLI
(`cli._load_module_services()`) y en `tests/conftest.py`. Se comprueba:
- tras `create_app(settings_prueba, run_migrations_on_startup=False)` y tras
  `cli._load_module_services()`, `payments.service.membership_gate()` es
  `memberships.service.membership_payability`;
- en un proceso limpio (`python -I`): importar solo `payments.service` no deja gate (payments no
  importa memberships, D1); tras `main.load_module_services()` o `cli._load_module_services()`
  el gate es el real;
- sin gate, `register` falla cerrado (`MembershipGateNotRegistered`, un `RuntimeError` que sale
  como 500 sin datos) y no deja pago ni auditoría; la prueba quita el gate y lo restaura.
Estas pruebas no usan `gate_doble` (riesgo 5 del sprint).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app
from app.cli import _load_module_services
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.main import create_app
from app.modules.memberships import service as memberships_service
from app.modules.payments import service as payments_service
from app.modules.payments.exceptions import MembershipGateNotRegistered
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan

API_ROOT = Path(app.__file__).resolve().parents[2]


def test_tras_create_app_el_gate_es_el_de_memberships(settings_prueba: Settings) -> None:
    create_app(settings_prueba, run_migrations_on_startup=False)
    assert payments_service.membership_gate() is memberships_service.membership_payability


def test_tras_cargar_los_services_del_cli_el_gate_es_el_de_memberships() -> None:
    _load_module_services()
    assert payments_service.membership_gate() is memberships_service.membership_payability


_SOLO_PAYMENTS = (
    "from app.modules.payments import service as p\n"
    "assert p.membership_gate() is None, 'payments no registra gate solo'\n"
)
_CON_MAIN = (
    _SOLO_PAYMENTS + "from app import main\n"
    "main.load_module_services()\n"
    "from app.modules.memberships import service as m\n"
    "assert p.membership_gate() is m.membership_payability\n"
)
_CON_CLI = (
    _SOLO_PAYMENTS + "from app import cli\n"
    "cli._load_module_services()\n"
    "from app.modules.memberships import service as m\n"
    "assert p.membership_gate() is m.membership_payability\n"
)


@pytest.mark.parametrize("programa", [_CON_MAIN, _CON_CLI], ids=["main", "cli"])
def test_en_un_proceso_limpio_el_gate_lo_registra_la_carga_de_modulos(programa: str) -> None:
    resultado = subprocess.run(  # noqa: S603 - programa fijo de la prueba
        [sys.executable, "-I", "-c", programa],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]


async def test_sin_gate_register_falla_cerrado_no_escribe_y_se_restaura(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan)
    membresia_id = membresia.id
    anterior = payments_service.membership_gate()
    assert anterior is memberships_service.membership_payability
    payments_service.set_membership_gate(None)
    try:
        with pytest.raises(MembershipGateNotRegistered), actor_scope(SYSTEM_USER_ID):
            await payments_service.register(
                session,
                membership_id=membresia_id,
                amount_cop=60_000,
                method="cash",
                role="admin",
            )
    finally:
        payments_service.set_membership_gate(anterior)
    assert payments_service.membership_gate() is memberships_service.membership_payability
    pagos = await session.scalar(
        text("SELECT count(*) FROM payments.payments WHERE membership_id = :m"),
        {"m": membresia_id},
    )
    auditoria = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE table_name = 'payments.payments'")
    )
    assert (pagos, auditoria) == (0, 0)
    assert issubclass(MembershipGateNotRegistered, RuntimeError)
