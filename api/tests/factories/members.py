"""Fábrica de `members.members` (plan del Sprint 2, sección 2, bloque B7; US-069, US-031).

- `KNOWN`: valores conocidos de los cinco campos cifrados. Las pruebas de cifrado en reposo
  buscan estos valores (y su forma normalizada) en la fila cruda: no deben aparecer nunca.
- `make_member(session, **cambios)`: inserta un socio bajo `actor_scope(SYSTEM_USER_ID)` con los
  valores de `KNOWN` (o los de `cambios`), asigna siempre `Secret.from_plain(...)`, hace `flush`
  y confirma el savepoint. Necesita el bus listo (fixture `bus_listo`).
- `make_members(session, n)`: `n` socios con documentos únicos (sin teléfono ni correo, para
  que sus índices no choquen con nada).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Final
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.secret import Secret
from app.modules.members.models import ENCRYPTED_FIELDS, Member

KNOWN: Final[Mapping[str, Any]] = {
    "document": "7319582046",
    "phone": "+57 300 765 4321",
    "email": "Lucia.Gomez@Correo.co",
    "birth_date": date(1991, 7, 23),
    "emergency_contact": {"name": "Rosa", "phone": "3115550199"},
}
"""Valores en claro conocidos; ninguna columna de la tabla debe contenerlos."""

KNOWN_NORMALIZED: Final[tuple[str, ...]] = (
    "7319582046",
    "+57 300 765 4321",
    "573007654321",
    "3007654321",
    "Lucia.Gomez@Correo.co",
    "lucia.gomez@correo.co",
    "1991-07-23",
    "Rosa",
    "3115550199",
)
"""`KNOWN` en claro y normalizado (N-02) como texto: lo que no puede aparecer en reposo."""

NOMBRE: Final = "Lucía"
APELLIDO: Final = "Gómez"


def unique_document() -> str:
    """Documento de 12 dígitos distinto en cada llamada (sin relación con `KNOWN`)."""
    return f"9{uuid4().int % 10**11:011d}"


def _valor(campo: str, valor: object) -> object:
    if campo in ENCRYPTED_FIELDS and valor is not None and not isinstance(valor, Secret):
        return Secret.from_plain(valor)  # type: ignore[arg-type]
    return valor


async def make_member(session: AsyncSession, **cambios: Any) -> Member:
    """Inserta un `Member` con `KNOWN` (o `cambios`) bajo `SYSTEM_USER_ID` y confirma."""
    valores: dict[str, Any] = {
        "first_name": NOMBRE,
        "last_name": APELLIDO,
        "document_type": "CC",
        "status": "active",
        **KNOWN,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    socio = Member(**{campo: _valor(campo, valor) for campo, valor in valores.items()})
    with actor_scope(SYSTEM_USER_ID):
        session.add(socio)
        await session.flush()
        await session.commit()
    return socio


async def make_members(session: AsyncSession, n: int, **cambios: Any) -> list[Member]:
    """`n` socios con documentos únicos, sin teléfono ni correo (prueba de rendimiento, B8)."""
    socios: list[Member] = []
    for indice in range(n):
        valores: dict[str, Any] = {
            "first_name": f"{NOMBRE} {indice}",
            "document": unique_document(),
            "phone": None,
            "email": None,
            **cambios,
        }
        socios.append(await make_member(session, **valores))
    return socios
