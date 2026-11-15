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
  `current_privacy_version` (`None` sin política publicada), `consent_required_from` (S6-C3) y
  `gym_name` (respaldo `"APEX"`,
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
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import current_clock
from app.core.config import Settings
from app.core.db import violated_constraint
from app.core.security import hash_opaque_token, new_opaque_token, opaque_token_matches
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
    TV_TOKEN_LAST_CHARS,
    ChannelsSettings,
    ClassesSettings,
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
    TvConfig,
    TvEditable,
    TvSectionOut,
    TvStored,
    TvTokenOut,
    TvView,
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


def _generic(key: str) -> SectionKey:
    """`ensure_enabled` para las funciones genéricas: `tv` queda fuera (S8-D30)."""
    seccion = ensure_enabled(key)
    if seccion is SectionKey.tv:
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
    """La sección guardada o sus defaults con `version = 0` (leer no siembra). `tv` se lee solo
    por `get_tv` (S8-D30, L-1): aquí es 404."""
    seccion = _generic(key)
    fila = await _row(session, seccion)
    if fila is None:
        return SectionOut(
            key=seccion, value=defaults_for(seccion), version=0, updated_at=None, updated_by=None
        )
    return _out(fila)


async def _insert_first(
    session: AsyncSession, key: SectionKey, value: dict[str, Any], by: UUID, *, version: int = 1
) -> SettingsSection:
    fila = SettingsSection(key=key.value, value=value, version=version, updated_by=by)
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
    """Guarda la sección completa con control de versión (N-17, flujo 7.3). `tv` solo se escribe
    por `update_tv`, `regenerate_tv_token` y `revoke_tv_token` (S8-D30): aquí es 404."""
    seccion = _generic(key)
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


# Sección `tv` (S8-C1; S8-D17, S8-D30, S8-D32): solo por estas funciones --------------------------


_TV: Final = SectionKey.tv


def _tv_stored(fila: SettingsSection, *, repair: bool) -> TvStored:
    """Lo guardado en la fila. Si ya no valida (L-3): con `repair` parte de los defaults (sin
    token), para que el admin pueda leer, regenerar o revocar y reparar la fila; sin él, 422."""
    try:
        return TvStored.model_validate(dict(fila.value))
    except ValidationError:
        logger.warning("settings: la sección guardada no valida", extra={"settings_key": "tv"})
        if repair:
            return TvStored.model_validate(defaults_for(_TV))
        raise SettingsValidationError(
            message="La sección guardada no es válida; regenera el token para repararla."
        ) from None


def _tv_view(fila: SettingsSection | None) -> TvSectionOut:
    """La vista (sin hash) de la fila, o de los defaults con `version = 0`."""
    if fila is None:
        guardado = TvStored.model_validate(defaults_for(_TV))
        return _tv_out(guardado, 0, None, None)
    return _tv_out(_tv_stored(fila, repair=True), fila.version, fila.updated_at, fila.updated_by)


def _tv_out(
    guardado: TvStored, version: int, updated_at: datetime | None, updated_by: UUID | None
) -> TvSectionOut:
    return TvSectionOut(
        key=_TV,
        version=version,
        updated_at=updated_at,
        updated_by=updated_by,
        value=TvView(
            refresh_seconds=guardado.refresh_seconds,
            show_leaderboard=guardado.show_leaderboard,
            has_token=guardado.device_token_hash is not None,
            token_last4=guardado.token_last4,
            rotated_at=guardado.rotated_at,
        ),
    )


async def get_tv(session: AsyncSession) -> TvSectionOut:
    """La vista de la TV (sin hash): la fila o los defaults con `version = 0`."""
    return _tv_view(await _row(session, _TV))


async def _tv_locked(session: AsyncSession, by: UUID) -> SettingsSection:
    """La fila `tv` bloqueada `FOR UPDATE`; si no existe la crea con los defaults (dentro de
    `begin_nested`) y la vuelve a tomar bloqueada. Si otra sesión la creó a la vez, toma la suya."""
    fila = await _row(session, _TV, lock=True)
    if fila is not None:
        return fila
    try:
        # versión 0: el primer guardado real la sube a 1 (como `get_tv` sin fila)
        await _insert_first(session, _TV, defaults_for(_TV), by, version=0)
    except VersionConflict:
        pass
    fila = await _row(session, _TV, lock=True)
    if fila is None:  # pragma: no cover - la fila existe tras el insert o el conflicto
        raise VersionConflict()
    return fila


async def _tv_save(
    session: AsyncSession, fila: SettingsSection, nuevo: TvStored, by: UUID
) -> SettingsSection:
    fila.value = nuevo.model_dump(mode="json")  # dict nuevo: el hook ve el cambio
    fila.version = fila.version + 1
    fila.updated_by = by
    await session.flush()
    logger.info(
        "settings: tv guardada",
        extra={"settings_key": "tv", "settings_version": fila.version},
    )
    return fila


async def update_tv(
    session: AsyncSession, patch: TvEditable, version: int, by: UUID
) -> TvSectionOut:
    """`PATCH`: `FOR UPDATE`, `check_version` y el hash, `token_last4` y `rotated_at` de LA FILA
    BLOQUEADA (H-1); solo cambian `refresh_seconds` y `show_leaderboard`."""
    fila = await _tv_locked(session, by)
    check_version(fila.version, version)
    actual = _tv_stored(fila, repair=False)
    nuevo = actual.model_copy(
        update={
            "refresh_seconds": patch.refresh_seconds,
            "show_leaderboard": patch.show_leaderboard,
        }
    )
    return _tv_view(await _tv_save(session, fila, nuevo, by))


async def regenerate_tv_token(session: AsyncSession, by: UUID, *, origin: str) -> TvTokenOut:
    """Token nuevo: guarda su SHA-256, sube `version` bajo el mismo candado (crea la fila si no
    existe) y devuelve el token y `origin/tv#token=<token>` una sola vez (S8-D32)."""
    fila = await _tv_locked(session, by)
    token = new_opaque_token()
    ahora = current_clock().now_utc()
    ultimos = token[-TV_TOKEN_LAST_CHARS:]
    nuevo = _tv_stored(fila, repair=True).model_copy(
        update={
            "device_token_hash": hash_opaque_token(token),
            "token_last4": ultimos,
            "rotated_at": ahora,
        }
    )
    guardada = await _tv_save(session, fila, nuevo, by)
    return TvTokenOut(
        token=token,
        url=f"{origin.rstrip('/')}/tv#token={token}",
        token_last4=ultimos,
        rotated_at=ahora,
        version=guardada.version,
    )


async def revoke_tv_token(session: AsyncSession, by: UUID) -> TvSectionOut:
    """Deja `device_token_hash = None` (L-7), bajo el mismo candado, y sube `version`."""
    fila = await _tv_locked(session, by)
    nuevo = _tv_stored(fila, repair=True).model_copy(
        update={"device_token_hash": None, "token_last4": None, "rotated_at": None}
    )
    return _tv_view(await _tv_save(session, fila, nuevo, by))


async def verify_tv_token(session: AsyncSession, token: str | None) -> TvConfig | None:
    """`TvConfig` si `token` es el vigente; `None` sin fila, sin hash, cabecera vacía o valor no
    válido, o fila que ya no valida (L-1): nunca 500 y registra solo la clave."""
    if not token:
        return None
    fila = await _row(session, _TV)
    if fila is None:
        return None
    try:
        guardado = TvStored.model_validate(dict(fila.value))
    except ValidationError:
        logger.warning("settings: la sección guardada no valida", extra={"settings_key": "tv"})
        return None
    if guardado.device_token_hash is None:
        return None
    if not opaque_token_matches(token, guardado.device_token_hash):
        return None
    return TvConfig(
        refresh_seconds=guardado.refresh_seconds, show_leaderboard=guardado.show_leaderboard
    )


# API interna para otros módulos (S2-D45) ---------------------------------------------------


async def _read_as[ModeloT: SectionValue](
    session: AsyncSession, key: SectionKey, modelo: type[ModeloT]
) -> ModeloT:
    fila = await _row(session, key)
    return modelo.model_validate(defaults_for(key) if fila is None else dict(fila.value))


async def get(session: AsyncSession, key: SectionKey) -> SectionValue:
    """Modelo validado de la sección (lo guardado o los defaults), para consumidores."""
    seccion = _generic(key)  # S8-C1b (L-2): `tv` (con su hash) solo sale por `verify_tv_token`
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


async def classes(session: AsyncSession) -> ClassesSettings:
    """Contrato para `classes` (S7-D8): cupo y ventana por defecto, tolerante a lo guardado."""
    try:
        return await _read_as(session, SectionKey.classes, ClassesSettings)
    except ValidationError:
        logger.warning(
            "settings: la sección guardada no valida",
            extra={"settings_key": SectionKey.classes.value},
        )
        return ClassesSettings.model_validate(defaults_for(SectionKey.classes))


async def current_privacy_version(session: AsyncSession) -> str | None:
    """Versión publicada de la política, o `None` si nunca se publicó (US-057 T4)."""
    return (await _read_as(session, SectionKey.privacy, PrivacyView)).policy_version


async def consent_required_from(session: AsyncSession) -> date | None:
    """Fecha de corte desde la que el alta exige la autorización de datos (S6-C3, US-149), o
    `None` si nunca se fijó (no se exige nada, Q16). Lectura de la sección `privacy`."""
    return (await _read_as(session, SectionKey.privacy, PrivacyView)).consent_required_from


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


def channels_credentials_present(config: Settings) -> dict[str, bool]:
    """Pura (S5-D30): `{"email": bool, "telegram": bool}` desde `core.config.Settings`, sin valores.
    Correo: servidor y remitente; Telegram: token y chat."""
    return {
        "email": bool(config.SMTP_HOST) and bool(config.SMTP_FROM),
        "telegram": config.TELEGRAM_BOT_TOKEN is not None and bool(config.TELEGRAM_CHAT_ID),
    }


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


TELEGRAM_GATE_TTL_S: Final = 30.0


def telegram_enabled_gate(
    session_factory: async_sessionmaker[AsyncSession], *, ttl_s: float = TELEGRAM_GATE_TTL_S
) -> Callable[[], Awaitable[bool]]:
    """Puerta de `TelegramAlertSink` (S5-D265d): lee `channels.telegram.enabled` en una sesión
    propia (sin fila = apagado) y cachea el valor `ttl_s` segundos con `current_clock()`."""
    cache: list[tuple[bool, float]] = []

    async def puerta() -> bool:
        ahora = current_clock().now_utc().timestamp()
        if cache and ahora < cache[0][1]:
            return cache[0][0]
        try:
            async with session_factory() as session:
                valor = await get(session, SectionKey.channels)
            encendido = isinstance(valor, ChannelsSettings) and valor.telegram.enabled
        except Exception as error:
            # Apertura ante fallo, cacheada el mismo TTL: una consulta y un aviso por ventana.
            logger.warning(
                "settings: puerta de telegram no leída", extra={"error_type": type(error).__name__}
            )
            encendido = True
        cache[:] = [(encendido, ahora + ttl_s)]
        return encendido

    return puerta
