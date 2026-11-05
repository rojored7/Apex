"""Funciones puras de plantillas y reglas de aviso (S5-B6; S5-D25, S5-D213). Privado: solo
`service.py` lo importa.

- `render(template, context)`: sustituye `{nombre} {plan} {vence} {dias}`; `{{` y `}}` son llaves
  literales. El valor sustituido nunca se vuelve a expandir. Es un recorrido propio (no
  `str.format`): `{nombre!r}`, `{nombre.x}`, `{0}` o `{}` son sintaxis no permitida.
- `validate_template_vars(text, field)`: la misma lectura sin contexto; lanza `TemplateError` con
  `field` y un mensaje fijo (nunca repite el texto recibido).
- `validate_rule`: disparador, canal y signo del desfase (`RuleValidationError` con `field`).
- `target_dates`, `days_value`, `can_skip` y `next_attempt_allowed`: reglas del job `notify` (B7).
- `DEFAULT_TEMPLATES` y `DEFAULT_RULES`: la siembra (S5-D25).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from app.modules.notifications.exceptions import RuleValidationError, TemplateError
from app.modules.notifications.models import CHANNELS, TRIGGERS, NotificationRule

ALLOWED_VARIABLES: Final[tuple[str, ...]] = ("nombre", "plan", "vence", "dias")
SKIPPABLE_STATUSES: Final[frozenset[str]] = frozenset({"pending", "failed"})

_VARIABLE_DESCONOCIDA: Final = "La plantilla usa una variable que no existe."
_LLAVE_SIN_CERRAR: Final = "La plantilla tiene una llave sin cerrar."
_LLAVE_SUELTA: Final = "La plantilla tiene una llave de cierre sin abrir."
_FALTA_EN_CONTEXTO: Final = "La plantilla usa una variable que no tiene valor."
_SALTO_EN_ASUNTO: Final = "El asunto no puede tener saltos de línea."
MAX_VARIABLE_LENGTH: Final = 16
"""Tope del nombre entre llaves (16): la búsqueda del cierre no recorre el resto del texto."""
_SALTOS: Final = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")


def _scan(text: str, field: str | None) -> Iterator[tuple[str, bool]]:
    """Recorre `text` y da `(trozo, es_variable)`; `TemplateError(field=field)` si hay una
    variable fuera de `ALLOWED_VARIABLES` o una llave mal formada."""
    i, largo = 0, len(text)
    while i < largo:
        c = text[i]
        siguiente = text[i + 1] if i + 1 < largo else ""
        if c == "{" and siguiente == "{":
            yield "{", False
            i += 2
        elif c == "}" and siguiente == "}":
            yield "}", False
            i += 2
        elif c == "}":
            raise TemplateError(message=_LLAVE_SUELTA, field=field)
        elif c == "{":
            cierre = text.find("}", i + 1, i + 2 + MAX_VARIABLE_LENGTH)
            if cierre == -1:
                raise TemplateError(message=_LLAVE_SIN_CERRAR, field=field)
            nombre = text[i + 1 : cierre]
            if nombre not in ALLOWED_VARIABLES:
                raise TemplateError(message=_VARIABLE_DESCONOCIDA, field=field)
            yield nombre, True
            i = cierre + 1
        else:
            fin = i
            while fin < largo and text[fin] not in "{}":
                fin += 1
            yield text[i:fin], False
            i = fin


def render(template: str, context: Mapping[str, str | int]) -> str:
    """Reemplaza `{nombre} {plan} {vence} {dias}`; `{{` y `}}` son llaves literales. Lanza
    `TemplateError` ante variable desconocida o ausente del contexto, o llave sin cerrar."""
    partes: list[str] = []
    for trozo, es_variable in _scan(template, None):
        if not es_variable:
            partes.append(trozo)
        elif trozo in context:
            partes.append(str(context[trozo]))
        else:
            raise TemplateError(message=_FALTA_EN_CONTEXTO)
    return "".join(partes)


def render_subject(template: str, context: Mapping[str, str | int]) -> str:
    """`render` del asunto con defensa en profundidad (S5-D216): si tras sustituir queda algún
    salto de línea (un valor del contexto lo trae), `TemplateError` con `field="subject"`."""
    salida = render(template, context)
    if any(c in _SALTOS for c in salida):
        raise TemplateError(message=_SALTO_EN_ASUNTO, field="subject")
    return salida


def validate_template_vars(text: str, field: str) -> None:
    """`TemplateError` con `field` si `text` usa una variable fuera de las cuatro permitidas o
    tiene llaves mal formadas. No necesita contexto."""
    for _ in _scan(text, field):
        pass


def validate_rule(trigger: str, offset_days: int, channel: str) -> None:
    """`RuleValidationError` con `field` (`trigger`, `channel` u `offset_days`), en ese orden."""
    if trigger not in TRIGGERS:
        raise RuleValidationError(message="El disparador no es válido.", field="trigger")
    if channel not in CHANNELS:
        raise RuleValidationError(message="El canal no es válido.", field="channel")
    if trigger == "membership_expiring" and offset_days > 0:
        raise RuleValidationError(
            message="Un aviso de vencimiento próximo lleva un desfase de cero o negativo.",
            field="offset_days",
        )
    if trigger == "membership_expired" and offset_days < 1:
        raise RuleValidationError(
            message="Un aviso de vencida lleva un desfase de uno o más días.", field="offset_days"
        )


def target_dates(rule: NotificationRule, end_date: date) -> date:
    """Fecha en que toca el aviso: `end_date + rule.offset_days`."""
    return end_date + timedelta(days=rule.offset_days)


def days_value(end_date: date, target_date: date) -> int:
    """Valor de `{dias}`: la diferencia absoluta en días entre las dos fechas (S5-D213)."""
    return abs((target_date - end_date).days)


def can_skip(status: str) -> bool:
    """Solo `pending` y `failed` se pueden omitir."""
    return status in SKIPPABLE_STATUSES


def next_attempt_allowed(attempts: int, max_attempts: int) -> bool:
    """`attempts < max_attempts`."""
    return attempts < max_attempts


@dataclass(frozen=True, slots=True)
class DefaultRule:
    name: str
    trigger: str
    offset_days: int
    template: str


SOON_NAME: Final = "Vence pronto"
EXPIRED_NAME: Final = "Venció"
DEFAULT_CHANNEL: Final = "whatsapp_link"

DEFAULT_TEMPLATES: Final[dict[str, tuple[str, str]]] = {
    SOON_NAME: (
        "Tu membresía vence pronto",
        "Hola {nombre}, tu plan {plan} vence el {vence} (en {dias} días). Te esperamos.",
    ),
    EXPIRED_NAME: (
        "Tu membresía venció",
        "Hola {nombre}, tu plan {plan} venció el {vence} (hace {dias} días). "
        "Renuévalo cuando quieras.",
    ),
}
"""Nombre → (asunto, cuerpo). Solo variables válidas; `{dias}` va sin signo (S5-D213)."""

DEFAULT_RULES: Final[tuple[DefaultRule, ...]] = (
    DefaultRule("Vence en 3 días", "membership_expiring", -3, SOON_NAME),
    DefaultRule("Vence hoy", "membership_expiring", 0, SOON_NAME),
    DefaultRule("Venció hace 1 día", "membership_expired", 1, EXPIRED_NAME),
    DefaultRule("Venció hace 7 días", "membership_expired", 7, EXPIRED_NAME),
    DefaultRule("Venció hace 15 días", "membership_expired", 15, EXPIRED_NAME),
)
