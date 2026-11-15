"""Schemas de settings (US-054, US-055, US-057, US-058; blueprint del Sprint 2, B1).

Contrato (N-18, S2-D15, D5):
- `SectionValue`: `ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)`.
- `GymSettings`: `name` (1 a 80, sin default en el modelo; vacío o ausente da 422),
  `nit: str | None` (`NIT_PATTERN`: dígitos y un dígito de verificación opcional, hasta 15),
  `address` (hasta 120), `city` (hasta 60), `phone` (hasta 20), `whatsapp` (hasta 20),
  `email: EmailAddress | None`; los opcionales son `None` por defecto.
- `PrivacySettings`: `policy_version` (1 a 20), `policy_text` (1 a 20.000),
  `retention_years` estricto 1 a 20 (5), `consent_required_from: date | None = None`.
  `PrivacyView` (solo salida): igual, con `policy_version` y `policy_text` que admiten `None`.
- `MembershipsSettings`: cuatro `StrictInt`: `expiring_days` 1 a 30 (7),
  `max_freeze_days_per_membership` 0 a 180 (30), `max_freezes_per_membership` 0 a 12 (2),
  `max_retroactive_days` 0 a 30 (7).
- `PaymentMethodsSettings` (S3-B3, US-056; D24, S3-D55, L-3): exactamente las claves de
  `PAYMENT_METHOD_CODES` (`cash`, `nequi`, `breb`), cada una un `MethodLabel` con `label`
  (`SafeText`, 1 a 30) y `hint` (`SafeText` o vacío, hasta 120); las tres etiquetas no se repiten
  sin distinguir mayúsculas (422 en `value.<code>.label` del segundo que repite). Los códigos son
  fijos: la sección solo cambia cómo se ven. `PaymentMethodInfo` es el contrato que
  `settings.service.payment_methods` entrega a `payments` (S2-D45).
- `SECTION_REGISTRY`: exactamente las cuatro de `ENABLED_SECTIONS` (esquemas de escritura);
  `SECTION_VIEWS`: los de lectura (`privacy` sin publicar se lee con `PrivacyView`).
- `SECTION_DEFAULTS`: `gym` con `name = "APEX"` y el resto `None`; `privacy` con
  `policy_version`/`policy_text`/`consent_required_from` en `None` y `retention_years = 5`;
  `memberships` con 7, 30, 2 y 7; `payment_methods` con "Efectivo", "Nequi" y "Bre-B" y pistas
  vacías. El service entrega copias (`defaults_for`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.core.validators import EmailAddress, SafeMultilineText, SafeText, check_visible_text


class SectionKey(StrEnum):
    gym = "gym"
    hours = "hours"
    payment_methods = "payment_methods"
    channels = "channels"
    classes = "classes"
    memberships = "memberships"
    tv = "tv"
    privacy = "privacy"


# S2-D15: las demás responden 404 hasta su versión. S3-B3 (US-056, D24) habilita `payment_methods`.
ENABLED_SECTIONS: frozenset[SectionKey] = frozenset(
    {
        SectionKey.gym,
        SectionKey.privacy,
        SectionKey.memberships,
        SectionKey.payment_methods,
        SectionKey.channels,  # S5-B4 (US-122, S5-D30)
        SectionKey.hours,  # S7-A1 (US-154, S7-D8)
        SectionKey.classes,
        SectionKey.tv,  # S8-C1 (US-175, S8-D17, S8-D30): solo por sus rutas propias
    }
)

# S8-D33: la TV refresca cada 15 a 300 segundos (30 por defecto).
TV_REFRESH_MIN: Final[int] = 15
TV_REFRESH_MAX: Final[int] = 300
TV_REFRESH_DEFAULT: Final[int] = 30
TV_TOKEN_LAST_CHARS: Final[int] = 4

# D24: códigos fijos de los medios de pago, en el orden en que se muestran. Los mismos en
# `payments.schemas.PaymentMethod`, `payments.models.PAYMENT_METHODS`, el CHECK del modelo y la
# migración `0010_payments` (`tests/architecture/test_payment_method_codes.py`).
PAYMENT_METHOD_CODES: Final[tuple[str, ...]] = ("cash", "nequi", "breb")
METHOD_LABEL_MAX_LENGTH: Final[int] = 30
METHOD_HINT_MAX_LENGTH: Final[int] = 120

NIT_PATTERN: Final[str] = r"^\d+(-\d)?$"
RETENCION_POR_DEFECTO: Final[int] = 5

# Revisión de seguridad V10 (N-2): JSONB rechaza `\u0000` (daba 500) y un U+202E se mostraría
# en todas las pantallas. Una línea: `SafeText`; la política admite saltos (`SafeMultilineText`).
PolicyVersion = Annotated[SafeText, Field(min_length=1, max_length=20)]
PolicyText = Annotated[SafeMultilineText, Field(min_length=1, max_length=20_000)]
RetentionYears = Annotated[StrictInt, Field(ge=1, le=20)]


class SectionValue(BaseModel):
    """Base de todo esquema de sección: sin campos extra e inmutable (Q12, US-054 T5)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# Solo dígitos ASCII (`[0-9]`, no `\d`): `\d` acepta dígitos Unicode (U+0665 en "0?:00") y las
# comparaciones de `open < close` y de solapes son de texto (revisión de S7-A1, MEDIUM).
HHMM_PATTERN: Final[str] = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
HOURS_MAX_RANGES: Final[int] = 2


class TimeRange(SectionValue):
    """Rango de atención `HH:MM` en hora de Bogotá (N-18); `open < close`: el día."""

    open: str = Field(pattern=HHMM_PATTERN)
    close: str = Field(pattern=HHMM_PATTERN)


DayRanges = Annotated[list[TimeRange], Field(max_length=HOURS_MAX_RANGES)]


class HoursSettings(SectionValue):
    """Horas de atención (US-154, S7-D8, N-18): de 0 a 2 rangos por día, ordenados y sin
    solaparse; lista vacía = cerrado. Solo informan: no restringen las franjas."""

    monday: DayRanges = Field(default_factory=list)
    tuesday: DayRanges = Field(default_factory=list)
    wednesday: DayRanges = Field(default_factory=list)
    thursday: DayRanges = Field(default_factory=list)
    friday: DayRanges = Field(default_factory=list)
    saturday: DayRanges = Field(default_factory=list)
    sunday: DayRanges = Field(default_factory=list)

    @field_validator("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    @classmethod
    def _ordenados_sin_solapar(cls, rangos: list[TimeRange]) -> list[TimeRange]:
        """`open < close` en cada rango y cada uno empieza donde o después de donde termina el
        anterior. Se valida por día (no por rango) para que el `field` sea `value.<día>`."""
        if any(rango.open >= rango.close for rango in rangos):
            raise ValueError("open debe ser menor que close")
        for previo, siguiente in pairwise(rangos):
            if siguiente.open < previo.close:
                raise ValueError("los rangos deben estar ordenados y sin solaparse")
        return rangos


class ClassesSettings(SectionValue):
    """Valores por defecto de las clases (US-154, S7-D8, N-18). Sin `allow_over_capacity` (N-38)."""

    default_capacity: StrictInt = Field(default=15, ge=1, le=100)
    checkin_window_min: StrictInt = Field(default=30, ge=0, le=240)


class GymSettings(SectionValue):
    """Datos del gimnasio (US-055, N-18). `name` sin default: el `"APEX"` vive en los defaults."""

    name: SafeText = Field(min_length=1, max_length=80)
    nit: str | None = Field(default=None, max_length=15, pattern=NIT_PATTERN)
    address: SafeText | None = Field(default=None, max_length=120)
    city: SafeText | None = Field(default=None, max_length=60)
    phone: SafeText | None = Field(default=None, max_length=20)
    whatsapp: SafeText | None = Field(default=None, max_length=20)
    email: EmailAddress | None = None


class PrivacySettings(SectionValue):
    """Política de privacidad (US-057, N-18): publicar exige versión y texto."""

    policy_version: PolicyVersion
    policy_text: PolicyText
    retention_years: RetentionYears = RETENCION_POR_DEFECTO
    consent_required_from: date | None = None


class GymView(SectionValue):
    """Salida de `gym`: los mismos campos sin `SafeText` (N-2 valida la ENTRADA); un valor
    guardado antes del texto seguro se sigue leyendo y se corrige con un `PATCH`."""

    name: str = Field(min_length=1, max_length=80)
    nit: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None


class PrivacyView(SectionValue):
    """Salida de `privacy`: la política nunca publicada tiene versión y texto `None`. Sin
    `SafeText` (solo la entrada lo aplica), como `GymView`."""

    policy_version: str | None = Field(default=None, max_length=20)
    policy_text: str | None = Field(default=None, max_length=20_000)
    retention_years: RetentionYears = RETENCION_POR_DEFECTO
    consent_required_from: date | None = None


class MembershipsSettings(SectionValue):
    """Parámetros de membresías (US-058, N-18). Enteros estrictos: `"7"`, `7.5`, `7.0` dan 422."""

    expiring_days: StrictInt = Field(default=7, ge=1, le=30)
    max_freeze_days_per_membership: StrictInt = Field(default=30, ge=0, le=180)
    max_freezes_per_membership: StrictInt = Field(default=2, ge=0, le=12)
    max_retroactive_days: StrictInt = Field(default=7, ge=0, le=30)


@dataclass(frozen=True)
class MembershipsPolicy:
    """Contrato que `memberships.service` importa desde `settings.schemas` (S2-D45)."""

    expiring_days: int
    max_freeze_days_per_membership: int
    max_freezes_per_membership: int
    max_retroactive_days: int


class MethodLabel(SectionValue):
    """Cómo se ve un medio de pago (US-056, S3-D55): etiqueta visible y pista opcional."""

    label: SafeText = Field(min_length=1, max_length=METHOD_LABEL_MAX_LENGTH)
    hint: str = Field(default="", max_length=METHOD_HINT_MAX_LENGTH)

    @field_validator("hint")
    @classmethod
    def _pista_segura(cls, valor: str) -> str:
        """Vacía se acepta; con texto, la misma regla de `SafeText` (sin `Cc` ni `Cf`)."""
        return check_visible_text(valor) if valor else valor


CountryCode = Annotated[str, StringConstraints(strip_whitespace=False, pattern=r"^[0-9]{1,3}$")]
SENDER_NAME_MAX_LENGTH: Final[int] = 80


class EmailChannel(SectionValue):
    """Correo: solo si está activo y el nombre que ve quien lo recibe (va a `From`, sin saltos)."""

    enabled: bool = False
    sender_name: SafeText = Field(default="APEX", min_length=1, max_length=SENDER_NAME_MAX_LENGTH)
    reply_to: EmailAddress | None = None


class WhatsappChannel(SectionValue):
    """Enlace de WhatsApp: el indicativo del país (solo dígitos, 1 a 3)."""

    enabled: bool = False
    country_code: CountryCode = "57"


class TelegramChannel(SectionValue):
    """Telegram es del equipo (S5-D29); aquí solo se enciende. Token y chat viven en el entorno."""

    enabled: bool = False


class ChannelsSettings(SectionValue):
    """Canales de aviso (US-122; S5-D30, S5-D204): sin secretos, todo cerrado (`extra="forbid"`)
    y apagado por defecto. `credentials_present` se calcula al leer; no es un campo."""

    email: EmailChannel = Field(default_factory=EmailChannel)
    whatsapp: WhatsappChannel = Field(default_factory=WhatsappChannel)
    telegram: TelegramChannel = Field(default_factory=TelegramChannel)


class PaymentMethodsSettings(SectionValue):
    """Etiquetas de los tres medios de pago fijos (US-056; D24, S3-D55)."""

    cash: MethodLabel
    nequi: MethodLabel
    breb: MethodLabel

    @model_validator(mode="after")
    def _etiquetas_unicas(self) -> PaymentMethodsSettings:
        """Dos medios con la misma etiqueta (sin distinguir mayúsculas) se leerían igual en los
        informes (L-3): el segundo que repite da error en `<code>.label`."""
        vistas: set[str] = set()
        for codigo in PAYMENT_METHOD_CODES:
            etiqueta = getattr(self, codigo).label
            clave = etiqueta.casefold()
            if clave in vistas:
                error = PydanticCustomError("duplicate_label", "La etiqueta ya está en uso.")
                detalle = InitErrorDetails(type=error, loc=(codigo, "label"), input=etiqueta)
                raise ValidationError.from_exception_data(type(self).__name__, [detalle])
            vistas.add(clave)
        return self


@dataclass(frozen=True)
class PaymentMethodInfo:
    """Contrato que `payments` importa desde `settings.schemas` (S2-D45, D24): un medio con su
    código fijo y cómo se ve."""

    code: str
    label: str
    hint: str


class TvEditable(SectionValue):
    """Lo único que el admin edita de la TV (S8-D30): refresco y si muestra el leaderboard."""

    refresh_seconds: Annotated[StrictInt, Field(ge=TV_REFRESH_MIN, le=TV_REFRESH_MAX)] = (
        TV_REFRESH_DEFAULT
    )
    show_leaderboard: StrictBool = True


class TvStored(TvEditable):
    """Lo guardado de la sección `tv` (S8-D17, S8-D30): el SHA-256 del token, nunca el token.
    Solo lo leen y escriben las funciones propias del service; ninguna respuesta lo devuelve."""

    device_token_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    token_last4: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{4}$")] | None = None
    rotated_at: datetime | None = None


class TvView(TvEditable):
    """La vista de la TV para el panel (S8-D30): sin el hash; `has_token` dice si hay token."""

    has_token: bool
    token_last4: str | None
    rotated_at: datetime | None


# Esquemas de escritura de las secciones habilitadas (S2-D15; S3-B3 suma `payment_methods`).
SECTION_REGISTRY: dict[SectionKey, type[SectionValue]] = {
    SectionKey.gym: GymSettings,
    SectionKey.privacy: PrivacySettings,
    SectionKey.memberships: MembershipsSettings,
    SectionKey.payment_methods: PaymentMethodsSettings,
    SectionKey.channels: ChannelsSettings,
    SectionKey.hours: HoursSettings,
    SectionKey.classes: ClassesSettings,
    SectionKey.tv: TvStored,
}

# Esquemas de lectura: `privacy` sin publicar no valida contra `PrivacySettings`, y ninguna
# salida aplica el texto seguro de la entrada (`GymView`, `PrivacyView`).
SECTION_VIEWS: dict[SectionKey, type[SectionValue]] = {
    **SECTION_REGISTRY,
    SectionKey.gym: GymView,
    SectionKey.privacy: PrivacyView,
}

# Valores de una sección nunca guardada (sin filas sembradas). Solo se leen por copia.
SECTION_DEFAULTS: dict[SectionKey, dict[str, Any]] = {
    SectionKey.gym: {
        "name": "APEX",
        "nit": None,
        "address": None,
        "city": None,
        "phone": None,
        "whatsapp": None,
        "email": None,
    },
    SectionKey.privacy: {
        "policy_version": None,
        "policy_text": None,
        "retention_years": RETENCION_POR_DEFECTO,
        "consent_required_from": None,
    },
    SectionKey.memberships: {
        "expiring_days": 7,
        "max_freeze_days_per_membership": 30,
        "max_freezes_per_membership": 2,
        "max_retroactive_days": 7,
    },
    SectionKey.payment_methods: {
        "cash": {"label": "Efectivo", "hint": ""},
        "nequi": {"label": "Nequi", "hint": ""},
        "breb": {"label": "Bre-B", "hint": ""},
    },
    SectionKey.channels: {
        "email": {"enabled": False, "sender_name": "APEX", "reply_to": None},
        "whatsapp": {"enabled": False, "country_code": "57"},
        "telegram": {"enabled": False},
    },
    SectionKey.hours: {
        dia: []
        for dia in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    },
    SectionKey.classes: {"default_capacity": 15, "checkin_window_min": 30},
    SectionKey.tv: {
        "refresh_seconds": TV_REFRESH_DEFAULT,
        "show_leaderboard": True,
        "device_token_hash": None,
        "token_last4": None,
        "rotated_at": None,
    },
}


# Entradas y salidas del API -------------------------------------------------------------


class _SectionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: SectionKey
    version: int = Field(ge=0)
    updated_at: datetime | None
    updated_by: UUID | None


class CredentialsPresent(BaseModel):
    """Si el entorno trae lo necesario para cada canal (S5-D30); jamás los valores."""

    model_config = ConfigDict(extra="forbid")

    email: bool
    telegram: bool


class SectionOut(_SectionMeta):
    """Sección genérica: fila guardada o defaults con `version = 0` y `updated_* = None`.

    `credentials_present` (S5-D204) solo lo trae `channels`; en las demás es `null`."""

    value: dict[str, Any]
    credentials_present: CredentialsPresent | None = None


class GymSectionOut(_SectionMeta):
    value: GymView


class PrivacySectionOut(_SectionMeta):
    value: PrivacyView


class MembershipsSectionOut(_SectionMeta):
    value: MembershipsSettings


class PaymentMethodsSectionOut(_SectionMeta):
    value: PaymentMethodsSettings


class HoursSectionOut(_SectionMeta):
    value: HoursSettings


class ClassesSectionOut(_SectionMeta):
    value: ClassesSettings


class TvSectionOut(_SectionMeta):
    """`GET/PATCH /settings/tv`: la vista, nunca el hash (S8-D30)."""

    value: TvView


class TvTokenOut(BaseModel):
    """`POST /settings/tv/regenerate-token` (S8-D32): el token y el enlace se ven UNA vez."""

    model_config = ConfigDict(extra="forbid")

    token: str
    url: str
    token_last4: str
    rotated_at: datetime
    version: int


class TvConfig(BaseModel):
    """Lo que la TV necesita de la sección tras validar el token (C2): sin el hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refresh_seconds: int
    show_leaderboard: bool


class TvPatchIn(BaseModel):
    """`PATCH /settings/tv`: solo `refresh_seconds` y `show_leaderboard`; un token o un hash en
    `value` es 422 (S8-D30)."""

    model_config = ConfigDict(extra="forbid")

    value: TvEditable
    version: int = Field(ge=0)


class SectionPatchIn(BaseModel):
    """`PATCH` reemplaza la sección completa con la versión que se leyó (N-17, S2-D15)."""

    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]
    version: int = Field(ge=0)


class GymPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: GymSettings
    version: int = Field(ge=0)


class PrivacyPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: PrivacySettings
    version: int = Field(ge=0)


class MembershipsPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: MembershipsSettings
    version: int = Field(ge=0)


class PaymentMethodsPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: PaymentMethodsSettings
    version: int = Field(ge=0)


class HoursPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: HoursSettings
    version: int = Field(ge=0)


class ClassesPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: ClassesSettings
    version: int = Field(ge=0)
