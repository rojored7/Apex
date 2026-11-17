"""La invalidación y la reposición bajo concurrencia real (S9-B5; S9-D7, S9-D11, S9-D30, S9-D42).

Dos conexiones con commit real y el bus de producción. Cada cruce del MISMO socio corre en los DOS
órdenes y el orden se FUERZA: la primera operación toma `lock_member` y NO confirma; la segunda
queda esperando (visible en `pg_locks`, `_esperando_candado`); al confirmar la primera, la segunda
sigue. Los dos órdenes deben dejar el mismo vigente, sin errores, sin dos récords del mismo
`(result_id, kind)` y con la cadena de auditoría íntegra. Valores a mano, en gramos enteros.

Cruces:
- anular el de 100 kg contra corregir el de 80 kg a 90 kg;
- invalidar un manual de 100 kg contra anular el resultado de 90 kg;
- invalidar un manual de 100 kg contra corregir el resultado de 90 kg a 95 kg;
- alta de un manual de 95 kg contra anular el resultado de 100 kg.
Además, una «base ocupada» REAL (55P03) en la reposición tras invalidar un manual sale como error
de «ocupado» y no confirma nada.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.audit_verify import run_verification
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import translate_busy
from app.modules.athletes import service
from app.modules.athletes.schemas import RecordIn
from app.modules.results import service as results_service
from app.modules.results.schemas import VoidIn
from tests.athletes._apoyo import alta_record, cuerpo_rm
from tests.athletes._apoyo_derivar import records_de
from tests.athletes._apoyo_invalidar import cargar, escena_serie, vivos, wod_en
from tests.athletes.test_void_concurrency import _esperando_candado
from tests.factories.users import make_user
from tests.results._apoyo import Escena

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")

Operacion = Callable[[AsyncSession], Awaitable[Any]]


@dataclass
class Cruce:
    """Una operación, quién la hace y su nombre (para los ids de la prueba)."""

    nombre: str
    actor: UUID
    correr: Operacion


async def _en_orden(
    engine: AsyncEngine,
    una: AsyncSession,
    otra: AsyncSession,
    primera: Cruce,
    segunda: Cruce,
) -> tuple[Any, Any]:
    """`primera` toma el candado del socio sin confirmar; `segunda` espera en `pg_locks`."""
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)
    with actor_scope(primera.actor):
        salida_a = await primera.correr(una)

    async def correr_segunda() -> Any:
        with actor_scope(segunda.actor):
            try:
                salida = await segunda.correr(otra)
                await otra.commit()
                return salida
            except BaseException:
                await otra.rollback()
                raise

    tarea = asyncio.create_task(correr_segunda())
    try:
        await _esperando_candado(engine, pid)
        assert not tarea.done(), f"{segunda.nombre} debe esperar a {primera.nombre}"
    finally:
        await una.commit()  # nunca dejar el candado tomado
    salida_b = await asyncio.wait_for(tarea, timeout=30)
    return salida_a, salida_b


async def _afirmar_integridad(una: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    filas = await records_de(una, member_id)
    for f in filas:
        assert (f["invalidated_at"] is None) == (f["invalidated_reason"] is None)
    pares = [(f["result_id"], f["kind"]) for f in filas if f["result_id"] is not None]
    assert len(pares) == len(set(pares)), "ningún (resultado, kind) con dos récords"
    with actor_scope(SYSTEM_USER_ID):
        vista = await run_verification(una, source="cli", by=SYSTEM_USER_ID)
    assert vista.ok is True
    return filas


def _anular(result_id: UUID, admin: UUID) -> Operacion:
    async def operacion(sesion: AsyncSession) -> Any:
        return await results_service.void_result(
            sesion, result_id, VoidIn(reason="Socio equivocado"), by=admin
        )

    return operacion


def _invalidar_manual(member_id: UUID, record_id: UUID, admin: UUID) -> Operacion:
    async def operacion(sesion: AsyncSession) -> Any:
        return await service.invalidate_manual_record(
            sesion, member_id, record_id, by=admin, role="admin"
        )

    return operacion


@dataclass
class Escenario:
    e: Escena
    admin: UUID
    cruces: dict[str, Cruce]
    esperado_g: list[int]


async def _escenario(nombre: str, una: AsyncSession) -> Escenario:
    e = await escena_serie(una, "2026-10-12")
    admin = (await make_user(una, role="admin")).id
    movimiento = e.movimientos[0]
    if nombre == "anular_vs_corregir":
        w2 = await wod_en(una, e, "2026-10-13", "W2")
        w3 = await wod_en(una, e, "2026-10-14", "W3")
        cien = await cargar(una, e, e.wod_id, 100_000)
        await cargar(una, e, w2, 60_000)
        ochenta = await cargar(una, e, w3, 80_000)
        cruces = {
            "a": Cruce("anular", admin, _anular(cien.id, admin)),
            "b": Cruce(
                "corregir",
                e.coach,
                lambda s: cargar(s, e, w3, 90_000, anterior_id=ochenta.id),
            ),
        }
        esperado = [90_000]
    elif nombre in {"manual_vs_anular", "manual_vs_corregir"}:
        manual = await alta_record(una, e.coach, e.socio_id, cuerpo_rm(movimiento, value_g=100_000))
        w2 = await wod_en(una, e, "2026-10-13", "W2")
        w3 = await wod_en(una, e, "2026-10-14", "W3")
        noventa = await cargar(una, e, w2, 90_000)
        if nombre == "manual_vs_anular":
            await cargar(una, e, w3, 70_000)
            otra_op = Cruce("anular", admin, _anular(noventa.id, admin))
            esperado = [70_000]
        else:
            otra_op = Cruce(
                "corregir", e.coach, lambda s: cargar(s, e, w2, 95_000, anterior_id=noventa.id)
            )
            esperado = [95_000]
        cruces = {
            "a": Cruce("invalidar manual", admin, _invalidar_manual(e.socio_id, manual.id, admin)),
            "b": otra_op,
        }
    else:  # alta_vs_anular
        cien = await cargar(una, e, e.wod_id, 100_000)

        async def alta(sesion: AsyncSession) -> Any:
            cuerpo = RecordIn.model_validate(cuerpo_rm(movimiento, value_g=95_000))
            return await service.add_record(sesion, e.socio_id, cuerpo, by=e.coach)

        cruces = {
            "a": Cruce("alta manual", e.coach, alta),
            "b": Cruce("anular", admin, _anular(cien.id, admin)),
        }
        esperado = [95_000]
    await una.commit()
    una.expunge_all()
    return Escenario(e, admin, cruces, esperado)


@pytest.mark.parametrize("orden", ["a_luego_b", "b_luego_a"])
@pytest.mark.parametrize(
    "nombre", ["anular_vs_corregir", "manual_vs_anular", "manual_vs_corregir", "alta_vs_anular"]
)
async def test_el_cruce_en_cada_orden_deja_el_mismo_vigente(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    nombre: str,
    orden: str,
) -> None:
    una, otra = dos_sesiones
    esc = await _escenario(nombre, una)
    primera, segunda = esc.cruces["a"], esc.cruces["b"]
    if orden == "b_luego_a":
        primera, segunda = segunda, primera
    socio_id = esc.e.socio_id

    await _en_orden(engine, una, otra, primera, segunda)

    filas = await _afirmar_integridad(una, socio_id)
    assert sorted(f["value_g"] for f in vivos(filas)) == esc.esperado_g, filas


async def test_base_ocupada_al_reponer_tras_invalidar_un_manual_no_confirma_nada(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    """Un manual de 100 kg tapa un resultado de 60 kg. Otra conexión inserta, sin confirmar, un
    récord con el mismo `(result_id, kind)` del de 60: el `INSERT` de la reposición espera ese
    único y choca con `lock_timeout` (55P03 REAL): error de «ocupado» y NADA confirmado."""
    una, _otra = dos_sesiones
    e = await escena_serie(una, "2026-10-12")
    manual = await alta_record(una, e.coach, e.socio_id, cuerpo_rm(e.movimientos[0]))
    sesenta = await cargar(una, e, e.wod_id, 60_000)
    await una.commit()
    socio_id, manual_id, coach, movimiento, wod_id = (
        e.socio_id,
        manual.id,
        e.coach,
        e.movimientos[0],
        e.wod_id,
    )
    una.expunge_all()

    async with engine.connect() as ajena:
        await ajena.execute(
            text(
                "INSERT INTO athletes.personal_records (id, created_by, member_id, kind, "
                "movement_id, value_g, achieved_on, source, result_id, wod_id) VALUES "
                "(:i, :c, :m, 'rm', :mov, 60000, DATE '2026-10-12', 'derived', :r, :w)"
            ),
            {
                "i": uuid4(),
                "c": SYSTEM_USER_ID,
                "m": socio_id,
                "mov": movimiento,
                "r": sesenta.id,
                "w": wod_id,
            },
        )
        try:
            with actor_scope(coach):
                await una.execute(text("SET LOCAL lock_timeout = '300ms'"))
                with pytest.raises(DBAPIError) as info:
                    await service.invalidate_manual_record(
                        una, socio_id, manual_id, by=coach, role="admin"
                    )
        finally:
            await una.rollback()
            await ajena.rollback()

    assert translate_busy(info.value) is not None, "debe ser un error de «ocupado» (503 busy)"
    filas = await records_de(una, socio_id)
    assert [f["id"] for f in vivos(filas)] == [manual_id], "el manual sigue vivo: nada confirmado"
    assert all(f["result_id"] != sesenta.id for f in filas)
