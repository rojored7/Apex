"""`gc.freeze()` al final del arranque (S4B-B4; S4B-D48). Marcada `perf`: no es gate
(`-m "not perf"`); se corre aparte: `uv run pytest -m perf tests/core/test_gc_after_startup.py -q`
y la medida va al cuaderno.

- tras el arranque del lifespan (`create_app` + `_startup`) `gc.get_freeze_count() > 0`: los objetos
  del arranque pasan a la generación permanente y el GC no los vuelve a escanear;
- durante 20 `POST /audit/verify` síncronos sobre 100.000 filas, la peor pausa de recolección de
  generación 2 (medida con `gc.callbacks`) es menor de 100 ms (plan B de 250 ms con decisión).

El `gc.freeze()` que deja el arranque se deshace en el `finally` (`gc.unfreeze()`), igual que en
`tests/audit/test_verify_performance.py`, para no contaminar otras pruebas.
"""

from __future__ import annotations

import gc
import time
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.main import create_app
from tests.audit._apoyo import VERIFY
from tests.audit.conftest import CadenaDePrueba, audit_chain_factory
from tests.conftest import Cabeceras, CrearUsuario

__all__ = ["audit_chain_factory"]

FILAS = 100_000
PETICIONES = 20
TOPE_PAUSA_GEN2_S = 0.100
MARGEN_FILAS = 300
"""`POST /audit/verify` es síncrono (200) solo si `max(seq) <= SYNC_VERIFY_MAX_ROWS` (100.000), y el
usuario de la prueba y cada verificación suman filas a la cadena: se llena hasta `FILAS` menos este
margen para que las 20 peticiones sigan por la vía síncrona (Verde S4B-B4, desviación 1)."""


@pytest.mark.perf
async def test_el_arranque_congela_los_objetos_con_gc_freeze(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    gc.unfreeze()
    gc.collect()
    antes = gc.get_freeze_count()  # sin gc.freeze() previo propio (otros plugins pueden dejar algo)
    orden: list[str] = []
    real_collect, real_freeze = gc.collect, gc.freeze

    def espia_collect(*args: Any, **kwargs: Any) -> int:
        orden.append("collect")
        return real_collect(*args, **kwargs)

    def espia_freeze() -> None:
        orden.append("freeze")
        real_freeze()

    monkeypatch.setattr(gc, "collect", espia_collect)
    monkeypatch.setattr(gc, "freeze", espia_freeze)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    try:
        async with app.router.lifespan_context(app):
            assert gc.get_freeze_count() > max(antes, 0)
            assert "freeze" in orden
            # S4B-D179: la última recolección es anterior al freeze (nada de basura congelada).
            assert orden.index("freeze") > 0 and orden[orden.index("freeze") - 1] == "collect"
    finally:
        gc.unfreeze()


@pytest.mark.perf
async def test_la_peor_pausa_de_gen2_en_20_verificaciones_de_100000_filas_es_menor_de_100_ms(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    await audit_chain_factory.make(FILAS - MARGEN_FILAS - await audit_chain_factory.last_seq())
    pausas: list[float] = []
    inicio: list[float] = []

    def medir(fase: str, info: dict[str, Any]) -> None:
        if info.get("generation") != 2:
            return
        if fase == "start":
            inicio.append(time.perf_counter())
        elif inicio:
            pausas.append(time.perf_counter() - inicio.pop())

    gc.collect()
    gc.freeze()  # lo que deja el arranque del api: el heap de pytest no cuenta
    gc.callbacks.append(medir)
    try:
        for i in range(PETICIONES):
            # 21 s: como mucho 3 por minuto y 20 en la hora, y el token de 15 min no vence (Verde,
            # desviación 2: con 1 min por petición la 16.ª vencía el token).
            reloj.set(reloj.now_utc() + timedelta(seconds=21))
            r = await app_http.post(VERIFY, headers=cabeceras(admin))
            assert r.status_code == 200, (i, r.text)
            assert r.json()["rows_checked"] >= FILAS - MARGEN_FILAS
    finally:
        gc.callbacks.remove(medir)
        gc.unfreeze()

    peor = max(pausas, default=0.0)
    print(f"{PETICIONES} verificaciones de {FILAS} filas: peor pausa gen 2 {peor * 1000:.1f} ms")
    assert peor < TOPE_PAUSA_GEN2_S, peor
