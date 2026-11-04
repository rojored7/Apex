"""Flujo de rotación para las pruebas de B3b: lo que hará el comando `rotate-key`, escrito sobre
las funciones de `core/crypto/service.py` (`start_rotation`, `reencrypt_batch`, `finish_rotation`,
`fail_job`). Cada paso confirma en su propia sesión, como el comando.

Contrato que fijan las pruebas (el Verde debe cumplirlo; ver el cuaderno):
- el servicio llama al bus por atributo de módulo (`bus.decrypt`, `bus.encrypt`): así la falla
  inyectada de `test_rotate.py` lo alcanza;
- `reencrypt_batch` devuelve cuántas filas migró en ESE lote y `0` cuando ya no queda ninguna;
- `start_rotation` no recarga el keyring del proceso: quien rota llama `load_all` (`recargar`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import audit
from app.core.context import actor_scope
from app.core.crypto import bus, oplog, service
from app.core.crypto.keyring import current_keyring
from app.core.crypto.models import CryptoJob, CryptoOp
from tests.crypto._rotacion import CLASE_ROTADA, Fabrica
from tests.factories.triggers import disable_user_sql, rearm_always_sql

ACTOR = UUID(int=7)
MOTIVO = "rotación trimestral de prueba"
LOTE = 500


@dataclass
class Corrida:
    """Lo que dejó `rotar`: el job, los tamaños de lote y el resultado de `finish_rotation`."""

    job_id: UUID
    lotes: list[int] = field(default_factory=list)
    cerrada: bool | None = None


async def recargar(sesion: AsyncSession) -> None:
    """Como `load_all` del proceso que rota: el keyring conoce la llave nueva y los estados."""
    keyring = current_keyring()
    assert keyring.provider is not None
    await keyring.load_all(sesion, keyring.provider)


async def iniciar(fabrica: Fabrica, clase: str = CLASE_ROTADA, motivo: str = MOTIVO) -> UUID:
    """`start_rotation` en su transacción y recarga del keyring; devuelve el id del job."""
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            job = await service.start_rotation(sesion, clase, motivo, ACTOR)
            job_id = job.id
    async with fabrica() as sesion:
        await recargar(sesion)
    return job_id


async def un_lote(fabrica: Fabrica, job_id: UUID, tamano: int = LOTE) -> int:
    """Un `reencrypt_batch` en su transacción (confirma al salir; revierte si lanza)."""
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            job = await sesion.get(CryptoJob, job_id)
            assert job is not None
            return await service.reencrypt_batch(sesion, job, tamano)


async def cerrar(fabrica: Fabrica, job_id: UUID) -> bool:
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            job = await sesion.get(CryptoJob, job_id)
            assert job is not None
            return await service.finish_rotation(sesion, job)


async def rotar(
    fabrica: Fabrica, clase: str = CLASE_ROTADA, tamano: int = LOTE, motivo: str = MOTIVO
) -> Corrida:
    """Rotación completa: inicia (o reanuda), recifra de a `tamano` y cierra."""
    corrida = Corrida(await iniciar(fabrica, clase, motivo))
    while True:
        migradas = await un_lote(fabrica, corrida.job_id, tamano)
        corrida.lotes.append(migradas)
        if migradas < tamano:
            break
    corrida.cerrada = await cerrar(fabrica, corrida.job_id)
    return corrida


async def job_de(fabrica: Fabrica, job_id: UUID) -> CryptoJob:
    async with fabrica() as sesion:
        job = await sesion.get(CryptoJob, job_id)
        assert job is not None
        return job


async def vaciar_ops(engine: AsyncEngine) -> None:
    """Borra `crypto_ops` (las filas de la siembra no son lo que se mide)."""
    async with engine.begin() as conn:
        await conn.execute(text(disable_user_sql("crypto.crypto_ops")))
        await conn.execute(text("DELETE FROM crypto.crypto_ops"))
        await conn.execute(text(rearm_always_sql("crypto.crypto_ops")))
    oplog.reset_buffer()


def leer(blob: str, id_: UUID) -> str:
    """Descifra un blob de `document` con el keyring del proceso (`aad = id`)."""
    return bus.decrypt(blob, bus.aad_for(id_)).decode("utf-8")


def esperado(posicion: int) -> str:
    return f"doc-{posicion:05d}"


async def todo_se_lee(sesion: AsyncSession, ids: list[UUID], blobs: dict[UUID, str]) -> None:
    """Cada fila se descifra y vale lo sembrado (`filas_rotacion` numera por posición)."""
    for posicion, id_ in enumerate(ids):
        assert leer(blobs[id_], id_) == esperado(posicion)


async def ops_de(fabrica: async_sessionmaker[AsyncSession], verbo: str) -> list[CryptoOp]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text("SELECT id FROM crypto.crypto_ops WHERE verb = :v ORDER BY at, id"), {"v": verbo}
        )
        ids = [fila[0] for fila in filas.all()]
        return [op for i in ids if (op := await sesion.get(CryptoOp, i)) is not None]


async def registrar_blob(
    fabrica: Fabrica, blob: str, *, en: str = "after", tabla: str = "crypto.crypto_keys"
) -> None:
    """Una entrada de auditoría cuyo `before` o `after` contiene `blob` (como un `update`)."""
    valores = {"campo": blob}
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            await audit.record(
                sesion,
                action="update",
                table_name=tabla,
                record_id=None,
                before=valores if en == "before" else None,
                after=valores if en == "after" else None,
                user_id=ACTOR,
            )
