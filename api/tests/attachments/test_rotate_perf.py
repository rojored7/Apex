"""Rotacion de 1.000 adjuntos sensibles de 100 KB y EXPLAIN de sus consultas (S6-R1, V8). `perf`.

Camino real de `rotate-key attachment.sensitive` y de la pantalla: `inventory.start_from_screen` +
`rotate_job.run_rotation` sobre el puerto `Reencryptor` de adjuntos, almacen local en `tmp_path`.
Los lotes son de 10 y no de 50 (S6-D111/S6-D116: los candados de fila duran lo que la E/S de cada
objeto); el plan decia 50, manda la decision.

Umbral: 120 s (0,12 s por adjunto). Justificacion: cada objeto son un descifrado y un cifrado
AES-GCM de 100 KB (menos de 2 ms) mas una lectura y una escritura de disco, y cada lote confirma
sus filas, su fila de `crypto_ops` y el avance del trabajo (100 confirmaciones); el orden de
magnitud esperado es de unos segundos y 120 s deja espacio a un disco lento de CI sin tapar un
costo cuadratico (que daria minutos).

Con 5 duenos de 200 adjuntos cada uno imprime ademas el `EXPLAIN (ANALYZE, BUFFERS)` de
`list_for_owner` (consulta de la pagina y conteo) y de `count_pending` (la de `Reencryptor`).
"""

# ruff: noqa: F811
from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.context import actor_scope
from app.core.crypto import rotate_job
from app.core.pagination import PageParams
from app.modules.attachments import service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import subir_real
from tests.attachments.conftest import Fabrica, almacen, por, real  # noqa: F401
from tests.crypto._rotacion_pantalla import MotorDedicado, motor_dedicado_contado  # noqa: F401
from tests.crypto.test_rotate_attachment_class import _iniciar, _job, puerto  # noqa: F401
from tests.factories import files
from tests.factories.explain import capturar_sql, imprimir_explain

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj")]

CANTIDAD = 1000
DUENOS = 5
TOPE_S = 120.0
PDF = files.pdf(100_000)


async def test_rotar_1000_adjuntos_sensibles_de_100_kb(
    real: Fabrica,
    almacen: LocalDiskStorage,
    por: UUID,
    puerto: Any,
    motor_dedicado_contado: MotorDedicado,
) -> None:
    duenos = [uuid4() for _ in range(DUENOS)]
    inicio_siembra = time.perf_counter()
    for n in range(CANTIDAD):
        await subir_real(real, por, "consent", PDF, dueno=duenos[n % DUENOS])
    siembra = time.perf_counter() - inicio_siembra
    inicio = await _iniciar(real, por)

    with actor_scope(por):
        arranque = time.perf_counter()
        await rotate_job.run_rotation(real, inicio.job_id)
        total = time.perf_counter() - arranque

    print(
        f"\nrotacion de {CANTIDAD} adjuntos de 100 KB (lotes de {rotate_job.BATCH_FILES}): "
        f"{total:.2f} s ({total / CANTIDAD * 1000:.1f} ms por adjunto; tope {TOPE_S:.0f} s); "
        f"siembra {siembra:.1f} s"
    )
    assert await _job(real, inicio.job_id) == ("done", CANTIDAD, CANTIDAD, None)
    assert total < TOPE_S, total

    async with real() as sesion:
        await sesion.execute(text("ANALYZE attachments.attachments"))
        with capturar_sql(sesion, "attachments.attachments") as capturadas:
            pagina = await service.list_for_owner(
                sesion, "members", duenos[0], PageParams(limit=25)
            )
        assert (pagina.total, len(pagina.items)) == (CANTIDAD // DUENOS, 25)
        await imprimir_explain(sesion, "list_for_owner", capturadas)

        with capturar_sql(sesion, "attachments.attachments") as capturadas:
            pendientes = await puerto.count_pending(sesion, inicio.new_key_id)
        assert pendientes == 0
        await imprimir_explain(sesion, "count_pending", capturadas)
