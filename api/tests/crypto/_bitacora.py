"""Datos de la bitácora y de los trabajos de criptografía para las pruebas de B2 (S6-B2, US-144).

`sembrar_ops` y `sembrar_jobs` insertan filas con instantes y ids fijos respecto a `T0` (el
reloj congelado de `tests/conftest.py`), de modo que el orden `at DESC, id DESC` y los rangos
`[from, to)` se puedan afirmar sin depender del reloj real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.crypto.models import CryptoJob, CryptoOp
from tests.conftest import T0
from tests.factories.triggers import disable_user_sql, rearm_always_sql

OPS_URL = "/api/v1/crypto/ops"
JOBS_URL = "/api/v1/crypto/jobs"

USUARIO_1 = UUID(int=101)
USUARIO_2 = UUID(int=102)
LLAVE_A = UUID(int=201)
LLAVE_B = UUID(int=202)
LOTE = UUID(int=301)
REGISTRO = UUID(int=401)


def iso(instante: datetime) -> str:
    """Instante UTC como lo envía el front en `from`/`to`."""
    return instante.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OpsSembradas:
    """Ids de las seis operaciones, por número (1 a 6), y el orden esperado de la lista."""

    ids: dict[int, UUID]

    def orden_por_defecto(self) -> list[UUID]:
        """`at DESC, id DESC`: 5 (T0-1d), 4 y 3 (T0-3d, empate: gana el id mayor), 2, 1, 6."""
        return [self.ids[n] for n in (5, 4, 3, 2, 1, 6)]

    def de(self, *numeros: int) -> set[UUID]:
        return {self.ids[n] for n in numeros}


async def vaciar_ops_de_arranque(session: AsyncSession) -> None:
    """Quita las filas `wrap` que `ensure_keys` deja al armar el bus de la prueba (a la hora
    real, no a `T0`): la bitácora de la prueba son solo las filas sembradas. Dentro del
    savepoint de la prueba, que se revierte."""
    for sql in (
        disable_user_sql("crypto.crypto_ops"),
        "DELETE FROM crypto.crypto_ops",
        rearm_always_sql("crypto.crypto_ops"),
    ):
        await session.execute(text(sql))


async def sembrar_ops(session: AsyncSession) -> OpsSembradas:
    """Seis filas de `crypto_ops` con ids `UUID(int=1001..1006)`.

    1 encrypt  member.document llave A usuario 1 ok     T0-10d
    2 decrypt  member.document llave A usuario 1 ok     T0-5d   record_id REGISTRO, key_version 1
    3 rotate   member.phone    llave B usuario 2 ok     T0-3d   lote
    4 rotate   member.phone    llave B usuario 2 error  T0-3d   lote (mismo instante que la 3)
    5 sign     audit.signature llave B usuario 2 ok     T0-1d
    6 export   sin clase, sin llave, usuario 1 ok       T0-400d
    """
    filas = [
        (1, "encrypt", "member.document", LLAVE_A, USUARIO_1, "ok", None, timedelta(days=10)),
        (2, "decrypt", "member.document", LLAVE_A, USUARIO_1, "ok", None, timedelta(days=5)),
        (3, "rotate", "member.phone", LLAVE_B, USUARIO_2, "ok", LOTE, timedelta(days=3)),
        (4, "rotate", "member.phone", LLAVE_B, USUARIO_2, "error", LOTE, timedelta(days=3)),
        (5, "sign", "audit.signature", LLAVE_B, USUARIO_2, "ok", None, timedelta(days=1)),
        (6, "export", None, None, USUARIO_1, "ok", None, timedelta(days=400)),
    ]
    await vaciar_ops_de_arranque(session)
    ids: dict[int, UUID] = {}
    for numero, verbo, clase, llave, usuario, resultado, lote, antes in filas:
        ids[numero] = UUID(int=1000 + numero)
        session.add(
            CryptoOp(
                id=ids[numero],
                at=T0 - antes,
                user_id=usuario,
                verb=verbo,
                data_class=clase,
                key_id=llave,
                key_version=1 if llave is not None else None,
                record_id=REGISTRO if numero == 2 else None,
                result=resultado,
                batch_id=lote,
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()
    return OpsSembradas(ids)


async def sembrar_muchas_ops(session: AsyncSession, cuantas: int) -> list[UUID]:
    """`cuantas` operaciones `encrypt` un minuto aparte (la más nueva primero en la lista)."""
    await vaciar_ops_de_arranque(session)
    ids = [UUID(int=5000 + n) for n in range(cuantas)]
    for n, uid in enumerate(ids):
        session.add(
            CryptoOp(
                id=uid,
                at=T0 - timedelta(minutes=n),
                user_id=USUARIO_1,
                verb="encrypt",
                data_class="member.document",
                result="ok",
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()
    return ids


@dataclass(frozen=True)
class JobsSembrados:
    ids: dict[int, UUID]

    def orden_por_defecto(self) -> list[UUID]:
        """`created_at DESC, id DESC`: 5, 3, 2, 1, 4."""
        return [self.ids[n] for n in (5, 3, 2, 1, 4)]

    def de(self, *numeros: int) -> set[UUID]:
        return {self.ids[n] for n in numeros}


ERROR_DEL_PROVEEDOR = "vault: permission denied token=s.SECRETO-DEL-PROVEEDOR"


async def sembrar_jobs(session: AsyncSession) -> JobsSembrados:
    """Cinco trabajos con ids `UUID(int=2001..2005)` (sin chocar con `uq_crypto_jobs_in_progress`).

    1 rotate           member.document done    200/200  -> 100  creado T0-3d
    2 reencrypt        member.phone    running   3/1    ->  33  creado T0-2d
    3 migrate_provider sin clase       done      9/9    -> 100  creado T0-1d
    4 rewrap           sin clase       failed    9/4    ->  44  creado T0-4d, con `error`
    5 rotate           member.email    pending   0/0    ->   0  creado T0-1h
    """
    filas = [
        (1, "rotate", "member.document", "done", 200, 200, timedelta(days=3), None),
        (2, "reencrypt", "member.phone", "running", 3, 1, timedelta(days=2), None),
        (3, "migrate_provider", None, "done", 9, 9, timedelta(days=1), None),
        (4, "rewrap", None, "failed", 9, 4, timedelta(days=4), ERROR_DEL_PROVEEDOR),
        (5, "rotate", "member.email", "pending", 0, 0, timedelta(hours=1), None),
    ]
    ids: dict[int, UUID] = {}
    for numero, tipo, clase, estado, total, hechos, antes, error in filas:
        ids[numero] = UUID(int=2000 + numero)
        session.add(
            CryptoJob(
                id=ids[numero],
                kind=tipo,
                data_class=clase,
                status=estado,
                total=total,
                done=hechos,
                started_at=None if estado == "pending" else T0 - antes,
                finished_at=T0 - antes if estado in ("done", "failed") else None,
                error=error,
                created_at=T0 - antes,
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()
    return JobsSembrados(ids)


async def sembrar_muchos_jobs(session: AsyncSession, cuantos: int) -> list[UUID]:
    """`cuantos` trabajos `done` un minuto aparte (el más nuevo primero en la lista)."""
    ids = [UUID(int=6000 + n) for n in range(cuantos)]
    for n, uid in enumerate(ids):
        session.add(
            CryptoJob(
                id=uid,
                kind="reencrypt",
                data_class="member.document",
                status="done",
                total=10,
                done=10,
                created_at=T0 - timedelta(minutes=n),
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()
    return ids
