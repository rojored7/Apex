"""`python -m app.cli [--db-timeouts off] recompute-memberships [--date] [--simulate] [--as]`
(S4A-B2, US-094; S4A-D15, S4A-D48, S4A-D53, S4A-D63; enmienda E5).

Contrato:
- recalcula con `memberships.service.recompute_statuses` y `db.get_sessionmaker()`; sale con 0
  sin errores y con 1 si `busy_omitidos + errores > 0`; imprime solo los conteos (ningún UUID,
  nombre ni documento);
- `--as` con un usuario activo atribuye la auditoría a esa persona; sin `--as`, al usuario
  técnico; `--as` inexistente sale con 2 sin tocar nada;
- `--date` distinto de hoy sin `--simulate` sale con 2; con `--simulate`, `ENV=dev` y la base
  `apex_test` (o `*_sim`) corre con el reloj a las 12:00 de Bogotá de esa fecha, imprime
  `RELOJ SIMULADO: <fecha>` como primera línea y reclama `expirations_sim` en `worker.job_runs`
  (nunca la fila real); con la base `.../apex` o con `ENV=production` sale con 2 (E5);
- con `ENV=production` exige `--as` y rechaza `--db-timeouts off` (S4A-D53): salida 2.

`get_settings` del CLI devuelve `settings_prueba` (o la copia de producción) por `correr`; el reloj
es `reloj` (`2026-10-21T15:00Z`): el CLI corre en un hilo con copia del contexto y lo ve. La
membresía de prueba es `active` del 1 al 25 de octubre: el 21 faltan 4 días (pasa a `expiring`) y
el 1 de noviembre ya venció (pasa a `expired`).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.cli import app
from app.core import events
from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.jobs import JobRun
from app.modules.memberships import service as memberships_service
from app.modules.memberships.models import Membership
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA, limpiar_tras_dos_sesiones
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.memberships.conftest import bus_confirmado  # noqa: F401

Fabrica = async_sessionmaker[AsyncSession]
FUTURA = date(2026, 11, 1)
NOMBRE = "Eustaquia"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    """Fábrica con commit real; al salir borra lo que quedó (como `dos_sesiones`)."""
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)


@pytest.fixture
def documento() -> str:
    return unique_document()


@pytest.fixture
async def membresia(fabrica: Fabrica, documento: str) -> Membership:
    async with fabrica() as sesion:
        socio = await make_member(sesion, first_name=NOMBRE, document=documento)
        plan = await make_plan(sesion)
        return await make_membership(
            sesion, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 25)
        )


async def _estado(fabrica: Fabrica, membership_id: UUID) -> str | None:
    async with fabrica() as sesion:
        return await sesion.scalar(select(Membership.status).where(Membership.id == membership_id))


async def _actores(fabrica: Fabrica, membership_id: UUID) -> list[UUID]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry.user_id).where(
                AuditEntry.table_name == "memberships.memberships",
                AuditEntry.action == "update",
                AuditEntry.record_id == membership_id,
            )
        )
        return list(filas)


async def _corridas(fabrica: Fabrica) -> list[tuple[str, date]]:
    async with fabrica() as sesion:
        filas = await sesion.execute(select(JobRun.job_name, JobRun.run_date))
        return [(nombre, dia) for nombre, dia in filas]


def _con_base(settings: Settings, nombre: str) -> Settings:
    partes = urlsplit(settings.DATABASE_URL.get_secret_value())
    url = urlunsplit(partes._replace(path=f"/{nombre}"))
    return settings.model_copy(update={"DATABASE_URL": SecretStr(url)})


def _sin_excepcion(resultado: Any) -> None:
    """La salida viene del comando (`typer.Exit`), no de una excepción sin manejar."""
    assert resultado.exception is None or isinstance(resultado.exception, SystemExit), (
        resultado.exception
    )


def _solo_conteos(salida: str, *prohibidos: str) -> None:
    assert re.search(r"revisados\D+\d+", salida), salida
    assert not UUID_RE.search(salida), salida
    for valor in prohibidos:
        assert valor not in salida, valor


# Corrida normal --------------------------------------------------------------------------------


async def test_sin_errores_sale_0_actualiza_e_imprime_solo_conteos(
    fabrica: Fabrica,
    membresia: Membership,
    documento: str,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = correr(
        app, ["recompute-memberships"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert await _estado(fabrica, membresia.id) == "expiring"
    assert await _actores(fabrica, membresia.id) == [SYSTEM_USER_ID]
    _solo_conteos(resultado.output, NOMBRE, documento)
    assert "RELOJ SIMULADO" not in resultado.output
    assert await _corridas(fabrica) == []


async def test_con_un_error_de_socio_sale_1_con_los_conteos(
    fabrica: Fabrica,
    membresia: Membership,
    documento: str,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lanza(evento: Any, sesion: AsyncSession) -> None:
        raise RuntimeError(f"documento {documento}")

    events.subscribe(memberships_service.MembershipExpiring, lanza)  # `restaurar_bus` lo quita

    resultado = correr(
        app, ["recompute-memberships"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 1, resultado.output
    assert re.search(r"errores\D+1", resultado.output), resultado.output
    assert await _estado(fabrica, membresia.id) == "active"
    _solo_conteos(resultado.output, NOMBRE, documento)


# --as -------------------------------------------------------------------------------------------


async def test_as_con_un_usuario_activo_le_atribuye_la_auditoria(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with fabrica() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    args = ["recompute-memberships", "--as", usuario.email]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert await _actores(fabrica, membresia.id) == [usuario.id]
    assert usuario.email not in resultado.output


async def test_as_inexistente_sale_2_sin_tocar_nada(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["recompute-memberships", "--as", "nadie-recompute@test.apex"]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert await _estado(fabrica, membresia.id) == "active"
    assert await _actores(fabrica, membresia.id) == []


# --date y --simulate (S4A-D48, E5) --------------------------------------------------------------


async def test_date_distinta_de_hoy_sin_simulate_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["recompute-memberships", "--date", FUTURA.isoformat()]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--simulate" in resultado.output
    assert await _estado(fabrica, membresia.id) == "active"


async def test_date_con_simulate_en_dev_y_apex_test_simula_y_reclama_expirations_sim(
    fabrica: Fabrica,
    membresia: Membership,
    documento: str,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    reloj: FrozenClock,
) -> None:
    assert urlsplit(settings_prueba.DATABASE_URL.get_secret_value()).path == "/apex_test"
    args = ["recompute-memberships", "--date", FUTURA.isoformat(), "--simulate"]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert resultado.output.splitlines()[0] == f"RELOJ SIMULADO: {FUTURA.isoformat()}"
    assert await _estado(fabrica, membresia.id) == "expired"
    assert await _corridas(fabrica) == [("expirations_sim", FUTURA)]
    _solo_conteos(resultado.output, NOMBRE, documento)
    assert reloj.today_bogota() == date(2026, 10, 21)  # el reloj del proceso no cambió


@pytest.mark.parametrize("base", ["apex", "apex_vivo"])
async def test_date_con_simulate_contra_una_base_que_no_es_de_simulacion_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    base: str,
) -> None:
    args = ["recompute-memberships", "--date", FUTURA.isoformat(), "--simulate"]

    resultado = correr(
        app, args, "dev", base=_con_base(settings_prueba, base), monkeypatch=monkeypatch
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert await _estado(fabrica, membresia.id) == "active"
    assert await _corridas(fabrica) == []


async def test_date_con_simulate_en_produccion_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with fabrica() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    args = [
        "recompute-memberships",
        "--date",
        FUTURA.isoformat(),
        "--simulate",
        "--as",
        usuario.email,
    ]

    resultado = correr(app, args, "production", base=settings_produccion, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert await _estado(fabrica, membresia.id) == "active"


async def test_simulate_con_as_sale_2_sin_tocar_nada(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    """S4A-D89 (revisión de seguridad de B2, L-1): la corrida simulada se atribuye al usuario
    técnico; `--as` se rechaza en vez de ignorarse en silencio."""
    async with fabrica() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    args = [
        "recompute-memberships",
        "--date",
        FUTURA.isoformat(),
        "--simulate",
        "--as",
        usuario.email,
    ]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--simulate no admite --as" in resultado.output
    assert "RELOJ SIMULADO" not in resultado.output
    assert await _estado(fabrica, membresia.id) == "active"
    assert await _corridas(fabrica) == []
    assert await _actores(fabrica, membresia.id) == []


async def test_date_invalida_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["recompute-memberships", "--date", "2026-13-40", "--simulate"]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert await _estado(fabrica, membresia.id) == "active"


async def test_date_igual_a_hoy_sin_simulate_corre_normal(
    fabrica: Fabrica,
    membresia: Membership,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["recompute-memberships", "--date", "2026-10-21"]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert "RELOJ SIMULADO" not in resultado.output
    assert await _estado(fabrica, membresia.id) == "expiring"


# Producción (S4A-D53) ---------------------------------------------------------------------------


async def test_en_produccion_sin_as_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = correr(
        app,
        ["recompute-memberships"],
        "production",
        base=settings_produccion,
        monkeypatch=monkeypatch,
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--as" in resultado.output
    assert await _estado(fabrica, membresia.id) == "active"


async def test_en_produccion_con_db_timeouts_off_sale_2(
    fabrica: Fabrica,
    membresia: Membership,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with fabrica() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    args = ["--db-timeouts", "off", "recompute-memberships", "--as", usuario.email]

    resultado = correr(app, args, "production", base=settings_produccion, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--db-timeouts" in resultado.output
    assert await _estado(fabrica, membresia.id) == "active"


async def test_en_produccion_con_as_corre(
    fabrica: Fabrica,
    membresia: Membership,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    """Control: con `--as` y los tiempos de espera puestos, producción sí corre."""
    async with fabrica() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    args = ["recompute-memberships", "--as", usuario.email]

    resultado = correr(app, args, "production", base=settings_produccion, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert await _actores(fabrica, membresia.id) == [usuario.id]
