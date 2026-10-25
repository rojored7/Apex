"""Ningún evento de dominio lleva datos personales ni texto libre (S3-D70, M-7; nace en S3-B6).

Los eventos viajan por el bus dentro de la transacción y los handlers pueden registrarlos; si un
evento llevara el motivo de una anulación, la referencia de un pago o un dato del socio, ese texto
podría terminar en un log o en una cola futura (Sprint 5). Regla, sobre todos los `DomainEvent`
definidos en `app` (los de cada `service.py` y su `events.py`, cargados con
`main.load_module_services()`):
- ningún campo se llama como un dato personal o un texto libre (`PROHIBIDOS`: `reason`,
  `reference`, `document`, `phone`, `email`, `name`, `first_name`, `last_name`, `note`, `notes`,
  `value`, `birth_date`, `emergency_contact`, `address`, `cancel_reason`, `void_reason`);
- excepción: un campo con un nombre prohibido cuyo tipo es un `Literal` cerrado (o `Literal | None`)
  es un código, no texto libre, y se acepta. Es el caso de `reason` en los eventos de `auth`
  (`LoginAttempted`, `SessionsRevoked`, `UserLocked`): códigos como `too_many_failures`;
- `MembershipCancelled` (S3-B6) lleva `reason_len` (el largo), nunca `reason`.
- S3-B10: `MemberUpdated(member_id, changed_fields)` lleva nombres de columna (`tuple[str, ...]`)
  y `MemberDeactivated(member_id)` solo el socio; el evento y el 409 `MemberIsDeactivated` no
  comparten nombre (L-7).
Controles con eventos falsos: un `reason: str` se detecta; `reason_len: int` y `reason:
Literal[...]` pasan.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from dataclasses import dataclass
from typing import Any, Literal

from app.core.events import DomainEvent
from app.main import load_module_services
from app.modules.members import service as members_service
from app.modules.members.exceptions import MemberIsDeactivated
from app.modules.memberships.service import MembershipCancelled

PROHIBIDOS = frozenset(
    {
        "reason",
        "reference",
        "document",
        "phone",
        "email",
        "name",
        "first_name",
        "last_name",
        "note",
        "notes",
        "value",
        "birth_date",
        "emergency_contact",
        "address",
        "cancel_reason",
        "void_reason",
    }
)


def _es_codigo_cerrado(tipo: Any) -> bool:
    """Verdadero si `tipo` es un `Literal` o una unión de `Literal` con `None`."""
    if typing.get_origin(tipo) is Literal:
        return True
    if typing.get_origin(tipo) in (typing.Union, types.UnionType):
        return all(
            argumento is type(None) or typing.get_origin(argumento) is Literal
            for argumento in typing.get_args(tipo)
        )
    return False


def violaciones(evento: type[DomainEvent]) -> list[str]:
    """`Evento.campo` por cada campo con nombre prohibido que no es un código cerrado."""
    tipos = typing.get_type_hints(evento)
    return [
        f"{evento.__name__}.{campo.name}"
        for campo in dataclasses.fields(evento)
        if campo.name in PROHIBIDOS and not _es_codigo_cerrado(tipos[campo.name])
    ]


def _subclases(base: type[DomainEvent]) -> set[type[DomainEvent]]:
    hijas = set(base.__subclasses__())
    for hija in list(hijas):
        hijas |= _subclases(hija)
    return hijas


def eventos_de_la_app() -> list[type[DomainEvent]]:
    load_module_services()
    return sorted(
        (e for e in _subclases(DomainEvent) if e.__module__.startswith("app.")),
        key=lambda e: (e.__module__, e.__name__),
    )


def test_hay_eventos_de_todos_los_modulos_que_emiten() -> None:
    modulos = {e.__module__.split(".")[2] for e in eventos_de_la_app()}
    assert {"auth", "members", "plans", "memberships", "payments"} <= modulos, modulos


def test_ningun_evento_lleva_datos_personales_ni_texto_libre() -> None:
    encontrados = [v for e in eventos_de_la_app() for v in violaciones(e)]
    assert encontrados == [], encontrados


def test_membership_cancelled_lleva_el_largo_del_motivo_y_no_el_texto() -> None:
    campos = {campo.name for campo in dataclasses.fields(MembershipCancelled)}
    assert campos == {"occurred_at", "membership_id", "member_id", "reason_len"}
    assert typing.get_type_hints(MembershipCancelled)["reason_len"] is int
    assert violaciones(MembershipCancelled) == []


# S3-B10 (S3-D70, L-7): los eventos de editar y dar de baja ---------------------------------------


def test_member_updated_lleva_nombres_de_campo_y_no_valores() -> None:
    """`changed_fields` son nombres de columna (una tupla de `str`), nunca los valores."""
    evento = members_service.MemberUpdated
    campos = {campo.name for campo in dataclasses.fields(evento)}
    assert campos == {"occurred_at", "member_id", "changed_fields"}
    assert typing.get_type_hints(evento)["changed_fields"] == tuple[str, ...]
    assert violaciones(evento) == []
    assert evento in eventos_de_la_app()


def test_member_deactivated_solo_lleva_el_socio() -> None:
    evento = members_service.MemberDeactivated
    assert {campo.name for campo in dataclasses.fields(evento)} == {"occurred_at", "member_id"}
    assert evento in eventos_de_la_app()


def test_member_reactivated_solo_lleva_el_socio() -> None:
    """Fase 4 del Sprint 3 (M1, PM1; S3-D89): el evento propio de la reactivación."""
    evento = members_service.MemberReactivated
    assert {campo.name for campo in dataclasses.fields(evento)} == {"occurred_at", "member_id"}
    assert violaciones(evento) == []
    assert evento in eventos_de_la_app()


def test_el_evento_de_la_baja_y_el_409_no_comparten_nombre() -> None:
    """L-7: un `except MemberDeactivated` mal importado no puede tragarse el 409."""
    assert members_service.MemberDeactivated.__name__ == "MemberDeactivated"
    assert MemberIsDeactivated.__name__ == "MemberIsDeactivated"
    assert not issubclass(members_service.MemberDeactivated, BaseException)
    assert (MemberIsDeactivated.status, MemberIsDeactivated.code) == (409, "member_deactivated")


# Controles con eventos falsos ------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class _ConMotivo(DomainEvent):
    membership_id: int
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _ConLargo(DomainEvent):
    membership_id: int
    reason_len: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _ConCodigo(DomainEvent):
    reason: Literal["admin", "too_many_failures"] | None = None
    reference: str | None = None


def test_el_analizador_detecta_texto_libre_y_acepta_largos_y_codigos() -> None:
    assert violaciones(_ConMotivo) == ["_ConMotivo.reason"]
    assert violaciones(_ConLargo) == []
    assert violaciones(_ConCodigo) == ["_ConCodigo.reference"]
    assert _ConMotivo not in eventos_de_la_app()  # solo cuenta lo definido en `app`
