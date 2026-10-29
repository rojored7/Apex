"""`python -m app.cli [--db-timeouts off] verify-audit [--as] [--wait-timeout]` (S4A-B3, US-105;
S4A-D15, S4A-D43, S4A-D44, S4A-D53).

Contrato:
- cadena íntegra: sale 0 e imprime `Cadena íntegra...`; una fila alterada: sale 1 e imprime
  `Cadena rota en el registro seq <N>`;
- la entrada `verify` de la cadena y la fila de `audit.verifications` van a nombre de
  `SYSTEM_USER_ID` sin `--as` y del usuario de `--as` con él; `after.source == "cli"`;
- sale 2 sin tocar nada si: `--as` no existe; la base no responde (sin URL ni contraseña en la
  salida); `--wait-timeout` se agota con el candado tomado; `ENV=production` sin `--as`;
  `ENV=production` con `--db-timeouts off`;
- la salida nunca lleva valores de `before` ni `after` (la marca de la fábrica);
- la conexión del candado es `AUTOCOMMIT` y se invalida al terminar (espía), y el candado queda
  libre.
Datos con commit real (`fabrica_confirmada`): el CLI abre su propio engine sobre `db_test`.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.audit_verify import AuditVerification
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from tests.audit._apoyo import EspiaDeConexiones, candado_libre
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.audit_chain import MARCA_AFTER, last_seq, make_audit_chain, tamper_row
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

pytestmark = pytest.mark.usefixtures("reloj")


def _sin_excepcion(resultado: Any) -> None:
    assert resultado.exception is None or isinstance(resultado.exception, SystemExit), (
        resultado.exception
    )


def _limpia(salida: str) -> None:
    assert MARCA_AFTER not in salida
    assert '"before"' not in salida and '"after"' not in salida
    assert not UUID_RE.search(salida), salida


async def _cadena(fabrica: Fabrica, n: int = 60) -> int:
    """Agrega `n` filas tras la última confirmada; devuelve el `seq` previo (la base)."""
    async with fabrica() as sesion:
        base = await last_seq(sesion)
        await make_audit_chain(sesion, n)
    return base


async def _verificaciones(fabrica: Fabrica) -> list[AuditVerification]:
    async with fabrica() as sesion:
        return list(await sesion.scalars(select(AuditVerification)))


async def _entradas_verify(fabrica: Fabrica) -> list[AuditEntry]:
    async with fabrica() as sesion:
        return list(await sesion.scalars(select(AuditEntry).where(AuditEntry.action == "verify")))


def _con_puerto_cerrado(settings: Settings) -> Settings:
    partes = urlsplit(settings.DATABASE_URL.get_secret_value())
    cerrado = partes._replace(netloc=f"{partes.username}:{partes.password}@127.0.0.1:1")
    return settings.model_copy(update={"DATABASE_URL": SecretStr(urlunsplit(cerrado))})


# Resultado y código de salida --------------------------------------------------------------------


async def test_cadena_integra_sale_0_y_va_a_nombre_del_usuario_tecnico(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cadena(fabrica_confirmada)

    resultado = correr(app, ["verify-audit"], "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert "Cadena íntegra" in resultado.output
    _limpia(resultado.output)
    [fila] = await _verificaciones(fabrica_confirmada)
    assert (fila.ok, fila.source, fila.triggered_by) == (True, "cli", SYSTEM_USER_ID)
    [entrada] = await _entradas_verify(fabrica_confirmada)
    assert entrada.user_id == SYSTEM_USER_ID
    assert entrada.after is not None and entrada.after["source"] == "cli"
    assert entrada.table_name == "audit.verifications"


async def test_fila_42_alterada_sale_1_con_el_seq(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = await _cadena(fabrica_confirmada)
    async with fabrica_confirmada() as sesion:
        await tamper_row(sesion, base + 42, "after", {"n": "alterado", "marca": MARCA_AFTER})

    resultado = correr(app, ["verify-audit"], "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 1, resultado.output
    assert f"Cadena rota en el registro seq {base + 42}" in resultado.output
    _limpia(resultado.output)
    [fila] = await _verificaciones(fabrica_confirmada)
    assert (fila.ok, fila.broken_at_seq) == (False, base + 42)


async def test_as_atribuye_la_entrada_y_triggered_by_a_esa_persona(
    fabrica_confirmada: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with fabrica_confirmada() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    await _cadena(fabrica_confirmada, 10)
    args = ["verify-audit", "--as", usuario.email]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert usuario.email not in resultado.output
    [fila] = await _verificaciones(fabrica_confirmada)
    assert (fila.triggered_by, fila.created_by) == (usuario.id, usuario.id)
    [entrada] = await _entradas_verify(fabrica_confirmada)
    assert entrada.user_id == usuario.id


async def test_as_inexistente_sale_2_sin_verificar(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cadena(fabrica_confirmada, 10)
    args = ["verify-audit", "--as", "nadie@test.apex"]

    resultado = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert await _verificaciones(fabrica_confirmada) == []


# Salidas 2 ---------------------------------------------------------------------------------------


async def test_base_caida_sale_2_sin_la_url_ni_la_contrasena(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    caida = _con_puerto_cerrado(settings_prueba)
    url = caida.DATABASE_URL.get_secret_value()
    contrasena = urlsplit(url).password or "apex-test"

    resultado = correr(app, ["verify-audit"], "dev", base=caida, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    for prohibido in (url, contrasena, "127.0.0.1:1", "postgresql"):
        assert prohibido not in resultado.output, prohibido
    assert "Traceback" not in resultado.output


@pytest.mark.usefixtures("candado_tomado")
async def test_wait_timeout_agotado_con_el_candado_tomado_sale_2(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cadena(fabrica_confirmada, 10)
    inicio = time.monotonic()

    resultado = correr(
        app,
        ["verify-audit", "--wait-timeout", "1"],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert time.monotonic() - inicio < 10
    assert await _verificaciones(fabrica_confirmada) == []


async def test_en_produccion_sin_as_sale_2(
    fabrica_confirmada: Fabrica, settings_produccion: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cadena(fabrica_confirmada, 10)

    resultado = correr(
        app, ["verify-audit"], "production", base=settings_produccion, monkeypatch=monkeypatch
    )

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--as" in resultado.output
    assert await _verificaciones(fabrica_confirmada) == []


async def test_en_produccion_con_db_timeouts_off_sale_2(
    fabrica_confirmada: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with fabrica_confirmada() as sesion:
        usuario = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    await _cadena(fabrica_confirmada, 10)
    args = ["--db-timeouts", "off", "verify-audit", "--as", usuario.email]

    resultado = correr(app, args, "production", base=settings_produccion, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 2, resultado.output
    assert "--db-timeouts" in resultado.output
    assert await _verificaciones(fabrica_confirmada) == []


# Candado de la CLI (H-2) -------------------------------------------------------------------------


async def test_la_conexion_del_candado_es_autocommit_e_invalidada(
    fabrica_confirmada: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    espia_de_conexiones: EspiaDeConexiones,
) -> None:
    await _cadena(fabrica_confirmada, 10)

    resultado = correr(app, ["verify-audit"], "dev", base=settings_prueba, monkeypatch=monkeypatch)

    _sin_excepcion(resultado)
    assert resultado.exit_code == 0, resultado.output
    assert espia_de_conexiones.autocommit_invalidadas(), espia_de_conexiones
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())
