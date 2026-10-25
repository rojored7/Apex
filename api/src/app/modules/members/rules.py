"""Reglas puras de socios (S2-B7, US-069; S2-B8, US-070; M-4, L-3, RN-13, N-02).

Archivo privado del módulo (S3-B9a, D7, S3-D73): solo lo importa `members`; los demás módulos
y las pruebas llegan por la fachada `members/service.py`, que re-exporta esto con `__all__`.
Se movió tal cual desde `service.py`, sin cambiar la lógica.

- `validate_member_input(data, today)`: nombres no vacíos, `sex` en `f`/`m`/`x` o nulo,
  `1900-01-01 <= birth_date <= today` (`today` es `today_bogota()`), documento o correo
  que no se normalicen a vacío y teléfono con al menos `PHONE_MIN_DIGITS` dígitos tras
  normalizar (L-3: `"+57"` se normaliza a `"57"`). Lanza
  `MemberValidationError` con `field` y sin repetir el valor.
- `compute_warnings(data)`: `["data_consent_missing"]` sin autorización, `[]` con ella.
- `mask(field, value, *, document_type=None)`: enmascarado en memoria del valor de entrada
  (`CC •••• 0304`, `••• ••• 4567`, `l•••@•••.co`, `••/••/1991`, `"Registrado"`); `None` da
  `None`. Nunca opera sobre el blob.
- `classify_query(q) -> QueryPlan`: `q` en NFC, sin caracteres de control y
  recortado; `name_pattern` = `%<q>%` con la barra invertida, `%` y `_` escapados
  (`LIKE_ESCAPE`, de `core.search`); `by_document` = el documento
  normalizado (`generic`) cuando no queda vacío, tiene al menos un dígito y solo letras y
  dígitos; `by_phone` = el teléfono normalizado con al menos `PHONE_MIN_DIGITS` dígitos;
  `by_email` = el correo normalizado si `q` tiene `@`. Captura `CryptoError("empty_value")`.
  `q` vacío o en blanco da el plan vacío (todo `None`).
- `chip_to_filter(chip) -> MemberChipFilter` (S3-B9b, US-071): los siete chips de la lista
  (`MEMBER_CHIPS`); "Dados de baja" es `status="deleted"` y los otros seis, el
  `membership_status` del mismo nombre. Un chip desconocido da `ValueError`.
- S3-B10 (US-075; D21, M-3, S3-D46): `diff_fields(before, patch)` (los campos presentes cuyo
  valor cambia; documento, teléfono y correo normalizados), `ensure_can_change(set_fields,
  role)` con `ADMIN_ONLY_FIELDS` (por presencia) y `validate_member_patch(patch, today)` (las
  reglas del alta sobre los campos presentes).
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal

from app.core.crypto.errors import CryptoError
from app.core.crypto.normalize import IndexKind, normalize_for_index
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern
from app.modules.members.exceptions import MemberFieldForbidden, MemberValidationError
from app.modules.members.models import SEXES
from app.modules.members.schemas import (
    DATA_CONSENT_MISSING,
    MemberCreate,
    MemberPatch,
    MembershipFilterStatus,
    MemberStatusFilter,
)

__all__ = [
    "ADMIN_ONLY_FIELDS",
    "BIRTH_DATE_MIN",
    "DOCUMENT_MIN_MASKED",
    "DOTS",
    "EMAIL_DATA_CLASS",
    "EMERGENCY_CONTACT_MASK",
    "LIKE_ESCAPE",
    "MASK_TAIL",
    "MEMBER_CHIPS",
    "PHONE_DATA_CLASS",
    "PHONE_MIN_DIGITS",
    "PLAN_VACIO",
    "MaskField",
    "MaskValue",
    "MemberChip",
    "MemberChipFilter",
    "QueryPlan",
    "chip_to_filter",
    "classify_query",
    "compute_warnings",
    "diff_fields",
    "ensure_can_change",
    "mask",
    "validate_member_input",
    "validate_member_patch",
]

MaskField = Literal["document", "phone", "email", "birth_date", "emergency_contact"]
MaskValue = str | date | Mapping[str, Any] | None

BIRTH_DATE_MIN: Final = date(1900, 1, 1)  # LOW L6: un año mal tecleado (`0991`) no pasa
PHONE_MIN_DIGITS: Final = 7  # L-3: "+57" queda en "57"; un fijo local tiene 7 dígitos
MASK_TAIL: Final = 4
DOCUMENT_MIN_MASKED: Final = 6  # al menos 2 caracteres ocultos además de la cola
DOTS: Final = "•••"
EMERGENCY_CONTACT_MASK: Final = "Registrado"
PHONE_DATA_CLASS: Final = "member.phone"
EMAIL_DATA_CLASS: Final = "member.email"

_MENSAJES: Final[Mapping[str, str]] = {
    "first_name": "El nombre es obligatorio.",
    "last_name": "El apellido es obligatorio.",
    "sex": "El sexo debe ser f, m o x.",
    "birth_date": "La fecha de nacimiento debe estar entre 1900 y hoy.",
    "document": "El documento no tiene caracteres válidos.",
    "phone": "El teléfono no tiene suficientes dígitos.",
    "email": "El correo no es válido.",
}


# Alta: validación, avisos y máscaras ------------------------------------------------


def _invalido(campo: str) -> MemberValidationError:
    """422 con `field`; el mensaje nunca repite el valor recibido."""
    return MemberValidationError(message=_MENSAJES[campo], field=campo)


def _normalizado(valor: str, kind: IndexKind) -> str:
    """Forma del índice ciego, o `""` si el valor se normaliza a vacío (L-3)."""
    try:
        return normalize_for_index(valor, kind)
    except CryptoError:
        return ""


def validate_member_input(data: MemberCreate, today: date) -> None:
    """Reglas del alta que el schema no expresa (L-3; LOW L6 de la revisión Python: fecha de
    nacimiento entre `BIRTH_DATE_MIN` y `today`). Lanza `MemberValidationError` con `field` y
    sin repetir el valor."""
    for campo in ("first_name", "last_name"):
        if not str(getattr(data, campo) or "").strip():
            raise _invalido(campo)
    if data.sex is not None and data.sex not in SEXES:
        raise _invalido("sex")
    if data.birth_date is not None and not BIRTH_DATE_MIN <= data.birth_date <= today:
        raise _invalido("birth_date")
    if not _normalizado(data.document, "generic"):
        raise _invalido("document")
    if data.phone is not None and len(_normalizado(data.phone, "phone")) < PHONE_MIN_DIGITS:
        raise _invalido("phone")
    if data.email is not None and not _normalizado(data.email, "email"):
        raise _invalido("email")


def compute_warnings(data: MemberCreate) -> builtins.list[str]:
    """Avisos del alta: `data_consent_missing` sin autorización (M-4)."""
    return [] if data.data_consent else [DATA_CONSENT_MISSING]


def _mask_document(value: str, document_type: str | None) -> str:
    """Los 4 últimos del normalizado; un documento de menos de `DOCUMENT_MIN_MASKED` caracteres
    va sin cola para no mostrarlo entero (revisión S2-B7, LOW-2)."""
    normalizado = _normalizado(value, "generic").upper()
    prefijo = f"{document_type or 'CC'} •{DOTS}"
    if len(normalizado) < DOCUMENT_MIN_MASKED:
        return prefijo
    return f"{prefijo} {normalizado[-MASK_TAIL:]}"


def _mask_phone(value: str) -> str:
    digitos = "".join(c for c in value if c in "0123456789")
    return f"{DOTS} {DOTS} {digitos[-MASK_TAIL:]}"


def _mask_email(value: str) -> str:
    local, _, dominio = value.strip().lower().rpartition("@")
    inicial = local[:1] or "•"
    etiqueta = dominio.rsplit(".", 1)[-1] if "." in dominio else DOTS
    return f"{inicial}{DOTS}@{DOTS}.{etiqueta}"


def mask(field: MaskField, value: MaskValue, *, document_type: str | None = None) -> str | None:
    """Enmascarado en memoria del valor de entrada; nunca opera sobre el blob."""
    if value is None:
        return None
    if field == "emergency_contact":
        return EMERGENCY_CONTACT_MASK
    if field == "birth_date":
        anio = value.year if isinstance(value, date) else date.fromisoformat(str(value)).year
        return f"••/••/{anio:04d}"
    if not isinstance(value, str):
        raise TypeError(f"{field} se enmascara desde texto")
    if field == "document":
        return _mask_document(value, document_type)
    if field == "phone":
        return _mask_phone(value)
    return _mask_email(value)


# Buscar (S2-B8) ----------------------------------------------------------------------


@dataclass(frozen=True)
class QueryPlan:
    """Qué busca un término: patrón de nombre y valores normalizados para cada índice ciego."""

    q: str | None
    name_pattern: str | None
    by_document: str | None
    by_phone: str | None
    by_email: str | None


PLAN_VACIO: Final = QueryPlan(
    q=None, name_pattern=None, by_document=None, by_phone=None, by_email=None
)


def _es_documento(normalizado: str) -> bool:
    """CC, CE, TI y PA: solo letras y dígitos ASCII y al menos un dígito (S2-B8, decisión 1)."""
    return normalizado.isascii() and normalizado.isalnum() and any(c.isdigit() for c in normalizado)


def classify_query(q: str | None) -> QueryPlan:
    """El plan de búsqueda de `q` (`core.search.clean_query`: NFC, sin `Cc`, recortado; defensa
    en profundidad, `SearchQuery` ya rechaza los controles con 422)."""
    termino = clean_query(q)
    if not termino:
        return PLAN_VACIO
    documento = _normalizado(termino, "generic")
    telefono = _normalizado(termino, "phone")
    correo = _normalizado(termino, "email") if "@" in termino else ""
    return QueryPlan(
        q=termino,
        name_pattern=contains_pattern(termino),
        by_document=documento if _es_documento(documento) else None,
        by_phone=telefono if len(telefono) >= PHONE_MIN_DIGITS else None,
        by_email=correo or None,
    )


# Chips de la lista (S3-B9b, US-071; D22, N-20) ---------------------------------------


MemberChip = Literal[
    "active", "expiring", "expired", "frozen", "pending_payment", "none", "deleted"
]
MEMBER_CHIPS: Final[tuple[MemberChip, ...]] = (
    "active",
    "expiring",
    "expired",
    "frozen",
    "pending_payment",
    "none",
    "deleted",
)
"""Los siete chips de la lista: "Al día", "Por vencer", "Vencidos", "Congelados", "Pendiente
de pago", "Sin membresía" y "Dados de baja" (admin y coach, N-20)."""


_CHIPS_DE_MEMBRESIA: Final[Mapping[str, MembershipFilterStatus]] = {
    "active": "active",
    "expiring": "expiring",
    "expired": "expired",
    "frozen": "frozen",
    "pending_payment": "pending_payment",
    "none": "none",
}


@dataclass(frozen=True)
class MemberChipFilter:
    """Los filtros de `MemberListQuery` que un chip fija; el resto queda como esté."""

    status: MemberStatusFilter | None
    membership_status: MembershipFilterStatus | None


def chip_to_filter(chip: str) -> MemberChipFilter:
    """El filtro de un chip: "Dados de baja" (`deleted`) es `status="deleted"`; los otros seis
    fijan el `membership_status` del mismo nombre. Un chip desconocido da `ValueError` (sin
    normalizar mayúsculas ni espacios: el front envía el valor exacto)."""
    if chip == "deleted":
        return MemberChipFilter(status="deleted", membership_status=None)
    estado = _CHIPS_DE_MEMBRESIA.get(chip)
    if estado is None:
        raise ValueError("chip de socios desconocido")
    return MemberChipFilter(status=None, membership_status=estado)


# Editar (S3-B10, US-075; D21, M-3, S3-D46) ---------------------------------------------


ADMIN_ROLE: Final = "admin"
ADMIN_ONLY_FIELDS: Final[frozenset[str]] = frozenset({"document", "document_type"})
"""Campos de identidad que solo cambia un admin; se deciden por PRESENCIA en el cuerpo (M-3)."""


_NORMALIZADOS: Final[Mapping[str, IndexKind]] = {
    "document": "generic",
    "phone": "phone",
    "email": "email",
}
"""Campos que se comparan por su forma normalizada (N-02): un cambio solo de formato no cuenta."""


def _valor_del_patch(patch: MemberPatch, campo: str) -> object:
    """El valor del patch en la forma de `before` (el contacto como mapeo sin nulos)."""
    if campo == "emergency_contact" and patch.emergency_contact is not None:
        return patch.emergency_contact.model_dump(exclude_none=True)
    return getattr(patch, campo)


def _mismo_valor(campo: str, antes: object, despues: object) -> bool:
    if antes is None or despues is None:
        return antes is despues
    kind = _NORMALIZADOS.get(campo)
    if kind is not None:
        nuevo = _normalizado(str(despues), kind)
        return bool(nuevo) and nuevo == _normalizado(str(antes), kind)
    return antes == despues


def diff_fields(before: Mapping[str, object], patch: MemberPatch) -> frozenset[str]:
    """Los campos de `patch.model_fields_set` cuyo valor difiere del actual (`before`, valores en
    claro; una clave ausente vale `None`). Documento, teléfono y correo se comparan normalizados
    (un cambio solo de formato no cuenta); `null` sobre un opcional con valor cuenta como cambio.
    `data_consent` no se compara aquí (lo decide `update` con `data_consent_at`)."""
    return frozenset(
        campo
        for campo in patch.model_fields_set - {"data_consent"}
        if not _mismo_valor(campo, before.get(campo), _valor_del_patch(patch, campo))
    )


def ensure_can_change(set_fields: AbstractSet[str], role: str) -> None:
    """`MemberFieldForbidden` (403 `forbidden_field`) si quien no es admin envía `document` o
    `document_type`, con cualquier valor (presencia, M-3). Con los dos, nombra `document`."""
    if role == ADMIN_ROLE:
        return
    for campo in sorted(ADMIN_ONLY_FIELDS):
        if campo in set_fields:
            raise MemberFieldForbidden(campo)


def validate_member_patch(patch: MemberPatch, today: date) -> None:
    """Las reglas del alta (`validate_member_input`) sobre los campos presentes del patch que el
    schema no expresa: fecha de nacimiento entre `BIRTH_DATE_MIN` y `today`, documento y correo
    que no se normalizan a vacío y teléfono con al menos `PHONE_MIN_DIGITS` dígitos."""
    if patch.birth_date is not None and not BIRTH_DATE_MIN <= patch.birth_date <= today:
        raise _invalido("birth_date")
    if patch.document is not None and not _normalizado(patch.document, "generic"):
        raise _invalido("document")
    if patch.phone is not None and len(_normalizado(patch.phone, "phone")) < PHONE_MIN_DIGITS:
        raise _invalido("phone")
    if patch.email is not None and not _normalizado(patch.email, "email"):
        raise _invalido("email")
