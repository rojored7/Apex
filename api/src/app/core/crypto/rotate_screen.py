"""Rotación desde la pantalla: validación y arranque en la transacción del request
(S6-R1, US-145; S6-D43, S6-D121, S6-D122).

`inventory.py` reexporta `RotationStarted`, `validate_rotation_request` y `start_from_screen`.
Sin `core/audit` ni `app.modules`; el `FOR UPDATE` de las tablas de llaves es solo de
`service.py`: aquí la exclusión la dan `uq_crypto_keys_active` y `uq_crypto_jobs_in_progress`
(un `IntegrityError` sale como 409 `rotation_running`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.crypto import service
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.service_pending import pending_total, require_rotatable
from app.core.errors import ConflictError, NotFoundError, ValidationFailed

ROTATE_CONFIRM_WORD: Final = "ROTAR"
OPEN_JOB_STATES: Final = ("pending", "running")
CUSTODY_KINDS: Final = ("migrate_provider", "rewrap")


@dataclass(frozen=True)
class RotationStarted:
    job_id: UUID
    new_key_id: UUID
    previous_key_id: UUID
    data_class: str = ""
    resumed: bool = False


def validate_rotation_request(reason: str, confirm: str) -> str:
    """Pura. `confirm` exactamente `ROTAR`; `reason` por `service.validate_reason` (una sola
    definición con el CLI: 1 a 200, sin control, correos ni números largos). Devuelve el motivo
    limpio. `ValidationFailed` con `field` `confirm` o `reason`, sin repetir el valor."""
    if confirm != ROTATE_CONFIRM_WORD:
        raise ValidationFailed(
            message="La confirmación no coincide con la palabra pedida.", field="confirm"
        )
    try:
        return service.validate_reason(reason)
    except ValueError as error:
        raise ValidationFailed(message=str(error), field="reason") from None


async def _load_key(session: AsyncSession, key_id: UUID) -> CryptoKey:
    consulta = (
        select(CryptoKey).where(CryptoKey.id == key_id).execution_options(populate_existing=True)
    )
    llave = (await session.execute(consulta)).scalar()
    if llave is None:
        raise NotFoundError("key_not_found", "No existe esa llave.")
    return llave


async def _job_of_class(session: AsyncSession, data_class: str, *estados: str) -> CryptoJob | None:
    consulta = (
        select(CryptoJob)
        .where(
            CryptoJob.kind == "rotate",
            CryptoJob.data_class == data_class,
            CryptoJob.status.in_(estados),
        )
        .order_by(CryptoJob.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(consulta)).scalar()


async def _previous_key_id(session: AsyncSession, llave: CryptoKey) -> UUID:
    anterior = await session.scalar(
        select(CryptoKey.id).where(
            CryptoKey.purpose == llave.purpose,
            CryptoKey.data_class == llave.data_class,
            CryptoKey.version == llave.version - 1,
        )
    )
    return anterior if anterior is not None else llave.id


async def _check_rotatable(session: AsyncSession, llave: CryptoKey) -> None:
    """Los 409 de la ruta, en el orden de la especificación (S6-D122)."""
    if llave.purpose != "encrypt":
        raise ConflictError("purpose_not_rotatable", "Esa llave no se rota desde aquí.")
    if llave.state != "active":
        raise ConflictError("key_not_active", "Solo se rota la llave activa.")
    await _check_custody_and_support(session, llave)
    if await _job_of_class(session, llave.data_class, *OPEN_JOB_STATES) is not None:
        raise ConflictError("rotation_running", "Ya hay una rotación en curso para esa clase.")


async def _check_custody_and_support(session: AsyncSession, llave: CryptoKey) -> None:
    """Sin migración o re-envoltura de la KEK abierta (S5-D190) y con clase rotable; lo comparten
    la rotación nueva y la reanudación."""
    custodia = await session.scalar(
        select(CryptoJob.id)
        .where(
            CryptoJob.kind.in_(CUSTODY_KINDS),
            CryptoJob.status.in_(("pending", "running", "failed")),
        )
        .limit(1)
    )
    if custodia is not None:
        raise ConflictError("rotation_running", "Hay una operación de custodia en curso.")
    try:
        require_rotatable(llave.data_class)
    except CryptoError:
        raise ConflictError(
            "rotation_not_supported", "Esa clase no admite rotación desde la pantalla."
        ) from None


async def _resume(session: AsyncSession, llave: CryptoKey, job: CryptoJob) -> RotationStarted:
    """Reanuda el job failed (o running huérfano) de la clase: mismo job_id, sin versión nueva."""
    await _check_custody_and_support(session, llave)
    try:
        job.status, job.error, job.finished_at = "running", None, None
        await session.flush()
    except IntegrityError:
        raise ConflictError("rotation_running", "Ya hay una rotación en curso.") from None
    previa = await _previous_key_id(session, llave)
    return RotationStarted(job.id, llave.id, previa, llave.data_class, resumed=True)


async def start_from_screen(
    session: AsyncSession, key_id: UUID, *, reason: str, by: UUID
) -> RotationStarted:
    """En la transacción del request: valida la llave, abre el job `running`, pasa la anterior a
    `decrypt_only` y crea la nueva `active` (sin recifrar nada). El job va ANTES de la anterior
    porque la guarda de `0024` comprueba al cierre que exista. Un job `failed` de la clase se
    reanuda, igual que uno `running` huérfano (mismo `job_id`, sin versión nueva). No audita
    (la puerta es del router)."""
    service.validate_reason(reason)
    llave = await _load_key(session, key_id)
    if llave.purpose == "encrypt" and llave.state == "active":
        # El router ya reservó el cupo: un running sin tarea (murió o el api se apagó) es huérfano
        abierto = await _job_of_class(session, llave.data_class, "failed", "running")
        if abierto is not None:
            return await _resume(session, llave, abierto)
    await _check_rotatable(session, llave)
    total = await pending_total(session, llave.data_class, uuid4())  # todo lo cifrado
    if total <= 0:
        raise ConflictError("nothing_to_rotate", "Esa clase no tiene datos que recifrar.")
    ahora = current_clock().now_utc()
    job = CryptoJob(
        kind="rotate",
        data_class=llave.data_class,
        status="running",
        total=total,
        done=0,
        started_at=ahora,
        created_by=by,
    )
    try:
        session.add(job)
        await session.flush()
        nueva, dek = await service._swap_key(session, llave, by)
    except IntegrityError:  # otro proceso ganó la carrera por el índice único de jobs o llaves
        raise ConflictError("rotation_running", "Ya hay una rotación en curso.") from None
    dek[:] = bytes(len(dek))
    return RotationStarted(job.id, nueva.id, llave.id, llave.data_class)
