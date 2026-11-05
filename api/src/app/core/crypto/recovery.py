"""Sondeo y recuperación del keyring tras el sellado (S5-B3; S5-D16, S5-D70, S5-D195).

- `try_load`: un intento de cargar el keyring del proceso con el proveedor de `current_provider()`.
  El api pasa `create_missing=True` (`ensure_keys`); el worker, `False` y `classes` (solo `SELECT`
  sobre `crypto_keys`, nunca `INSERT`). Devuelve el estado público; solo degrada con
  `CryptoUnavailable` de razón `sealed` o `unreachable` (M-4): `unwrap_failed`, `key_missing` y
  `forbidden` se propagan sin crear llaves.
- `poll_forever`: tarea del `lifespan`; reintenta cada `CRYPTO_RECOVERY_POLL_S` mientras el estado
  no sea `ok`. Una línea de log y una alerta por transición (`crypto_sealed`, `crypto_recovered`).
- El estado vive en el proceso; `reset()` lo olvida (pruebas). Ningún log lleva URL, token ni
  cuerpo del custodio.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.alerts import alert
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import Keyring, configure_keyring, current_keyring
from app.core.crypto.provider import current_provider, make_resolver
from app.core.crypto.state import CryptoState, ReasonAware

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
OnLoaded = Callable[[], Awaitable[None]]
JITTER_MAX_S: Final = 2.0
"""Tope del jitter aleatorio del sondeo (S5-D200, L4): varios procesos no sondean a la vez."""
ALERT_FORBIDDEN: Final = "crypto_forbidden"
ALERT_UNWRAP_FAILED: Final = "crypto_unwrap_failed"
ALERT_SEALED: Final = "crypto_sealed"
ALERT_RECOVERED: Final = "crypto_recovered"

_state: CryptoState = "unknown"
_degraded: bool = False
_racha: str | None = None
"""Código de alerta ya emitido en la racha de fallos del sondeo (S5-D200)."""


def current_state() -> CryptoState:
    """Último estado de `try_load` u `observe` en este proceso (`unknown` antes del primero)."""
    return _state


def is_loaded() -> bool:
    """Hay keyring cargado en el proceso (el real, no una marca: lo que `/health` debe decir)."""
    try:
        current_keyring()
    except CryptoUnavailable:
        return False
    return True


def reset() -> None:
    """Olvida estado, aviso y racha. El `finally` del lifespan y de `worker_runtime` lo llaman junto
    con `configure_keyring(None)` (S5-D198): la app siguiente del proceso parte de cero."""
    global _state, _degraded, _racha
    _state, _degraded, _racha = "unknown", False, None


def _transition(state: CryptoState) -> None:
    """Fija el estado; una línea y una alerta solo al cruzar entre degradado y sano."""
    global _state, _degraded
    _state = state
    if state != "ok" and not _degraded:
        _degraded = True
        logger.warning("crypto sealed: el custodio de llaves no está disponible (%s)", state)
        alert(ALERT_SEALED)
    elif state == "ok" and _degraded:
        _degraded = False
        logger.info("crypto recovered: el custodio de llaves volvió; keyring cargado")
        alert(ALERT_RECOVERED)


def observe(state: CryptoState) -> None:
    """Lo que el check `crypto` de `/health` ve (S5-D202): un re-sellado con el keyring en memoria
    emite log y `crypto_sealed` una vez, y `crypto_recovered` al volver, con la misma
    deduplicación que `try_load`."""
    if state != "unknown":
        _transition(state)


async def _load(
    session: AsyncSession,
    settings: Settings,
    *,
    create_missing: bool,
    classes: frozenset[str] | None,
) -> None:
    proveedor = current_provider()
    resolver = make_resolver(settings, creation=proveedor)
    if create_missing:
        await ensure_keys(session, proveedor, resolver)
        return
    keyring = Keyring()
    await keyring.load_all(session, resolver, classes=classes)
    configure_keyring(keyring)


async def try_load(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    create_missing: bool,
    classes: frozenset[str] | None = None,
    on_loaded: OnLoaded | None = None,
) -> CryptoState:
    """Intenta cargar el keyring del proceso (api: `ensure_keys`; worker: solo `load_all`).

    Solo `sealed` y `unreachable` degradan. Un token sin permiso (`forbidden`, que el proveedor
    deja en `last_reason`, S5-D200), `unwrap_failed` y `key_missing` se propagan. `on_loaded` corre
    cuando el estado pasa a `ok` desde uno degradado (S5-D199: los pasos de arranque pendientes);
    si falla, el error sube y no se reintenta (el estado ya es `ok`)."""
    if create_missing and classes is not None:
        raise ValueError("classes solo se admite con create_missing=False (worker)")
    antes = _degraded
    try:
        proveedor = current_provider()
        estado = await proveedor.status()
        if estado != "ok":
            if isinstance(proveedor, ReasonAware) and proveedor.last_reason == "forbidden":
                raise CryptoUnavailable("forbidden")
            _transition(estado)
            return _state
        with actor_scope(SYSTEM_USER_ID):
            async with session_factory() as session, session.begin():
                await _load(session, settings, create_missing=create_missing, classes=classes)
        current_keyring()  # guarda ante un `_load` que no dejó keyring (cuenta como sellado)
    except CryptoUnavailable as error:
        if error.reason in ("sealed", "not_loaded"):
            _transition("sealed")
        elif error.reason == "unreachable":
            _transition("unreachable")
        else:
            raise
        return _state
    _transition("ok")
    if antes and on_loaded is not None:
        await on_loaded()
    return _state


def _alertar_racha(error: Exception) -> bool:
    """Alerta `crypto_forbidden` o `crypto_unwrap_failed` una vez por racha. Devuelve si el error
    era de custodia (con código conocido); los demás se registran con traza en el primero."""
    global _racha
    if isinstance(error, CryptoUnavailable) and error.reason == "forbidden":
        alerta = ALERT_FORBIDDEN
    elif isinstance(error, CryptoError) and error.code in ("unwrap_failed", "key_missing"):
        alerta = ALERT_UNWRAP_FAILED
    else:
        return False
    if _racha != alerta:
        _racha = alerta
        alert(alerta)
        logger.error("crypto recovery failed: %s", alerta)
    return True


async def poll_forever(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    create_missing: bool,
    classes: frozenset[str] | None = None,
    sleep: Sleep = asyncio.sleep,
    jitter: Callable[[], float] = lambda: random.uniform(0.0, JITTER_MAX_S),  # noqa: S311
    on_loaded: OnLoaded | None = None,
) -> None:
    """Tarea del `lifespan`: cada `CRYPTO_RECOVERY_POLL_S` (más un jitter de 0 a 2 s) reintenta
    mientras no haya `ok` con keyring (S5-D198); con el keyring cargado solo duerme. Un fallo ajeno
    al sello no la mata (S5-D200): `forbidden`, `unwrap_failed` y `key_missing` alertan una vez por
    racha; cualquier otro error se registra con traza solo en el primero de la racha. La cancela
    el `finally` de quien la lanzó."""
    global _racha
    traza_pendiente = True
    while True:
        await sleep(settings.CRYPTO_RECOVERY_POLL_S + jitter())
        if _state == "ok" and is_loaded():
            continue
        try:
            await try_load(
                session_factory,
                settings,
                create_missing=create_missing,
                classes=classes,
                on_loaded=on_loaded,
            )
        except Exception as error:
            if not _alertar_racha(error) and traza_pendiente:
                traza_pendiente = False
                logger.error("crypto recovery failed: %s", type(error).__name__, exc_info=True)
        else:
            _racha = None
            traza_pendiente = True
