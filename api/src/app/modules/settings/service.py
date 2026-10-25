"""Service de settings (US-054, US-055, US-057, US-058; blueprint del Sprint 2, B1).

- Puras: `validate_section` (arma `field = "value." + ".".join(map(str, loc))` y lanza
  `SettingsValidationError` sin repetir el valor), `check_version` (`VersionConflict` si
  difieren), `defaults_for` (copia de `SECTION_DEFAULTS[key]`) y `ensure_enabled` (clave
  desconocida o fuera de `ENABLED_SECTIONS`: `SectionNotAvailable`).
- `get_section`: la fila o los defaults con `version = 0`, `updated_at = None` y
  `updated_by = None`. Leer nunca siembra filas.
- `update_section` (N-17, flujo 7.3): `ensure_enabled`, `validate_section` y
  `SELECT ... FOR UPDATE` por `key`. Sin fila exige `version == 0` e inserta con `version = 1`
  dentro de `begin_nested()`; el `IntegrityError` de `uq_settings_sections_key` (dos primeros
  guardados a la vez) se traduce a `VersionConflict`. Con fila: `check_version`, `dict` nuevo
  (`model_dump(mode="json")`), `version += 1`, `updated_by = by` y `flush`. El hook de US-016
  audita `insert` y luego `update` (`__audited__`).
- API interna para otros módulos (S2-D45): `get`, `memberships_policy`,
  `current_privacy_version` (`None` sin política publicada) y `gym_name` (respaldo `"APEX"`,
  también si lo guardado ya no valida; revisión Python M3).
- Medios de pago (S3-B3, US-056; D24, S3-D55, L-3): la pura `decorate_methods(codes, labels)`
  devuelve un `PaymentMethodInfo` por código, en el orden de `codes` (nunca el del JSON), con la
  etiqueta de `labels` o la de `SECTION_DEFAULTS` si falta; ignora claves ajenas.
  `payment_methods(session)` lee la sección y la valida con `PaymentMethodsSettings`; si lo
  guardado ya no valida (claves de más o de menos, edición a mano) registra un aviso con solo la
  clave y responde con los defaults: nunca expone un código ajeno ni da 500.
- El log registra solo `key` y `version`, nunca el valor.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import violated_constraint
from app.modules.settings.exceptions import (
    SectionNotAvailable,
    SettingsValidationError,
    VersionConflict,
)
from app.modules.settings.models import SettingsSection
from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    PAYMENT_METHOD_CODES,
    SECTION_DEFAULTS,
    SECTION_REGISTRY,
    SECTION_VIEWS,
    GymView,
    MembershipsPolicy,
    MembershipsSettings,
    MethodLabel,
    PaymentMethodInfo,
    PaymentMethodsSettings,
    PrivacyView,
    SectionKey,
    SectionOut,
    SectionValue,
)

GYM_NAME_FALLBACK: Final[str] = "APEX"
UNIQUE_KEY_INDEX: Final[str] = "uq_settings_sections_key"

logger = logging.getLogger("app.settings")

# Puras ---------------------------------------------------------------------------------


def _field_from(error: ValidationError) -> str:
    errores = error.errors()
    loc = errores[0].get("loc", ()) if errores else ()
    return "value." + ".".join(map(str, loc)) if loc else "value"


def validate_section(key: SectionKey, value: Mapping[str, Any]) -> SectionValue:
    """Valida `value` con el esquema de escritura de `key`; el error nunca lleva el valor."""
    esquema = SECTION_REGISTRY[key]
    try:
        return esquema.model_validate(dict(value))
    except ValidationError as error:
        campo = _field_from(error)
        raise SettingsValidationError(
            message=f"El campo {campo} no es válido.", field=campo
        ) from None


def check_version(stored: int, sent: int) -> None:
    """`VersionConflict` si la versión enviada no es la guardada (N-17)."""
    if stored != sent:
        raise VersionConflict()


def defaults_for(key: SectionKey) -> dict[str, Any]:
    """Copia de los valores por defecto de la sección."""
    return copy.deepcopy(SECTION_DEFAULTS[key])


def ensure_enabled(key: str) -> SectionKey:
    """La clave como `SectionKey` o `SectionNotAvailable` (S2-D15)."""
    try:
        seccion = SectionKey(key)
    except ValueError:
        raise SectionNotAvailable() from None
    if seccion not in ENABLED_SECTIONS:
        raise SectionNotAvailable()
    return seccion


# Lectura y escritura ----------------------------------------------------------------------


async def _row(
    session: AsyncSession, key: SectionKey, *, lock: bool = False
) -> SettingsSection | None:
    consulta = select(SettingsSection).where(SettingsSection.key == key.value)
    if lock:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(consulta)).scalar_one_or_none()


def _out(fila: SettingsSection) -> SectionOut:
    return SectionOut(
        key=SectionKey(fila.key),
        value=dict(fila.value),
        version=fila.version,
        updated_at=fila.updated_at,
        updated_by=fila.updated_by,
    )


async def get_section(session: AsyncSession, key: str) -> SectionOut:
    """La sección guardada o sus defaults con `version = 0` (leer no siembra)."""
    seccion = ensure_enabled(key)
    fila = await _row(session, seccion)
    if fila is None:
        return SectionOut(
            key=seccion, value=defaults_for(seccion), version=0, updated_at=None, updated_by=None
        )
    return _out(fila)


async def _insert_first(
    session: AsyncSession, key: SectionKey, value: dict[str, Any], by: UUID
) -> SettingsSection:
    fila = SettingsSection(key=key.value, value=value, version=1, updated_by=by)
    try:
        async with session.begin_nested():
            session.add(fila)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != UNIQUE_KEY_INDEX:
            raise
        logger.info("settings: primer guardado concurrente", extra={"settings_key": key.value})
        raise VersionConflict() from None
    return fila


async def update_section(
    session: AsyncSession, key: str, value: Mapping[str, Any], version: int, by: UUID
) -> SectionOut:
    """Guarda la sección completa con control de versión (N-17, flujo 7.3)."""
    seccion = ensure_enabled(key)
    nuevo = validate_section(seccion, value).model_dump(mode="json")
    fila = await _row(session, seccion, lock=True)
    if fila is None:
        check_version(0, version)
        fila = await _insert_first(session, seccion, nuevo, by)
    else:
        check_version(fila.version, version)
        fila.value = nuevo  # dict nuevo: el hook ve el cambio (regla transversal 5)
        fila.version = fila.version + 1
        fila.updated_by = by
        await session.flush()  # `eager_defaults`: `updated_at` ya cargado (M4)
    logger.info(
        "settings: sección guardada",
        extra={"settings_key": seccion.value, "settings_version": fila.version},
    )
    return _out(fila)


# API interna para otros módulos (S2-D45) ---------------------------------------------------


async def _read_as[ModeloT: SectionValue](
    session: AsyncSession, key: SectionKey, modelo: type[ModeloT]
) -> ModeloT:
    fila = await _row(session, key)
    return modelo.model_validate(defaults_for(key) if fila is None else dict(fila.value))


async def get(session: AsyncSession, key: SectionKey) -> SectionValue:
    """Modelo validado de la sección (lo guardado o los defaults), para consumidores."""
    seccion = ensure_enabled(key)
    return await _read_as(session, seccion, SECTION_VIEWS[seccion])


async def memberships_policy(session: AsyncSession) -> MembershipsPolicy:
    """Contrato para `memberships`: los cuatro parámetros (S2-D45)."""
    valor = await _read_as(session, SectionKey.memberships, MembershipsSettings)
    return MembershipsPolicy(
        expiring_days=valor.expiring_days,
        max_freeze_days_per_membership=valor.max_freeze_days_per_membership,
        max_freezes_per_membership=valor.max_freezes_per_membership,
        max_retroactive_days=valor.max_retroactive_days,
    )


async def current_privacy_version(session: AsyncSession) -> str | None:
    """Versión publicada de la política, o `None` si nunca se publicó (US-057 T4)."""
    return (await _read_as(session, SectionKey.privacy, PrivacyView)).policy_version


async def gym_name(session: AsyncSession) -> str:
    """Nombre del gimnasio para `GET /auth/me` y los avisos; respaldo `"APEX"`.

    Revisión Python M3: `/auth/me` corre en cada carga del panel; un valor guardado que ya no
    valida (cambio de esquema, edición a mano) daba 500 a todos. Ahora se registra un aviso
    (solo la clave, nunca el valor) y se responde con el respaldo."""
    try:
        valor = await _read_as(session, SectionKey.gym, GymView)
    except ValidationError:
        logger.warning("settings: la sección guardada no valida", extra={"settings_key": "gym"})
        return GYM_NAME_FALLBACK
    return valor.name or GYM_NAME_FALLBACK


def decorate_methods(
    codes: Sequence[str], labels: Mapping[str, MethodLabel]
) -> tuple[PaymentMethodInfo, ...]:
    """Pura: un medio por código, en el orden de `codes`, con su etiqueta o la por defecto."""
    por_defecto = SECTION_DEFAULTS[SectionKey.payment_methods]
    medios: list[PaymentMethodInfo] = []
    for codigo in codes:
        etiqueta = labels.get(codigo) or MethodLabel.model_validate(por_defecto[codigo])
        medios.append(PaymentMethodInfo(code=codigo, label=etiqueta.label, hint=etiqueta.hint))
    return tuple(medios)


async def payment_methods(session: AsyncSession) -> tuple[PaymentMethodInfo, ...]:
    """Contrato para `payments` (D24): los tres medios en orden fijo, tolerante a lo guardado."""
    clave = SectionKey.payment_methods
    try:
        valor = await _read_as(session, clave, PaymentMethodsSettings)
    except ValidationError:
        logger.warning(
            "settings: la sección guardada no valida", extra={"settings_key": clave.value}
        )
        valor = PaymentMethodsSettings.model_validate(defaults_for(clave))
    etiquetas = {codigo: getattr(valor, codigo) for codigo in PAYMENT_METHOD_CODES}
    return decorate_methods(PAYMENT_METHOD_CODES, etiquetas)
