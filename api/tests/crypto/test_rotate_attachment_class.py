"""Rotación de `attachment.sensitive` con `run_rotation` (S6-R1, US-145; S6-D26, S6-D61, S6-D111,
S6-D116, E7). Rojo R1.

120 adjuntos sensibles (commit real, `real`): la rotación los recifra de a `BATCH_FILES` (10, igual
a `attachments.reencrypt.BATCH_SIZE`) por el puerto `Reencryptor`, 12 lotes con un `batch_id` por
lote; cada objeto descifra con la llave nueva y `key_id` queda al día. Un corte entre el objeto y
el `UPDATE` de `key_id` (lote que falla después de `put`) deja el objeto con la llave nueva y la
fila con la vieja: al reanudar se recifra sin pérdida.

Contradicción registrada: el plan decía lotes de 50 (paso 110); manda S6-D111 (10) por decisión del
orquestador (S6-D116).
"""

# ruff: noqa: F811
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from app.core.context import actor_scope
from app.core.crypto import inventory, reencryptor, rotate_job
from app.core.crypto.errors import CryptoError
from app.core.crypto.reencryptor import get_reencryptor
from app.modules.attachments import reencrypt, service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import subir_real
from tests.attachments.conftest import Fabrica, almacen, por, real  # noqa: F401
from tests.crypto._rotacion import llave_activa
from tests.crypto._rotacion_pantalla import MotorDedicado, motor_dedicado_contado  # noqa: F401
from tests.factories import files

pytestmark = pytest.mark.usefixtures("reloj")

CLASE = "attachment.sensitive"
CANTIDAD = 120
PDF = files.pdf(3000)


@pytest.fixture
def puerto() -> Any:
    reencryptor._reset_for_tests()
    service.register_reencryptor()
    registrado = get_reencryptor(CLASE)
    assert registrado is not None
    yield registrado
    reencryptor._reset_for_tests()


class Grabador:
    """Envuelve el puerto real: anota `batch_size` pedido y filas migradas por llamada; con
    `fallar_en` lanza DESPUÉS de que el lote escribió los objetos (corte simulado)."""

    def __init__(self, real_: Any) -> None:
        self.real = real_
        self.pedidos: list[int] = []
        self.migradas: list[int] = []
        self.fallar_en: int | None = None

    async def count_total(self, session: Any) -> int:
        return int(await self.real.count_total(session))

    async def count_pending(self, session: Any, active_key_id: UUID) -> int:
        return int(await self.real.count_pending(session, active_key_id))

    async def count_by_key(self, session: Any, key_id: UUID) -> int:
        return int(await self.real.count_by_key(session, key_id))

    async def reencrypt_batch(self, session: Any, active_key_id: UUID, batch_size: int) -> int:
        self.pedidos.append(batch_size)
        n = int(await self.real.reencrypt_batch(session, active_key_id, batch_size))
        self.migradas.append(n)
        if self.fallar_en == len(self.pedidos):
            raise CryptoError("put_failed", "corte simulado entre el objeto y el UPDATE")
        return n


async def _sembrar(real: Fabrica, por: UUID) -> None:
    for _ in range(CANTIDAD):
        await subir_real(real, por, "consent", PDF)


async def _activa(real: Fabrica) -> UUID:
    async with real() as sesion:
        return (await llave_activa(sesion, CLASE)).id


async def _iniciar(real: Fabrica, por: UUID) -> Any:
    activa = await _activa(real)
    with actor_scope(por):
        async with real() as sesion, sesion.begin():
            return await inventory.start_from_screen(sesion, activa, reason="adjuntos", by=por)


async def _filas(real: Fabrica) -> list[dict[str, Any]]:
    async with real() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT id, key_id, filename_random FROM attachments.attachments "
                "WHERE sensitive ORDER BY id"
            )
        )
        return [dict(f) for f in filas.mappings().all()]


def _llave_del_objeto(almacen: LocalDiskStorage, fila: dict[str, Any]) -> str:
    blob = (almacen.root / fila["filename_random"]).read_bytes().decode("ascii")
    return blob.split(".")[1]


async def _job(real: Fabrica, job_id: UUID) -> tuple[Any, ...]:
    async with real() as sesion:
        fila = await sesion.execute(
            text("SELECT status, done, total, error FROM crypto.crypto_jobs WHERE id = :i"),
            {"i": job_id},
        )
        return tuple(fila.one())


def test_batch_files_es_el_mismo_tope_que_el_del_puerto() -> None:
    assert rotate_job.BATCH_FILES == reencrypt.BATCH_SIZE == 10


async def test_rotar_120_adjuntos_sensibles_en_12_lotes_de_10(
    real: Fabrica,
    almacen: LocalDiskStorage,
    por: UUID,
    puerto: Any,
    motor_dedicado_contado: MotorDedicado,
) -> None:
    await _sembrar(real, por)
    grabador = Grabador(puerto)
    reencryptor._registered[CLASE] = grabador  # type: ignore[assignment]
    inicio = await _iniciar(real, por)

    with actor_scope(por):
        await rotate_job.run_rotation(real, inicio.job_id)

    assert [n for n in grabador.migradas if n] == [10] * 12
    assert set(grabador.pedidos) == {rotate_job.BATCH_FILES}
    assert await _job(real, inicio.job_id) == ("done", CANTIDAD, CANTIDAD, None)
    async with real() as sesion:
        assert await puerto.count_pending(sesion, inicio.new_key_id) == 0
        lotes = (
            await sesion.execute(
                text(
                    "SELECT batch_id, sum(count) AS n FROM crypto.crypto_ops WHERE "
                    "data_class = :c AND verb = 'encrypt' AND batch_id IS NOT NULL "
                    "GROUP BY batch_id"
                ),
                {"c": CLASE},
            )
        ).all()
    assert sorted(int(f.n) for f in lotes) == [10] * 12  # un batch_id por lote
    filas = await _filas(real)
    assert len(filas) == CANTIDAD
    for fila in filas:
        assert str(fila["key_id"]) == str(inicio.new_key_id)
        assert _llave_del_objeto(almacen, fila) == str(inicio.new_key_id)


async def test_un_corte_entre_el_objeto_y_el_update_se_recifra_en_el_lote_siguiente(
    real: Fabrica,
    almacen: LocalDiskStorage,
    por: UUID,
    puerto: Any,
    motor_dedicado_contado: MotorDedicado,
) -> None:
    await _sembrar(real, por)
    grabador = Grabador(puerto)
    grabador.fallar_en = 4
    reencryptor._registered[CLASE] = grabador  # type: ignore[assignment]
    inicio = await _iniciar(real, por)

    with actor_scope(por):
        await rotate_job.run_rotation(real, inicio.job_id)

    estado, hechas, *_ = await _job(real, inicio.job_id)
    assert (estado, hechas) == ("failed", 30)
    nueva = str(inicio.new_key_id)
    cortados = [
        f
        for f in await _filas(real)
        if _llave_del_objeto(almacen, f) == nueva and str(f["key_id"]) != nueva
    ]
    assert len(cortados) == 10  # objeto con la llave nueva y fila con la vieja

    grabador.fallar_en = None
    with actor_scope(por):
        async with real() as sesion, sesion.begin():
            reanudado = await inventory.start_from_screen(
                sesion, inicio.new_key_id, reason="de nuevo", by=por
            )
        assert reanudado.job_id == inicio.job_id
        await rotate_job.run_rotation(real, inicio.job_id)

    assert await _job(real, inicio.job_id) == ("done", CANTIDAD, CANTIDAD, None)
    async with real() as sesion:
        assert await puerto.count_pending(sesion, inicio.new_key_id) == 0
    for fila in await _filas(real):
        assert str(fila["key_id"]) == nueva and _llave_del_objeto(almacen, fila) == nueva


async def test_count_rows_by_key_suma_los_adjuntos_con_esa_llave(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID, puerto: Any
) -> None:
    """S6-D74 / S6-D107: `retire-key` cuenta `attachments.key_id` por el puerto real."""
    from app.core.crypto import service as servicio

    for _ in range(3):
        await subir_real(real, por, "consent", PDF)
    activa = await _activa(real)

    async with real() as sesion:
        filas = await servicio.count_rows_by_key(sesion, activa)

    assert filas["objetos"] == 3
