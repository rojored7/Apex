"""Motor dedicado, candado y ciclo de vida de la tarea de rotación (S6-R1, US-145; S6-D61, E7).
Rojo R1.

- `rotation_engine(settings)` crea un `AsyncEngine` propio (`pool_size=1`, `max_overflow=0`),
  distinto
  del motor principal del api;
- durante una rotación el pool principal conserva sus conexiones: el candado de sesión
  `apex:rotate:<clase>` vive en una conexión del motor dedicado (no del principal) y se suelta al
  terminar; los lotes toman del pool principal, uno a la vez;
- la tarea de arranque (`app.state.rotation_task`) se cancela limpiamente en el `finally` del
  `lifespan`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.crypto import rotate_job
from app.main import create_app
from tests.crypto._rotacion import CLASE_ROTADA, filas_rotacion, llave_activa
from tests.crypto._rotacion_pantalla import MotorDedicado, Pantalla, PuertaDeLotes
from tests.crypto.conftest import limpiar_llaves_con_commit

pytestmark = pytest.mark.usefixtures("reloj")

CLAVE_CANDADO = f"apex:rotate:{CLASE_ROTADA}"
PROBAR_CANDADO = "SELECT pg_try_advisory_lock(hashtext(:clave))"
SOLTAR_CANDADO = "SELECT pg_advisory_unlock(hashtext(:clave))"


async def _candado_libre(motor: AsyncEngine) -> bool:
    """`True` si NADIE más tiene el candado (lo toma y lo suelta desde una conexión ajena)."""
    async with motor.connect() as conexion:
        tomado = bool(await conexion.scalar(text(PROBAR_CANDADO), {"clave": CLAVE_CANDADO}))
        if tomado:
            await conexion.scalar(text(SOLTAR_CANDADO), {"clave": CLAVE_CANDADO})
        return tomado


async def test_rotation_engine_crea_un_motor_propio_de_una_sola_conexion(
    settings_prueba: Settings, engine: AsyncEngine
) -> None:
    dedicado = rotate_job.rotation_engine(settings_prueba)

    try:
        assert isinstance(dedicado, AsyncEngine)
        assert dedicado is not engine
        assert dedicado.url.database == engine.url.database
        assert dedicado.sync_engine.pool.size() == 1  # type: ignore[attr-defined]
        assert dedicado.sync_engine.pool._max_overflow == 0  # type: ignore[attr-defined]
    finally:
        await dedicado.dispose()


async def test_el_candado_vive_en_la_conexion_dedicada_y_el_pool_principal_no_pierde_ninguna(
    pantalla: Pantalla,
    puerta: PuertaDeLotes,
    motor_dedicado_contado: MotorDedicado,
    engine: AsyncEngine,
) -> None:
    async with pantalla.fabrica() as sesion:
        await filas_rotacion(sesion, 1200)
        vieja = (await llave_activa(sesion)).id
    medidas: list[tuple[int, int, bool]] = []
    principal = engine.sync_engine.pool
    dedicado = motor_dedicado_contado.engine.sync_engine.pool

    async def medir(_numero: int) -> None:
        medidas.append(
            (
                principal.checkedout(),  # type: ignore[attr-defined]
                dedicado.checkedout(),  # type: ignore[attr-defined]
                await _candado_libre(engine),
            )
        )

    puerta.antes_de_cada_lote = medir
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    assert len(medidas) >= 3
    assert motor_dedicado_contado.pedidos >= 1
    for principal_en_uso, dedicado_en_uso, libre in medidas:
        assert principal_en_uso <= 1, medidas  # solo la sesión del lote en curso
        assert dedicado_en_uso == 1, medidas  # el candado de sesión
        assert libre is False, medidas  # nadie más puede tomar `apex:rotate:<clase>`
    assert dedicado.checkedout() == 0  # se suelta y se devuelve al terminar
    assert await _candado_libre(engine) is True
    assert principal.checkedout() == 0  # type: ignore[attr-defined]


async def test_el_candado_se_suelta_tambien_cuando_la_rotacion_falla(
    pantalla: Pantalla,
    puerta: PuertaDeLotes,
    motor_dedicado_contado: MotorDedicado,
    engine: AsyncEngine,
) -> None:
    async with pantalla.fabrica() as sesion:
        await filas_rotacion(sesion, 1200)
        vieja = (await llave_activa(sesion)).id
    real: Any = puerta.real

    async def revienta(session: AsyncSession, job: Any, tamano: int = 500) -> int:
        if puerta.contador == 2:
            raise RuntimeError("fallo de prueba")
        return int(await real(session, job, tamano))

    puerta.real = revienta
    puerta.abrir()

    await pantalla.rotar(vieja)
    await pantalla.terminar()

    assert await _candado_libre(engine) is True
    assert motor_dedicado_contado.engine.sync_engine.pool.checkedout() == 0  # type: ignore[attr-defined]


async def test_la_tarea_de_arranque_se_cancela_limpiamente_en_el_finally_del_lifespan(
    settings_prueba: Settings, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrato: `main.py` llama `rotate_job.resume_running_jobs(...)` por atributo de módulo, en
    una tarea guardada en `app.state.rotation_task` solo si el keyring quedó cargado, y la
    cancela y espera en el `finally` del `lifespan`."""
    arrancada = asyncio.Event()
    cancelaciones: list[str] = []

    async def colgada(_fabrica: Any) -> None:
        arrancada.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelaciones.append("cancelada")
            raise

    monkeypatch.setattr(rotate_job, "resume_running_jobs", colgada)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    tarea: asyncio.Task[Any] | None = None
    try:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(arrancada.wait(), 5)
            tarea = app.state.rotation_task
            assert tarea is not None and not tarea.done()
        assert tarea.done() and tarea.cancelled()
        assert cancelaciones == ["cancelada"]
        assert getattr(app.state, "rotation_task", None) in (None, tarea)
    finally:
        await limpiar_llaves_con_commit(engine)


async def test_el_cli_choca_con_el_candado_de_la_tarea_de_la_pantalla(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    """Un solo rotador por clase: mientras la tarea del api rota `member.document`, `rotate-key`
    (que usa `service.start_rotation`) recibe `RotationInProgress` y no crea nada."""
    from app.core.crypto import service
    from tests.crypto._rotacion_flujo import ACTOR

    async with pantalla.fabrica() as sesion:
        await filas_rotacion(sesion, 1200)
        vieja = (await llave_activa(sesion)).id
    assert (await pantalla.rotar(vieja)).status_code == 202
    await puerta.llega()

    async with pantalla.fabrica() as sesion, sesion.begin():
        with pytest.raises(service.RotationInProgress):
            await service.start_rotation(sesion, CLASE_ROTADA, "desde el cli", ACTOR)

    assert len(await pantalla.llaves()) == 2
    puerta.abrir()
    await pantalla.terminar()
