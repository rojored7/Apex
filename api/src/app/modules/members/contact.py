"""Contacto para avisos (S4A-B6, US-077; S4A-D21, S4A-D50): archivo privado de `members`.

Solo lo importa `members`; los demás llegan por la fachada `members/service.py`. En el Sprint 4A
nadie fuera de `members` lo llama (`tests/architecture/test_contact_callers.py`,
`CONTACT_CALLERS` vacío); el Sprint 5 agrega solo `notifications.service`.

- `Contact(first_name, phone, email)`: valor congelado; `repr` y `str` nunca muestran el
  teléfono ni el correo (`field(repr=False)`). El llamador no lo persiste en claro ni lo
  serializa (`pickle`, `copy` y `json.dumps` fallan; `asdict`/`astuple` no se usan).
- `validate_purpose(purpose)`: solo `notify` y `auth_link`; cualquier otro valor (también
  `mask`, `reveal`, `export`, vacío o `None`) lanza `InvalidPurpose`.
- `contact_for_notification(session, member_id, purpose)`: ver su docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal, NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.modules.members.detail import MEMBERS_TABLE, _decrypt_fields
from app.modules.members.exceptions import InvalidPurpose, MemberNotContactable
from app.modules.members.models import Member

ContactPurpose = Literal["notify", "auth_link"]
CONTACT_PURPOSES: Final[frozenset[str]] = frozenset({"notify", "auth_link"})
CONTACT_FIELDS: Final = ("phone", "email")
CONTACT_NOT_SERIALIZABLE: Final = "Contact no se serializa: vive solo en memoria."


@dataclass(frozen=True, slots=True)
class Contact:
    """Nombre en claro (va en el leaderboard) y el teléfono y el correo descifrados (o `None`).

    Vive solo en memoria mientras se arma el aviso: no se serializa. `pickle`, `copy` y
    `deepcopy` lanzan `TypeError` (`__reduce__`), `json.dumps` sin ayuda también, y `vars` no
    aplica (`slots`). `dataclasses.asdict` y `astuple` no se pueden cerrar sin romper la dataclass:
    el llamador no los usa (revisión de B6, `security-reviewer` LOW).
    """

    first_name: str
    phone: str | None = field(repr=False)
    email: str | None = field(repr=False)

    def __str__(self) -> str:
        return repr(self)

    def __reduce__(self) -> NoReturn:
        raise TypeError(CONTACT_NOT_SERIALIZABLE)


def validate_purpose(purpose: object) -> ContactPurpose:
    """El propósito si es `notify` o `auth_link`; si no, `InvalidPurpose` (no lee nada)."""
    if purpose == "notify":
        return "notify"
    if purpose == "auth_link":
        return "auth_link"
    raise InvalidPurpose()


async def contact_for_notification(session: AsyncSession, member_id: UUID, purpose: str) -> Contact:
    """Teléfono y correo en claro del socio para un aviso, con rastro (S4A-D21).

    Orden: (1) `validate_purpose(purpose)` antes de leer la base; (2) el socio, o
    `MemberNotContactable` si no existe o tiene `deleted_at`, sin descifrar; (3) teléfono y
    correo por `detail._decrypt_fields` con el propósito (una fila `decrypt` por campo no nulo en
    `crypto_ops`, con el `record_id` del socio y el `batch_id` del `batch_scope` del llamador; sin
    `bus.batch`, que perdería el `record_id`); (4) por cada campo no nulo, una fila `reveal` en la
    auditoría con `after = {"field", "purpose"}`, `record_id` y `subject_member_id` del socio y
    el actor de `get_actor()`. Un campo vacío da `None`, no se descifra ni se audita.

    Regla de composición (S4A-D50): no pide `lock_member` ni `with_for_update` (no escribe filas de
    `members`), pero su primera fila de auditoría toma el candado de la cadena. Una unidad por
    socio: se llama en una transacción propia, o después de `lock_member` del MISMO socio y antes
    de cualquier escritura posterior que pida candados; nunca dentro de un bucle sobre varios
    socios en la misma transacción. Quien la llama CONFIRMA la transacción antes de enviar el
    aviso: un rollback borra las filas `reveal` pero no las `decrypt` (que `oplog` escribe en otra
    conexión), y un aviso enviado tras un rollback quedaría sin rastro en la auditoría.
    """
    proposito = validate_purpose(purpose)
    socio = await session.scalar(select(Member).where(Member.id == member_id))
    if socio is None or socio.deleted_at is not None:
        raise MemberNotContactable()
    claros = _decrypt_fields(socio, CONTACT_FIELDS, proposito)
    for campo in CONTACT_FIELDS:
        if campo in claros:
            await audit.record(
                session,
                action="reveal",
                table_name=MEMBERS_TABLE,
                record_id=socio.id,
                before=None,
                after={"field": campo, "purpose": proposito},
                subject_member_id=socio.id,
            )
    return Contact(
        first_name=socio.first_name,
        phone=_texto(claros.get("phone")),
        email=_texto(claros.get("email")),
    )


def _texto(claro: object) -> str | None:
    """El claro de un campo de texto como `str`; un campo vacío da `None`."""
    return None if claro is None else str(claro)
