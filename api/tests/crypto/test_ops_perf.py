"""Rendimiento de `GET /crypto/ops` con 10.000 filas (S6-B2, V8). Marcada `perf`: no es gate.

Umbral del plan (V8): menos de 300 ms. Se mide la segunda peticion (la primera calienta). Imprime
tambien el `EXPLAIN (ANALYZE, BUFFERS)` de las consultas de `list_ops` (conteo y pagina).
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.crypto._bitacora import OPS_URL, sembrar_muchas_ops
from tests.crypto.conftest import ClienteAdmin
from tests.factories.explain import capturar_sql, imprimir_explain

pytestmark = pytest.mark.perf

FILAS = 10_000
TOPE_MS = 300


async def test_la_bitacora_con_10_mil_filas_responde_en_menos_de_300_ms(
    session: AsyncSession, cliente_admin: ClienteAdmin
) -> None:
    await sembrar_muchas_ops(session, FILAS)
    await session.execute(text("ANALYZE crypto.crypto_ops"))
    primera = await cliente_admin.get(OPS_URL)  # calentamiento
    assert primera.status_code == 200, primera.text

    with capturar_sql(session, "crypto_ops") as capturadas:
        inicio = time.perf_counter()
        r = await cliente_admin.get(OPS_URL)
        ms = (time.perf_counter() - inicio) * 1000

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["total"], len(cuerpo["items"])) == (FILAS, 25)
    print(f"\nGET /crypto/ops con {FILAS} filas: {ms:.1f} ms (tope {TOPE_MS} ms)")
    await imprimir_explain(session, "list_ops", capturadas)
    assert ms < TOPE_MS, ms
