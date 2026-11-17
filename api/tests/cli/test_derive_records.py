"""`derive-records [--as] [--dry-run]` (S9-B6; S9-D21, S9-D42; M-6). Rojo B6.

- Los resultados anteriores a v0.6 (sin récords) crean los que tocan, en orden de `wod_date` y con
  las MISMAS reglas puras; dos corridas seguidas: la segunda crea 0; `--dry-run` no escribe.
- Invariante M-6: tras cualquier corrida el vigente de cada objetivo es el máximo real de las
  marcas vigentes y validadas.
- Una transacción por socio bajo `lock_member`: «base ocupada» REAL se reintenta 3 veces y cuenta
  en `ocupados`; un fallo forzado cuenta en `fallidos` y revierte entero a ese socio; el tope de
  marcas alerta `athletes_restore_capped`. Con ocupados, fallidos o topes el código es 1.
- Auditoría: una fila `insert` por récord y una fila resumen con SOLO los conteos (sin ids de
  socio). No emite `PersonalRecordSet`.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal
from uuid import UUID

import pytest
from click.testing import Result
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.cli_ops import derive_records as comando
from app.core import events
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.locks import MEMBER_LOCK_NAMESPACE, MEMBER_LOCK_SQL
from app.modules.athletes import derive
from app.modules.athletes import service as athletes_service
from app.modules.athletes.events import PersonalRecordSet
from app.modules.results.events import WodResultValidated
from tests.athletes._apoyo_derivar import AlertasCapturadas, alertas, records_de, vigente_g  # noqa: F401
from tests.athletes._apoyo_invalidar import (
    anular_resultado,
    cargar,
    escena_serie,
    poner_en,
    wod_en,
)
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.members import make_members
from tests.factories.users import make_user
from tests.factories.wods import make_benchmark, make_wod
from tests.members.conftest import bus_confirmado  # noqa: F401  (llaves con commit real)
from tests.results._apoyo import Escena

REAL = pytest.mark.usefixtures("reloj", "bus_confirmado")
TABLA = "athletes.personal_records"
Pares = tuple[AsyncSession, AsyncSession]


@contextmanager
def _sin_derivar() -> Iterator[None]:
    """Como v0.5: los resultados se guardan sin que el handler de `athletes` derive nada."""
    suscritos = events._subscribers.get(WodResultValidated, [])
    quitados = [h for h in suscritos if h is derive.on_wod_result_validated]
    for handler in quitados:
        suscritos.remove(handler)
    try:
        yield
    finally:
        suscritos.extend(quitados)


async def _cargas(una: AsyncSession, e: Escena, kgs: list[int], dia0: int = 17) -> list[UUID]:
    """Un resultado de carga (en kg) por día, desde el 2026-10-`dia0`; devuelve sus ids."""
    ids: list[UUID] = []
    for i, kg in enumerate(kgs):
        wod = e.wod_id if i == 0 else await wod_en(una, e, f"2026-10-{dia0 + i:02d}", f"W{i}")
        ids.append((await cargar(una, e, wod, kg * 1000)).id)
    return ids


async def _otro_socio(una: AsyncSession, e: Escena) -> Escena:
    socio = (await make_members(una, 1))[0]
    return dataclasses.replace(e, socio=socio, socio_id=socio.id)


def _derivar(
    base: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    env: Literal["dev", "production"] = "dev",
) -> Result:
    return correr(app, ["derive-records", *args], env, base=base, monkeypatch=monkeypatch)


def _conteos(salida: str) -> dict[str, int]:
    pares = re.findall(r"(socios|creados|ocupados|fallidos) (\d+)", salida)
    return {clave: int(valor) for clave, valor in pares}


async def _auditoria(una: AsyncSession) -> list[dict[str, Any]]:
    await una.rollback()
    consulta = text(
        "SELECT action, record_id, after, user_id FROM audit.audit_log "
        "WHERE table_name = :t ORDER BY seq"
    )
    return [dict(f) for f in (await una.execute(consulta, {"t": TABLA})).mappings()]


async def _filas(una: AsyncSession, socio_id: UUID) -> list[dict[str, Any]]:
    await una.rollback()
    return await records_de(una, socio_id)


# Lo que crea ------------------------------------------------------------------------------------


@REAL
async def test_los_resultados_previos_crean_los_records_que_tocan(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 110, 120])
        await una.commit()
    assert await _filas(una, e.socio_id) == [], "como v0.5: sin récords"

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    assert _conteos(r.output) == {
        "socios": 1,
        "creados": 3,
        "ocupados": 0,
        "fallidos": 0,
    }
    filas = await _filas(una, e.socio_id)
    assert sorted(f["value_g"] for f in filas) == [100_000, 110_000, 120_000]
    assert vigente_g(filas) == 120_000
    assert {f["source"] for f in filas} == {"derived"}
    assert {f["created_by"] for f in filas} == {SYSTEM_USER_ID}, "sin --as: usuario técnico (N-15)"


@REAL
async def test_con_as_atribuye_los_records_a_esa_persona(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    admin = await make_user(una, role="admin", password=CLAVE_PRUEBA)
    with _sin_derivar():
        await _cargas(una, e, [100])
        await una.commit()

    r = _derivar(settings_prueba, monkeypatch, "--as", admin.email)

    assert r.exit_code == 0, r.output
    assert {f["created_by"] for f in await _filas(una, e.socio_id)} == {admin.id}


@REAL
async def test_benchmark_previo_crea_el_historico_y_el_vigente_es_el_mejor(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17", score_type="time")
    bench = await make_benchmark(una, e.coach, "Bench B6", "time")
    with _sin_derivar():
        for dia, segundos in ((18, 300), (19, 250), (20, 280)):
            wod = await make_wod(
                una,
                e.coach,
                list(e.movimientos),
                date=f"2026-10-{dia}",
                title=f"B{dia}",
                score_type="time",
                time_cap_s=600,
                benchmark_id=str(bench.id),
            )
            await poner_en(una, e, wod.id, seconds=segundos)
        await una.commit()

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    assert _conteos(r.output)["creados"] == 2
    filas = [f for f in await _filas(una, e.socio_id) if f["kind"] == "benchmark"]
    assert sorted(f["seconds"] for f in filas) == [250, 300], "el 280 no supera al 250"


@REAL
async def test_dos_corridas_la_segunda_crea_cero_y_no_audita_records(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 120])
        await una.commit()
    primera = _derivar(settings_prueba, monkeypatch)
    assert primera.exit_code == 0 and _conteos(primera.output)["creados"] == 2
    antes = await _filas(una, e.socio_id)
    inserts = [a for a in await _auditoria(una) if a["record_id"] is not None]

    segunda = _derivar(settings_prueba, monkeypatch)

    assert segunda.exit_code == 0, segunda.output
    assert _conteos(segunda.output)["creados"] == 0
    assert await _filas(una, e.socio_id) == antes
    assert [a for a in await _auditoria(una) if a["record_id"] is not None] == inserts


@REAL
async def test_dry_run_cuenta_pero_no_escribe_nada(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 120])
        await una.commit()
    auditoria = await _auditoria(una)

    r = _derivar(settings_prueba, monkeypatch, "--dry-run")

    assert r.exit_code == 0, r.output
    assert _conteos(r.output)["creados"] == 2, "informa lo que crearía"
    assert await _filas(una, e.socio_id) == []
    assert await _auditoria(una) == auditoria, "ni récords ni fila resumen"
    real = _derivar(settings_prueba, monkeypatch)
    assert _conteos(real.output)["creados"] == 2


# Producción -------------------------------------------------------------------------------------


@REAL
async def test_en_produccion_exige_as_de_un_admin(
    dos_sesiones: Pares, settings_produccion: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    coach = await make_user(una, role="coach", password=CLAVE_PRUEBA)
    admin = await make_user(una, role="admin", password=CLAVE_PRUEBA)
    with _sin_derivar():
        await _cargas(una, e, [100])
        await una.commit()

    sin = _derivar(settings_produccion, monkeypatch, env="production")
    de_coach = _derivar(settings_produccion, monkeypatch, "--as", coach.email, env="production")
    assert sin.exit_code == 2 and de_coach.exit_code == 2, (sin.output, de_coach.output)
    assert await _filas(una, e.socio_id) == []

    bien = _derivar(settings_produccion, monkeypatch, "--as", admin.email, env="production")
    assert bien.exit_code == 0, bien.output
    assert len(await _filas(una, e.socio_id)) == 1


# Invariante M-6 ---------------------------------------------------------------------------------


@REAL
async def test_120_de_v05_y_110_de_v06_deja_vigente_120(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [120])
        await una.commit()
    wod = await wod_en(una, e, "2026-10-19", "V06")
    await cargar(una, e, wod, 110_000)  # v0.6 en vivo: sin vigente, deriva el 110
    await una.commit()
    assert vigente_g(await _filas(una, e.socio_id)) == 110_000, "el primer RM de v0.6 es menor"

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    assert vigente_g(await _filas(una, e.socio_id)) == 120_000


@REAL
async def test_m6_tras_la_corrida_el_vigente_es_el_maximo_real(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Orden revuelto (100, 130, 90, 120) y una marca de 200 kg ANULADA: el máximo real es 130."""
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    admin = await make_user(una, role="admin", password=CLAVE_PRUEBA)
    with _sin_derivar():
        ids = await _cargas(una, e, [100, 130, 90, 120, 200])
        await una.commit()
        await anular_resultado(una, admin.id, ids[4])
        await una.commit()

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    filas = await _filas(una, e.socio_id)
    assert vigente_g(filas) == 130_000
    assert 200_000 not in {f["value_g"] for f in filas}
    segunda = _derivar(settings_prueba, monkeypatch)
    assert _conteos(segunda.output)["creados"] == 0
    assert vigente_g(await _filas(una, e.socio_id)) == 130_000


# Fallos (S9-D42) --------------------------------------------------------------------------------


@REAL
async def test_base_ocupada_se_reintenta_tres_veces_cuenta_y_sigue_con_los_demas(
    engine: AsyncEngine,
    dos_sesiones: Pares,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    una, _ = dos_sesiones
    a = await escena_serie(una, "2026-10-17")
    b = await _otro_socio(una, a)
    with _sin_derivar():
        await _cargas(una, a, [100])
        await cargar(una, b, a.wod_id, 90_000)
        await una.commit()
    intentos: list[UUID] = []
    original = comando.lock_member

    async def espiar(sesion: AsyncSession, member_id: UUID) -> None:
        intentos.append(member_id)
        await original(sesion, member_id)

    monkeypatch.setattr(comando, "lock_member", espiar)
    monkeypatch.setattr(comando, "BUSY_WAIT_S", 0.0)
    corta = settings_prueba.model_copy(update={"DB_LOCK_TIMEOUT_MS": 300})

    async with engine.connect() as ajena:
        retenido = {"m": str(a.socio_id), "ns": MEMBER_LOCK_NAMESPACE}
        await ajena.execute(text(MEMBER_LOCK_SQL), retenido)
        r = _derivar(corta, monkeypatch)
        await ajena.rollback()

    assert r.exit_code == 1, r.output
    assert _conteos(r.output) == {
        "socios": 2,
        "creados": 1,
        "ocupados": 1,
        "fallidos": 0,
    }
    assert intentos.count(a.socio_id) == 3, "tres intentos del socio ocupado"
    assert intentos.count(b.socio_id) == 1
    assert await _filas(una, a.socio_id) == [], "el ocupado no quedó a medias"
    assert len(await _filas(una, b.socio_id)) == 1, "los demás se procesan"
    assert str(a.socio_id) not in r.output and str(b.socio_id) not in r.output


@REAL
async def test_fallo_forzado_revierte_a_ese_socio_entero_cuenta_y_sigue(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    malo = await escena_serie(una, "2026-10-17")
    bueno = await _otro_socio(una, malo)
    with _sin_derivar():
        await _cargas(una, malo, [100, 120])
        await cargar(una, bueno, malo.wod_id, 90_000)
        await una.commit()
    original = athletes_service.rederive_member

    async def falla_despues_de_escribir(
        sesion: AsyncSession, member_id: UUID, *, strict: bool
    ) -> Any:
        resultado = await original(sesion, member_id, strict=strict)
        if member_id == malo.socio_id:
            raise RuntimeError("fallo forzado")
        return resultado

    monkeypatch.setattr(athletes_service, "rederive_member", falla_despues_de_escribir)

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 1, r.output
    assert _conteos(r.output) == {
        "socios": 2,
        "creados": 1,
        "ocupados": 0,
        "fallidos": 1,
    }
    assert await _filas(una, malo.socio_id) == [], "ni la mitad de ese socio"
    assert len(await _filas(una, bueno.socio_id)) == 1
    assert str(malo.socio_id) not in r.output, "el resumen no lleva ids de socio"


@REAL
async def test_sin_tope_con_mas_marcas_que_la_pagina_deja_el_vigente_en_el_maximo_real(
    dos_sesiones: Pares,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    alertas: AlertasCapturadas,  # noqa: F811
) -> None:
    """S9-D62 B: el comando recorre TODAS las marcas por páginas (sin tope de 200 por objetivo ni
    de 2.000 por socio, sin alerta `athletes_restore_capped`): 5 marcas con página de 2."""
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 110, 150, 120, 90])
        await una.commit()
    monkeypatch.setattr(derive, "RESTORE_MAX_MARKS", 2)
    monkeypatch.setattr(derive, "REDERIVE_PAGE", 2)

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    assert "topes" not in r.output
    assert vigente_g(await _filas(una, e.socio_id)) == 150_000
    assert alertas.de("athletes_restore_capped") == []
    segunda = _derivar(settings_prueba, monkeypatch)
    assert segunda.exit_code == 0 and _conteos(segunda.output)["creados"] == 0


@REAL
async def test_el_simulacro_no_alerta_nunca(
    dos_sesiones: Pares,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    alertas: AlertasCapturadas,  # noqa: F811
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 110, 120])
        await una.commit()
    monkeypatch.setattr(derive, "RESTORE_MAX_MARKS", 1)
    monkeypatch.setattr(derive, "REDERIVE_PAGE", 1)

    r = _derivar(settings_prueba, monkeypatch, "--dry-run")

    assert r.exit_code == 0 and _conteos(r.output)["creados"] == 3, r.output
    assert alertas.recibidas == []


@REAL
async def test_no_deriva_records_de_socios_dados_de_baja(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    a = await escena_serie(una, "2026-10-17")
    baja = await _otro_socio(una, a)
    with _sin_derivar():
        await _cargas(una, a, [100])
        await cargar(una, baja, a.wod_id, 90_000)
        await una.commit()
    await una.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :m"), {"m": baja.socio_id}
    )
    await una.commit()

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0, r.output
    assert _conteos(r.output)["socios"] == 1 and _conteos(r.output)["creados"] == 1
    assert await _filas(una, baja.socio_id) == []
    assert len(await _filas(una, a.socio_id)) == 1


@REAL
async def test_fallo_de_conexion_imprime_los_conteos_parciales_y_aborta(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    a = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, a, [100])
        await una.commit()

    async def cae(*_a: Any, **_k: Any) -> Any:
        raise ConnectionRefusedError("sin conexión")

    monkeypatch.setattr(athletes_service, "rederive_member", cae)

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code != 0 and r.exception is not None
    assert _conteos(r.output) == {"socios": 1, "creados": 0, "ocupados": 0, "fallidos": 0}
    assert await _auditoria(una) == [], "sin fila resumen con la conexión caída"


# Auditoría y eventos ----------------------------------------------------------------------------


@REAL
async def test_audita_un_insert_por_record_y_una_fila_resumen_sin_ids_de_socio(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    admin = await make_user(una, role="admin", password=CLAVE_PRUEBA)
    with _sin_derivar():
        await _cargas(una, e, [100, 120])
        await una.commit()

    r = _derivar(settings_prueba, monkeypatch, "--as", admin.email)

    assert r.exit_code == 0, r.output
    filas = await _auditoria(una)
    por_record = [a for a in filas if a["record_id"] is not None]
    resumen = [a for a in filas if a["record_id"] is None]
    assert [a["action"] for a in por_record] == ["insert", "insert"]
    assert {a["user_id"] for a in filas} == {admin.id}
    assert len(resumen) == 1
    cuerpo = json.dumps(resumen[0]["after"], default=str)
    assert '"creados": 2' in cuerpo and '"socios": 1' in cuerpo
    assert str(e.socio_id) not in cuerpo


@REAL
async def test_no_emite_personal_record_set(
    dos_sesiones: Pares, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    una, _ = dos_sesiones
    e = await escena_serie(una, "2026-10-17")
    with _sin_derivar():
        await _cargas(una, e, [100, 120])
        await una.commit()
    emitidos: list[PersonalRecordSet] = []

    async def espia(evento: PersonalRecordSet, _sesion: AsyncSession) -> None:
        emitidos.append(evento)

    events.subscribe(PersonalRecordSet, espia)

    r = _derivar(settings_prueba, monkeypatch)

    assert r.exit_code == 0 and _conteos(r.output)["creados"] == 2, r.output
    assert emitidos == []


def test_el_comando_esta_registrado_y_aparece_en_la_ayuda() -> None:
    ayuda = CliRunner().invoke(app, ["derive-records", "--help"])
    assert ayuda.exit_code == 0
    assert "--as" in ayuda.output and "--dry-run" in ayuda.output
