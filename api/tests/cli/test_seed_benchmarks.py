"""`seed-benchmarks [--as]` (S8-A2, US-166, N-46; S8-D6, L-6). Rojo A2.

- Siembra los 12 benchmarks fijos con `ON CONFLICT (name_norm) DO NOTHING`; la segunda corrida no
  crea nada ni audita; no pisa una edición (ni un nombre que solo cambia en mayúsculas).
- La auditoría lleva una fila `insert` por benchmark CREADO (y el conteo que imprime lo es).
- Sin `--as` atribuye al usuario técnico (N-15); en producción exige `--as` de un admin activo.
- Una sola transacción: si una fila falla no queda ninguna.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app
from app.core.audit import TECHNICAL_COLUMNS, AuditEntry
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.modules.wods import seed as seed_module
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA, limpiar_tras_dos_sesiones
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]
_runner = CliRunner()
NOMBRES = {
    "Fran",
    "Grace",
    "Helen",
    "Diane",
    "Elizabeth",
    "Isabel",
    "Karen",
    "Annie",
    "Jackie",
    "Cindy",
    "Mary",
    "Murph",
}
TIPOS = {"time", "rounds_reps", "reps", "load"}


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)


async def _filas(fabrica: Fabrica) -> list[dict[str, Any]]:
    async with fabrica() as sesion:
        consulta = text("SELECT * FROM wods.benchmarks ORDER BY name_norm")
        return [dict(f) for f in (await sesion.execute(consulta)).mappings()]


async def _auditoria(fabrica: Fabrica) -> list[tuple[str, Any]]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT action, user_id FROM audit.audit_log "
                "WHERE table_name = 'wods.benchmarks' ORDER BY seq"
            )
        )
        return [(f[0], f[1]) for f in filas]


async def _admin(fabrica: Fabrica, role: str = "admin") -> Any:
    async with fabrica() as sesion:
        return await make_user(sesion, role=role, password=CLAVE_PRUEBA)


def _numeros(salida: str) -> list[int]:
    return [int(n) for n in re.findall(r"\b\d+\b", salida)]


def test_la_lista_fija_tiene_los_doce_con_tipo_valido() -> None:
    assert {b.name for b in seed_module.BENCHMARKS} == NOMBRES
    assert len(seed_module.BENCHMARKS) == 12
    assert {b.score_type for b in seed_module.BENCHMARKS} <= TIPOS
    assert all(0 < len(b.description) <= 2000 for b in seed_module.BENCHMARKS)


def test_el_comando_esta_registrado_y_aparece_en_la_ayuda() -> None:
    ayuda = _runner.invoke(app, ["--help"])
    assert ayuda.exit_code == 0 and "seed-benchmarks" in ayuda.output
    propia = _runner.invoke(app, ["seed-benchmarks", "--help"])
    assert propia.exit_code == 0 and "--as" in propia.output


async def test_dos_corridas_no_duplican(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    args = ["seed-benchmarks", "--as", admin.email]
    primera = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert primera.exit_code == 0, primera.output
    assert _numeros(primera.output) == [12], primera.output
    filas = await _filas(fabrica)
    assert {f["name"] for f in filas} == NOMBRES
    auditoria = await _auditoria(fabrica)
    segunda = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert segunda.exit_code == 0, segunda.output
    assert _numeros(segunda.output) == [0], segunda.output
    assert len(await _filas(fabrica)) == 12
    assert await _auditoria(fabrica) == auditoria


async def test_no_pisa_una_edicion(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with fabrica() as sesion:
        await sesion.execute(
            text(
                "INSERT INTO wods.benchmarks (id, created_by, name, name_norm, description, "
                "score_type) VALUES (gen_random_uuid(), :u, 'FRAN', 'fran', 'mía', 'reps')"
            ),
            {"u": SYSTEM_USER_ID},
        )
        await sesion.commit()
    resultado = correr(
        app, ["seed-benchmarks"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )
    assert resultado.exit_code == 0, resultado.output
    assert _numeros(resultado.output) == [11], resultado.output
    filas = {f["name_norm"]: f for f in await _filas(fabrica)}
    assert len(filas) == 12
    assert (filas["fran"]["name"], filas["fran"]["description"]) == ("FRAN", "mía")
    assert filas["fran"]["score_type"] == "reps"


async def test_on_conflict_do_nothing_y_conteo_de_creados_en_la_auditoria(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    correr(
        app,
        ["seed-benchmarks", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    auditoria = await _auditoria(fabrica)
    assert len(auditoria) == 12 and {a for a, _ in auditoria} == {"insert"}
    async with fabrica() as sesion:
        detalle = await sesion.scalar(
            text(
                "SELECT after->>'name_norm' FROM audit.audit_log "
                "WHERE table_name = 'wods.benchmarks' ORDER BY seq LIMIT 1"
            )
        )
    assert detalle in {n.lower() for n in NOMBRES}


async def test_as_atribuye_filas_y_auditoria(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    correr(
        app,
        ["seed-benchmarks", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert {f["created_by"] for f in await _filas(fabrica)} == {admin.id}
    assert {u for _, u in await _auditoria(fabrica)} == {admin.id}


async def test_sin_as_usa_system_user_id(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = correr(
        app, ["seed-benchmarks"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )
    assert resultado.exit_code == 0, resultado.output
    assert {f["created_by"] for f in await _filas(fabrica)} == {SYSTEM_USER_ID}
    assert {u for _, u in await _auditoria(fabrica)} == {SYSTEM_USER_ID}


async def test_en_produccion_exige_as_de_admin_activo(
    fabrica: Fabrica, settings_produccion: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    sin_as = correr(
        app, ["seed-benchmarks"], "production", base=settings_produccion, monkeypatch=monkeypatch
    )
    assert sin_as.exit_code == 2, sin_as.output
    coach = await _admin(fabrica, "coach")
    de_coach = correr(
        app,
        ["seed-benchmarks", "--as", coach.email],
        "production",
        base=settings_produccion,
        monkeypatch=monkeypatch,
    )
    assert de_coach.exit_code == 2, de_coach.output
    inexistente = correr(
        app,
        ["seed-benchmarks", "--as", "nadie@apex.co"],
        "production",
        base=settings_produccion,
        monkeypatch=monkeypatch,
    )
    assert inexistente.exit_code == 2, inexistente.output
    assert await _filas(fabrica) == []
    admin = await _admin(fabrica)
    ok = correr(
        app,
        ["seed-benchmarks", "--as", admin.email],
        "production",
        base=settings_produccion,
        monkeypatch=monkeypatch,
    )
    assert ok.exit_code == 0, ok.output
    assert len(await _filas(fabrica)) == 12


async def test_un_as_inexistente_en_dev_sale_con_2_sin_escribir(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = correr(
        app,
        ["seed-benchmarks", "--as", "nadie@apex.co"],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert r.exit_code == 2, r.output
    assert await _filas(fabrica) == []


async def test_una_transaccion(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La tercera fila rompe el CHECK de `score_type`: no queda ni la primera ni su auditoría."""
    rota = (
        *seed_module.BENCHMARKS[:2],
        seed_module.SeedBenchmark("Rota", "none", "tipo inválido"),
    )
    monkeypatch.setattr(seed_module, "BENCHMARKS", rota)
    r = correr(app, ["seed-benchmarks"], "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert r.exit_code != 0, r.output
    assert await _filas(fabrica) == []
    assert await _auditoria(fabrica) == []


async def test_la_auditoria_de_la_siembra_trae_la_fila_completa(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S8-A2b (L3): el `after` de cada alta lleva TODAS las columnas de la fila (como el del hook
    del ORM; solo se omiten las técnicas), no solo las que escribió la siembra."""
    admin = await _admin(fabrica)
    correr(
        app,
        ["seed-benchmarks", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    async with fabrica() as sesion:
        filas = (
            await sesion.execute(
                text("SELECT a.after FROM audit.audit_log a WHERE a.table_name = 'wods.benchmarks'")
            )
        ).all()
        real = (
            (await sesion.execute(text("SELECT * FROM wods.benchmarks LIMIT 1"))).mappings().one()
        )
    assert len(filas) == 12
    esperadas = set(real.keys()) - TECHNICAL_COLUMNS
    for (after,) in filas:
        assert set(after) == esperadas and after["id"] and after["created_by"]
