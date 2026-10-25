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
