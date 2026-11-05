"""Apoyo de B3b (rotación de llave y `retire-key`; S4B-D39, D40, D63, D86).

`tests/crypto/conftest.py` reexporta las fixtures; `tests/cli/conftest.py` también.

- `rotacion_lista`: entorno con commit real para `test_rotate*.py`: llaves creadas por
  `ensure_keys`, tabla `test_crypto.crypto_test_person` (modelo de prueba) y el registro
  apuntando la clase `member.document` a ESA tabla (`override_registry`); al salir vacía todo.
- `filas_rotacion(session, n=1200)`: inserta y confirma las filas.
- `candado_rotacion_tomado`: el candado de la clase tomado en OTRA conexión.
- `manifiesto_reciente(tmp_path)`, `escribir_manifiesto(...)`, `verify_reciente(session, actor)`:
  lo que `retire-key` exige. La edad se mide contra `current_clock()` (la prueba usa `reloj`,
  `T0`), no contra `now()` del servidor.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import oplog
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey, CryptoOp
from app.core.crypto.registry import REGISTRY, DataClassSpec, override_registry
from app.core.crypto.secret import Secret
from app.core.crypto.types import install_crypto_type_listeners
from tests.conftest import LIMPIAR_LLAVES
from tests.crypto.models_fixture import SCHEMA, CryptoTestPerson
from tests.factories.backup import make_backup_dir
from tests.factories.triggers import disable_user_sql, rearm_always_sql

CLASE_ROTADA = "member.document"
COLUMNA_ROTADA = f"{SCHEMA}.crypto_test_person.document"
FILAS_ROTACION = 1200
Fabrica = async_sessionmaker[AsyncSession]
BORRADOS = (
    ("crypto.crypto_ops", "DELETE FROM crypto.crypto_ops"),
    ("crypto.crypto_jobs", "DELETE FROM crypto.crypto_jobs"),
)
BLOBS_SQL = "SELECT id, document FROM test_crypto.crypto_test_person ORDER BY id"
INDICES_SQL = "SELECT id, document_idx FROM test_crypto.crypto_test_person ORDER BY id"


def registro_de_rotacion() -> dict[str, DataClassSpec]:
    """`REGISTRY` con `member.document` apuntando a la tabla de prueba."""
    return {
        **REGISTRY,
        CLASE_ROTADA: replace(REGISTRY[CLASE_ROTADA], columns=(COLUMNA_ROTADA,)),
    }


async def _limpiar_rotacion(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        for tabla, borrar in BORRADOS:
            await conn.execute(text(disable_user_sql(tabla)))
            await conn.execute(text(borrar))
            await conn.execute(text(rearm_always_sql(tabla)))
        for sql in LIMPIAR_LLAVES:
            await conn.execute(text(sql))


@pytest.fixture
async def rotacion_lista(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Fabrica]:
    """Fábrica de sesiones con commit real sobre un bus listo y la tabla de prueba vacía."""
    install_crypto_type_listeners()
    oplog.install_oplog_listeners()
    configure_keyring(None)
    await _limpiar_rotacion(engine)
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await conn.run_sync(lambda c: CryptoTestPerson.__table__.create(c))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    oplog.reset_buffer()
    db.configure_engine(
        engine
    )  # `fail_job` abre su propia transacción por el engine global (D139 #1)
    try:
        with override_registry(registro_de_rotacion()):
            async with fabrica() as sesion, sesion.begin():
                with actor_scope(SYSTEM_USER_ID):
                    await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)
            yield fabrica
    finally:
        db.configure_engine(None)
        oplog.reset_buffer()
        configure_keyring(None)
        await _limpiar_rotacion(engine)


async def filas_rotacion(session: AsyncSession, n: int = FILAS_ROTACION) -> list[UUID]:
    """Inserta y confirma `n` personas con `document` cifrado (`doc-00000`...) con la llave
    `active` del keyring del proceso; devuelve sus ids en orden de inserción."""
    ids: list[UUID] = []
    with actor_scope(SYSTEM_USER_ID):
        for desde in range(0, n, 300):
            lote = [
                CryptoTestPerson(name=f"p{i}", document=Secret.from_plain(f"doc-{i:05d}"))
                for i in range(desde, min(desde + 300, n))
            ]
            session.add_all(lote)
            await session.flush()
            ids.extend(p.id for p in lote)
        await session.commit()
    oplog.reset_buffer()
    return ids


async def llave_activa(session: AsyncSession, data_class: str = CLASE_ROTADA) -> CryptoKey:
    """La fila `encrypt` `active` de la clase."""
    return (
        await session.scalars(
            select(CryptoKey).where(
                CryptoKey.purpose == "encrypt",
                CryptoKey.data_class == data_class,
                CryptoKey.state == "active",
            )
        )
    ).one()


async def llaves_de(
    session: AsyncSession, purpose: str = "encrypt", data_class: str = CLASE_ROTADA
) -> list[CryptoKey]:
    """Todas las llaves de (purpose, clase) por versión."""
    filas = await session.scalars(
        select(CryptoKey)
        .where(CryptoKey.purpose == purpose, CryptoKey.data_class == data_class)
        .order_by(CryptoKey.version)
    )
    return list(filas)


async def blobs_de_rotacion(session: AsyncSession) -> dict[UUID, str]:
    """`{id: blob}` crudo de `document` (sin pasar por `Encrypted`)."""
    filas = await session.execute(text(BLOBS_SQL))
    return {i: b for i, b in filas.all()}


async def indices_de_rotacion(session: AsyncSession) -> dict[UUID, str | None]:
    filas = await session.execute(text(INDICES_SQL))
    return {i: b for i, b in filas.all()}


@pytest.fixture
async def candado_rotacion_tomado(engine: AsyncEngine) -> AsyncIterator[None]:
    """`pg_try_advisory_lock(hashtext('apex:rotate:member.document'))` tomado en OTRA conexión
    mientras dura la prueba."""
    async with engine.connect() as conexion:
        tomado = await conexion.scalar(
            text("SELECT pg_try_advisory_lock(hashtext('apex:rotate:member.document'))")
        )
        assert tomado is True
        try:
            yield
        finally:
            await conexion.execute(
                text("SELECT pg_advisory_unlock(hashtext('apex:rotate:member.document'))")
            )


def escribir_manifiesto(
    carpeta: Path,
    *,
    verify: str = "ok",
    con_firma: bool = True,
    antiguedad: timedelta = timedelta(hours=5),
) -> Path:
    """`latest.json` (y `latest.json.minisig` si `con_firma`) con `created_at = ahora - antiguedad`
    según `current_clock()`; devuelve la ruta de `latest.json`."""
    ahora = current_clock().now_utc()
    juego = make_backup_dir(carpeta, ahora, verify=verify, created_at=ahora - antiguedad)
    if con_firma:
        (carpeta / "latest.json.minisig").write_text("firma de prueba\n", encoding="utf-8")
    return juego.latest


@pytest.fixture
def manifiesto_reciente(tmp_path: Path) -> Path:
    """`latest.json` firmado, `verify == "ok"` y de hace 5 h (la prueba usa `reloj`)."""
    return escribir_manifiesto(tmp_path / "backups-retiro")


async def verify_reciente(
    session: AsyncSession,
    actor: UUID,
    *,
    edad: timedelta = timedelta(hours=1),
    resultado: str = "ok",
    verbo: str = "verify",
    data_class: str = "kek.backup",
) -> None:
    """Inserta y confirma una fila `crypto_ops` `verify` de `kek.backup` de `actor`, de hace `edad`
    según `current_clock()` (`SYSTEM_USER_ID` simula al job, no a una persona)."""
    session.add(
        CryptoOp(
            at=current_clock().now_utc() - edad,
            user_id=actor,
            verb=verbo,
            data_class=data_class,
            result=resultado,
            created_by=actor,
        )
    )
    await session.commit()


async def cuenta_de_ops(session: AsyncSession, verbo: str, data_class: str | None = None) -> int:
    consulta = select(func.count()).select_from(CryptoOp).where(CryptoOp.verb == verbo)
    if data_class is not None:
        consulta = consulta.where(CryptoOp.data_class == data_class)
    return int(await session.scalar(consulta) or 0)
