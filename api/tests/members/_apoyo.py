"""Ayudas de las pruebas de socios (S2-B7).

- `entrada(**cambios)`: un `MemberCreate` validado con los valores de `KNOWN` (el correo ya
  normalizado por `EmailAddress`) y la autorización marcada.
- `crear(session, actor, data)`: `service.create` bajo `actor_scope(actor)` y commit (una
  petición, una transacción).
- `fila_socio`, `filas_crudas` y `operaciones`: lecturas con SQL crudo de `members.members` y de
  `crypto.crypto_ops`.
- `CAMPOS_DETALLE`: las claves exactas de `MemberDetailOut` (sin `notes`, M-5).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
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
        "created_at",
        "updated_at",
        "warnings",
    }
)

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
