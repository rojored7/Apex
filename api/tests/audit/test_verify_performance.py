"""Rendimiento de la verificación (S4A-B3; S4A-D13, S4A-D47, contradicción 3). Marcada `perf`: no
es gate (`-m "not perf"`); se corre aparte con `uv run pytest -m perf
tests/audit/test_verify_performance.py -q` y sus tiempos van al cuaderno.

100.000 filas con `VERIFY_BATCH_SIZE = 500` (S4A-D120; antes 1000):
- la verificación completa tarda menos de 60 s;
- ningún bloque entre dos cesiones del loop (`_pause_between_batches`, el `sleep(0)` entre lotes)
  pasa de 100 ms: cota superior del bloque síncrono de un lote (incluye su lectura).
La medida decide `SYNC_VERIFY_MAX_ROWS` (si 100.000 caben en 20 s sube a 100.000; si 50.000 no
caben, baja a 20.000); el valor y los tiempos se anotan en el cuaderno.
"""

from __future__ import annotations

import time

import pytest

from app.core import audit_verify
from app.core.audit_verify import run_verification
from app.core.context import SYSTEM_USER_ID, actor_scope
from tests.audit.conftest import CadenaDePrueba

FILAS = 100_000
TOPE_TOTAL_S = 60.0
TOPE_BLOQUE_S = 0.100


@pytest.mark.perf
async def test_cien_mil_filas_en_menos_de_60_s_y_bloques_de_menos_de_100_ms(
    audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert audit_verify.VERIFY_BATCH_SIZE == 500
    await audit_chain_factory.make(FILAS)
    marcas: list[float] = []
    original = audit_verify._pause_between_batches

    async def medir() -> None:
        marcas.append(time.perf_counter())
        await original()
        marcas.append(time.perf_counter())

    monkeypatch.setattr(audit_verify, "_pause_between_batches", medir)

    inicio = time.perf_counter()
    with actor_scope(SYSTEM_USER_ID):
        resultado = await run_verification(
            audit_chain_factory.session, source="cli", by=SYSTEM_USER_ID
        )
    total = time.perf_counter() - inicio

    assert (resultado.ok, resultado.rows_checked) == (True, FILAS)
    assert len(marcas) >= 2 * (FILAS // audit_verify.VERIFY_BATCH_SIZE - 1)
    # Bloques: del inicio a la 1.ª pausa y de la salida de cada pausa a la entrada de la siguiente.
    bloques = [marcas[0] - inicio] + [
        marcas[i + 1] - marcas[i] for i in range(1, len(marcas) - 1, 2)
    ]
    peor = max(bloques)
    print(f"verificación de {FILAS} filas: {total:.2f} s; peor bloque {peor * 1000:.1f} ms")
    assert total < TOPE_TOTAL_S, total
    assert peor < TOPE_BLOQUE_S, peor
