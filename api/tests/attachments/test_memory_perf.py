"""Memoria y tiempo de subir y descargar adjuntos de 5 MiB (S6-C1, S6-C4, V8). Marcada `perf`.

Pico medido con `tracemalloc` por operacion y, aparte (sin `tracemalloc`, que frena), el tiempo.
El plan (V8, paso 78) decia < 14 MiB; las decisiones S6-D110 (subida: 26 MiB) y S6-D115 (descarga:
35,5 MiB en el service) lo reemplazan porque el piso lo fija el blob textual de `core/crypto`.
Las pruebas fijan esos topes e imprimen tambien la cifra frente a los 14 MiB originales.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attachments import rules, service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import subir, subir_real
from tests.attachments.conftest import Fabrica
from tests.factories import files

pytestmark = pytest.mark.perf

MIB: Final = 1024 * 1024
PLAN_MIB: Final = 14
TOPE_SUBIDA: Final = 26 * MIB  # S6-D110
TOPE_DESCARGA: Final = 35.5 * MIB  # S6-D115


def _informe(operacion: str, pico: int, segundos: float, tope: float) -> None:
    print(
        f"\n{operacion}: pico {pico / MIB:.2f} MiB (plan < {PLAN_MIB} MiB, "
        f"tope decidido {tope / MIB:.1f} MiB); {segundos * 1000:.0f} ms"
    )


@pytest.mark.parametrize(
    ("kind", "datos"),
    [
        pytest.param("photo", files.jpeg(rules.ATTACHMENT_MAX_BYTES), id="foto"),
        pytest.param("consent", files.pdf(rules.ATTACHMENT_MAX_BYTES), id="sensible"),
    ],
)
async def test_subida_de_5_mib_pico_de_memoria_y_tiempo(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID, kind: str, datos: bytes
) -> None:
    inicio = time.perf_counter()
    await subir(listo, por, kind, datos)
    segundos = time.perf_counter() - inicio

    tracemalloc.start()
    try:
        base, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        await subir(listo, por, kind, datos)
        pico = tracemalloc.get_traced_memory()[1] - base
    finally:
        tracemalloc.stop()

    _informe(f"subida {kind} de {len(datos) // MIB} MiB", pico, segundos, TOPE_SUBIDA)
    assert pico < TOPE_SUBIDA, f"{pico / MIB:.2f} MiB"


async def test_descarga_de_un_sensible_de_5_mib_pico_de_memoria_y_tiempo(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    datos = files.pdf(rules.ATTACHMENT_MAX_BYTES)
    adjunto = await subir_real(real, por, "consent", datos)

    async with real() as sesion:
        inicio = time.perf_counter()
        cuerpo = await service.open_attachment(sesion, adjunto.id, by=por)
        segundos = time.perf_counter() - inicio
        assert cuerpo.data == datos

        tracemalloc.start()
        try:
            base = tracemalloc.get_traced_memory()[0]
            tracemalloc.reset_peak()
            await service.open_attachment(sesion, adjunto.id, by=por)
            pico = tracemalloc.get_traced_memory()[1] - base
        finally:
            tracemalloc.stop()

    _informe("descarga sensible de 5 MiB", pico, segundos, TOPE_DESCARGA)
    assert pico < TOPE_DESCARGA, f"{pico / MIB:.2f} MiB"
