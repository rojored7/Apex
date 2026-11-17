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
from app.modules.auth import kiosk as auth_kiosk
from app.modules.classes import service as classes_service
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


def test_tras_create_app_y_tras_el_cli_el_puerto_del_quiosco_es_el_de_classes(
    settings_prueba: Settings,
) -> None:
    """S7-C4d (L-2): `auth` no importa `classes`; el puerto lo registra `classes` al importarse."""
    create_app(settings_prueba, run_migrations_on_startup=False)
    assert auth_kiosk.kiosk_session_info_port() is classes_service.kiosk_session_info
    _load_module_services()
    assert auth_kiosk.kiosk_session_info_port() is classes_service.kiosk_session_info


_KIOSCO_LIMPIO = (
    "from app.modules.auth import kiosk as k\n"
    "assert k.kiosk_session_info_port() is None, 'auth no registra el puerto solo'\n"
    "from app import main\n"
    "main.load_module_services()\n"
    "from app.modules.classes import service as c\n"
    "assert k.kiosk_session_info_port() is c.kiosk_session_info\n"
)


def test_en_un_proceso_limpio_el_puerto_del_quiosco_lo_registra_la_carga_de_modulos() -> None:
    resultado = subprocess.run(  # noqa: S603 - programa fijo de la prueba
        [sys.executable, "-I", "-c", _KIOSCO_LIMPIO],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]


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


def test_tras_create_app_el_puerto_de_resultados_de_wods_es_el_de_results(
    settings_prueba: Settings,
) -> None:
    """S8-B1 (M-1 de la revisión de A3): no existe la clase provisional `NoResultsYet`; tras
    `create_app` el puerto es el de `results` y, sin puerto, `results_probe()` falla cerrado."""
    from app.modules.results import service as results_service
    from app.modules.wods import probe as wods_probe
    from app.modules.wods import service as wods_service
    from app.modules.wods.exceptions import ResultsProbeNotRegistered

    assert not hasattr(wods_service, "NoResultsYet") and not hasattr(wods_probe, "NoResultsYet")
    create_app(settings_prueba, run_migrations_on_startup=False)
    anterior = wods_service.current_results_probe()
    assert anterior is results_service.results_probe
    assert classes_service.results_port is not None
    wods_service.set_results_probe(None)
    try:
        with pytest.raises(ResultsProbeNotRegistered):
            wods_service.results_probe()
    finally:
        wods_service.set_results_probe(anterior)


def test_tras_cargar_los_services_del_cli_el_puerto_de_wods_es_el_de_results() -> None:
    from app.modules.results import service as results_service
    from app.modules.wods import service as wods_service

    _load_module_services()
    assert wods_service.current_results_probe() is results_service.results_probe


def test_la_clase_provisional_no_existe_en_el_codigo() -> None:
    """S8-B1: ningún archivo de `src` define ni nombra `NoResultsYet`."""
    nombrados = [
        p.relative_to(API_ROOT).as_posix()
        for p in (API_ROOT / "src").rglob("*.py")
        if "NoResultsYet" in p.read_text(encoding="utf-8")
    ]
    assert nombrados == []


_SOLO_WODS = chr(10).join(
    [
        "from app.modules.wods import service as w",
        "assert w.current_results_probe() is None, 'wods no registra puerto solo'",
    ]
)
_PUERTO_RESULTS = chr(10).join(
    [
        "from app.modules.results import service as r",
        "assert w.current_results_probe() is r.results_probe",
    ]
)
_PUERTOS_CON_MAIN = chr(10).join(
    [_SOLO_WODS, "from app import main", "main.load_module_services()", _PUERTO_RESULTS]
)
_PUERTOS_CON_CLI = chr(10).join(
    [_SOLO_WODS, "from app import cli", "cli._load_module_services()", _PUERTO_RESULTS]
)
_PUERTOS_CON_WORKER = chr(10).join(
    [
        _SOLO_WODS,
        "from app.worker import runtime",
        "runtime._install_listeners()",
        _PUERTO_RESULTS,
    ]
)


@pytest.mark.parametrize(
    "programa",
    [_PUERTOS_CON_MAIN, _PUERTOS_CON_CLI, _PUERTOS_CON_WORKER],
    ids=["main", "cli", "worker"],
)
def test_en_un_proceso_limpio_el_puerto_de_wods_lo_registra_la_carga_de_modulos(
    programa: str,
) -> None:
    """S8-B1: el puerto de `results` queda registrado en el api, el CLI y el worker."""
    resultado = subprocess.run(  # noqa: S603 - programa fijo de la prueba
        [sys.executable, "-I", "-c", programa],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]


def test_tras_create_app_el_puerto_de_records_de_wods_es_el_de_athletes(
    settings_prueba: Settings,
) -> None:
    """S9-B2 (S9-D9): tras `create_app` el puerto es el de `athletes`; sin puerto, falla cerrado."""
    from app.modules.athletes import service as athletes_service
    from app.modules.wods import service as wods_service
    from app.modules.wods.exceptions import RecordsProbeNotRegistered

    create_app(settings_prueba, run_migrations_on_startup=False)
    anterior = wods_service.current_records_probe()
    assert anterior is athletes_service.records_probe
    wods_service.set_records_probe(None)
    try:
        with pytest.raises(RecordsProbeNotRegistered):
            wods_service.records_probe()
    finally:
        wods_service.set_records_probe(anterior)


def test_tras_cargar_los_services_del_cli_el_puerto_de_records_es_el_de_athletes() -> None:
    from app.modules.athletes import service as athletes_service
    from app.modules.wods import service as wods_service

    _load_module_services()
    assert wods_service.current_records_probe() is athletes_service.records_probe


_SOLO_WODS_RECORDS = chr(10).join(
    [
        "from app.modules.wods import service as w",
        "assert w.current_records_probe() is None, 'wods no registra puerto solo'",
    ]
)
_PUERTO_ATHLETES = chr(10).join(
    [
        "from app.modules.athletes import service as a",
        "assert w.current_records_probe() is a.records_probe",
    ]
)
_RECORDS_CON_MAIN = chr(10).join(
    [_SOLO_WODS_RECORDS, "from app import main", "main.load_module_services()", _PUERTO_ATHLETES]
)
_RECORDS_CON_CLI = chr(10).join(
    [_SOLO_WODS_RECORDS, "from app import cli", "cli._load_module_services()", _PUERTO_ATHLETES]
)
_RECORDS_CON_WORKER = chr(10).join(
    [
        _SOLO_WODS_RECORDS,
        "from app.worker import runtime",
        "runtime._install_listeners()",
        _PUERTO_ATHLETES,
    ]
)


@pytest.mark.parametrize(
    "programa",
    [_RECORDS_CON_MAIN, _RECORDS_CON_CLI, _RECORDS_CON_WORKER],
    ids=["main", "cli", "worker"],
)
def test_en_un_proceso_limpio_el_puerto_de_records_lo_registra_la_carga_de_modulos(
    programa: str,
) -> None:
    """S9-B2: el puerto de `athletes` queda registrado en el api, el CLI y el worker."""
    resultado = subprocess.run(  # noqa: S603 - programa fijo de la prueba
        [sys.executable, "-I", "-c", programa],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]
