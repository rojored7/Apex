"""Ayudas de las pruebas de socios (S2-B7).

- `entrada(**cambios)`: un `MemberCreate` validado con los valores de `KNOWN` (el correo ya
  normalizado por `EmailAddress`) y la autorización marcada.
- `crear(session, actor, data)`: `service.create` bajo `actor_scope(actor)` y commit (una
  petición, una transacción).
- `fila_socio`, `filas_crudas` y `operaciones`: lecturas con SQL crudo de `members.members` y de
  `crypto.crypto_ops`.
- `CAMPOS_DETALLE`: las claves exactas de `MemberDetailOut` (sin `notes`, M-5); desde S3-B9b
  con `plan_name` y `membership_end_date`.
- `CAMPOS_FILA` (S3-B9b): las claves exactas de `MemberRowOut` (N-01: nada sensible), con
  `membership_end_date` (D22, D35).
- `ruta_socio(member_id)` (S3-B9b): `GET /members/{member_id}`.
- S3-B10: `ruta_reveal` y `ruta_reactivar`; `auditoria_del_socio(session, member_id, action)`
  (filas de `audit.audit_log` del socio, en orden de `seq`); `descifrar(blob, member_id)` (el
  claro de un blob de la fila cruda, con `aad = id`; deja un `decrypt` sin propósito en el
  buffer: solo al final de una prueba); `peticion(session, actor)` (sesión vacía y actor, como
  una petición nueva).
- S4A-B6: `contar_crypto_ops(session, record_id, verb, purpose)`: filas de `crypto_ops` del
  registro con ese verbo y propósito.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.crypto import bus
from app.modules.members import service
from app.modules.members.schemas import MemberCreate, MemberDetailOut
from tests.factories.members import APELLIDO, KNOWN, NOMBRE

MEMBERS = "/api/v1/members"

CAMPOS_DETALLE = frozenset(
    {
        "id",
        "first_name",
        "last_name",
        "sex",
        "status",
        "document_type",
        "document",
        "phone",
        "email",
        "birth_date",
        "emergency_contact",
        "data_consent_at",
        "data_consent_version",
        "deleted_at",
        "membership_status",
        "plan_name",
        "membership_end_date",
        "created_at",
        "updated_at",
        "warnings",
    }
)

CAMPOS_FILA = frozenset(
    {
        "id",
        "first_name",
        "last_name",
        "sex",
        "status",
        "deleted_at",
        "membership_status",
        "plan_name",
        "membership_end_date",
    }
)


def ruta_socio(member_id: UUID | str) -> str:
    return f"{MEMBERS}/{member_id}"


# Máscaras de los valores de `KNOWN` (blueprint B7: `CC •••• 0304`, `••• ••• 4567`,
# `l•••@•••.co`, `••/••/1991`, `"Registrado"`).
MASCARAS_KNOWN = {
    "document": "CC •••• 2046",
    "phone": "••• ••• 4321",
    "email": "l•••@•••.co",
    "birth_date": "••/••/1991",
    "emergency_contact": "Registrado",
}


def cuerpo(**cambios: Any) -> dict[str, Any]:
    """Cuerpo JSON de `POST /members` con los valores de `KNOWN` y la autorización marcada."""
    valores: dict[str, Any] = {
        "first_name": NOMBRE,
        "last_name": APELLIDO,
        "document": KNOWN["document"],
        "phone": KNOWN["phone"],
        "email": KNOWN["email"],
        "birth_date": KNOWN["birth_date"].isoformat(),
        "sex": "f",
        "emergency_contact": dict(KNOWN["emergency_contact"]),
        "data_consent": True,
    }
    valores.update(cambios)
    return valores


def entrada(**cambios: Any) -> MemberCreate:
    return MemberCreate.model_validate(cuerpo(**cambios))


async def crear(session: AsyncSession, actor: UUID, data: MemberCreate) -> MemberDetailOut:
    with actor_scope(actor):
        salida = await service.create(session, data)
        await session.commit()
    return salida


async def fila_socio(session: AsyncSession, member_id: UUID) -> dict[str, Any]:
    fila = (
        (
            await session.execute(
                text("SELECT * FROM members.members WHERE id = :id"), {"id": member_id}
            )
        )
        .mappings()
        .one()
    )
    return dict(fila)


async def cuantos_socios(session: AsyncSession, *, document_idx: str | None = None) -> int:
    if document_idx is None:
        consulta = text("SELECT count(*) FROM members.members")
        return int(await session.scalar(consulta) or 0)
    consulta = text("SELECT count(*) FROM members.members WHERE document_idx = :i")
    return int(await session.scalar(consulta, {"i": document_idx}) or 0)


async def operaciones(session: AsyncSession, **filtros: object) -> list[dict[str, Any]]:
    """Filas de `crypto.crypto_ops` con igualdad en cada filtro (`verb`, `record_id`, ...)."""
    condiciones = " AND ".join(f"{campo} = :{campo}" for campo in filtros) or "true"
    consulta = text(f"SELECT * FROM crypto.crypto_ops WHERE {condiciones} ORDER BY at")  # noqa: S608
    return [dict(f) for f in (await session.execute(consulta, filtros)).mappings().all()]


# S3-B10 -----------------------------------------------------------------------------------


def ruta_reveal(member_id: UUID | str) -> str:
    return f"{ruta_socio(member_id)}/reveal"


def ruta_reactivar(member_id: UUID | str) -> str:
    return f"{ruta_socio(member_id)}/reactivate"


async def auditoria_del_socio(
    session: AsyncSession, member_id: UUID, action: str | None = None
) -> list[dict[str, Any]]:
    """Filas de `audit.audit_log` con `record_id = member_id` (y la acción, si se pide)."""
    if action is None:
        consulta = text("SELECT * FROM audit.audit_log WHERE record_id = :id ORDER BY seq")
        parametros: dict[str, Any] = {"id": member_id}
    else:
        consulta = text(
            "SELECT * FROM audit.audit_log WHERE record_id = :id AND action = :a ORDER BY seq"
        )
        parametros = {"id": member_id, "a": action}
    return [dict(f) for f in (await session.execute(consulta, parametros)).mappings().all()]


def descifrar(blob: str, member_id: UUID) -> str:
    """El claro (texto) de un blob `apx1.` de la fila cruda del socio."""
    return bus.decrypt(blob, bus.aad_for(member_id)).decode("utf-8")


@contextmanager
def peticion(session: AsyncSession, actor: UUID) -> Iterator[None]:
    """Una petición: la sesión sin objetos cargados y el actor fijado (el que llama confirma)."""
    session.expunge_all()
    with actor_scope(actor):
        yield


# S4A-B6 -----------------------------------------------------------------------------------


async def contar_crypto_ops(
    session: AsyncSession, record_id: UUID, verb: str, purpose: str | None
) -> int:
    """Filas de `crypto.crypto_ops` del registro con ese verbo y propósito (`None` = sin propósito).

    Cuenta filas, no la suma de `count`: una fila agregada por `bus.batch` pierde el `record_id`
    y no entra (S4A-D21 exige una fila por campo con el `record_id` del socio)."""
    consulta = text(
        "SELECT count(*) FROM crypto.crypto_ops WHERE record_id = :r AND verb = :v "
        "AND purpose IS NOT DISTINCT FROM CAST(:p AS text)"
    )
    return int(await session.scalar(consulta, {"r": record_id, "v": verb, "p": purpose}) or 0)
