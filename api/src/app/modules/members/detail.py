"""Ficha del socio (S3-B9b, US-073; D20, D-4, M-2, N-01, N-20): archivo privado de `members`
(S3-B9a, D7, S3-D73). Solo lo importa `members`; los demás módulos llegan por la fachada
`members/service.py`.

- `_decrypt_fields(socio, campos, purpose) -> dict[str, object]`: descifra en memoria cada campo
  cifrado NO nulo con `types.reveal(socio, campo, purpose)` (una fila `decrypt` en `crypto_ops`
  con ese `purpose`, el `record_id` del socio y el actor). Es la única llamada a `types.reveal`
  fuera de `core/` (D-4, `tests/architecture/test_reveal_single_door.py`). Los nulos no se
  descifran ni dejan fila.
- `get(session, member_id) -> MemberDetailOut`: el socio (también dado de baja, N-20) o
  `MemberNotFound`; los cinco campos cifrados enmascarados con `mask` sobre los valores
  descifrados con `purpose="mask"` (D20, sin lote); estado, plan y fin de la membresía que decide
  por `memberships.service.status_for([id])` (import perezoso, G-03); `warnings == []`. Nunca
  audita ni deja filas `reveal`.
- `reveal(session, member_id, field, *, ip) -> RevealOut` (S3-B10, US-074; D19, M-1, L-12):
  descifra con `_decrypt_fields(socio, [field], "reveal")` y audita con
  `core.audit.record(action="reveal", table_name="members.members", after={"field", "ip"},
  subject_member_id=id)` en la misma transacción, sin el valor, sin evento y sin `commit()`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Final, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.crypto import types
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.models import ENCRYPTED_FIELDS, Member
from app.modules.members.rules import MaskField, MaskValue, mask
from app.modules.members.schemas import (
    EmergencyContactOut,
    MemberDetailOut,
    RevealField,
    RevealOut,
)

CAMPOS_CIFRADOS: Final[tuple[str, ...]] = ENCRYPTED_FIELDS
MASK_PURPOSE: Final = "mask"
REVEAL_PURPOSE: Final = "reveal"
MEMBERS_TABLE: Final = "members.members"
CONTACTO_ILEGIBLE: Final = "el contacto de emergencia guardado no tiene la forma esperada"
SIN_MEMBRESIA: Final = "none"  # blueprint B7: sin entrada en `status_for`, `none`


def _decrypt_fields(socio: Member, campos: Iterable[str], purpose: str) -> dict[str, object]:
    """Valores en claro de los `campos` no nulos del socio, con su tipo (`date`, mapeo). Cada
    uno deja una fila `decrypt` en `crypto_ops` con `purpose`; los nulos no se descifran."""
    return {
        campo: types.reveal(socio, campo, purpose)
        for campo in campos
        if getattr(socio, campo) is not None
    }


def _mascaras(socio: Member, claros: Mapping[str, object]) -> dict[str, str | None]:
    """Los cinco campos enmascarados en memoria desde los valores descifrados (D20)."""
    return {
        campo: mask(
            cast(MaskField, campo),
            cast(MaskValue, claros.get(campo)),
            document_type=socio.document_type if campo == "document" else None,
        )
        for campo in CAMPOS_CIFRADOS
    }


async def get(session: AsyncSession, member_id: UUID) -> MemberDetailOut:
    """La ficha enmascarada del socio (también dado de baja, N-20) o `MemberNotFound` sin
    descifrar nada. Nunca audita ni abre un lote (D20)."""
    socio = await session.scalar(select(Member).where(Member.id == member_id))
    if socio is None:
        raise MemberNotFound()
    mascaras = _mascaras(socio, _decrypt_fields(socio, CAMPOS_CIFRADOS, MASK_PURPOSE))
    # lazy: G-03 (members -> memberships)
    from app.modules.memberships import service as memberships_service

    membresia = (await memberships_service.status_for(session, [socio.id])).get(socio.id)
    return MemberDetailOut.model_validate(
        {
            "id": socio.id,
            "first_name": socio.first_name,
            "last_name": socio.last_name,
            "sex": socio.sex,
            "status": socio.status,
            "document_type": socio.document_type,
            **mascaras,
            "data_consent_at": socio.data_consent_at,
            "data_consent_version": socio.data_consent_version,
            "deleted_at": socio.deleted_at,
            "membership_status": SIN_MEMBRESIA if membresia is None else membresia.status,
            "plan_name": None if membresia is None else membresia.plan_name,
            "membership_end_date": None if membresia is None else membresia.end_date,
            "created_at": socio.created_at,
            "updated_at": socio.updated_at,
            "warnings": [],
        }
    )


def _revelado(claro: object) -> str | EmergencyContactOut | None:
    """El valor de `RevealOut`: la fecha como `AAAA-MM-DD`, el contacto como objeto y el texto
    tal como se guardó; un campo vacío da `None`."""
    if claro is None:
        return None
    if isinstance(claro, date):
        return claro.isoformat()
    if isinstance(claro, Mapping):
        try:
            return EmergencyContactOut.model_validate(claro)
        except ValidationError:
            # Revisión de seguridad de S3-B10 (LOW-2): el error de pydantic copia el claro en
            # `input_value`; sale uno opaco y sin la cadena de la excepción original.
            raise RuntimeError(CONTACTO_ILEGIBLE) from None
    return str(claro)


async def reveal(
    session: AsyncSession, member_id: UUID, field: RevealField, *, ip: str
) -> RevealOut:
    """El valor en claro de un campo cifrado del socio (también dado de baja, N-20), con una
    fila `reveal` en la auditoría (`after = {"field", "ip"}`, nunca el valor, L-12) y una
    `decrypt` con `purpose="reveal"` en `crypto_ops` (D19). Sin evento y sin `commit()` propio:
    el valor solo sale si la auditoría se escribió en la misma transacción. Un id inexistente da
    `MemberNotFound` sin descifrar ni auditar; un campo vacío da `None`, audita y no descifra."""
    socio = await session.scalar(select(Member).where(Member.id == member_id))
    if socio is None:
        raise MemberNotFound()
    claro = _decrypt_fields(socio, [field], REVEAL_PURPOSE).get(field)
    await audit.record(
        session,
        action="reveal",
        table_name=MEMBERS_TABLE,
        record_id=socio.id,
        before=None,
        after={"field": field, "ip": ip},
        subject_member_id=socio.id,
    )
    return RevealOut(field=field, value=_revelado(claro))
