"""Límite de intentos por IP con ventana deslizante (US-036; N-14, N-31, N-44).

- `allow(history, now, limit, window_s)`: pura. Cuentan los intentos con `now - t < window_s`;
  si se rechaza, `Retry-After = ceil(history[0] + window_s - now)`, mínimo 1.
- `client_ip(request, trusted_proxies)`: si `request.client.host` está en una red de
  confianza, se recorre `X-Forwarded-For` de derecha a izquierda y se toma la primera IP que
  no sea de confianza; si no, la IP del socket y la cabecera se ignora. Con
  `TRUSTED_PROXIES` vacío todo cuenta contra la IP del proxy: más restrictivo, nunca más abierto.
- `SlidingWindowStore`: `deque` por (bucket, clave) en un `OrderedDict`, poda en cada acceso,
  tope de claves con expulsión O(1) de la usada hace más tiempo (L-11) y `asyncio.Lock`.
  Registra todo intento procesado; el rechazado no se registra, así la ventana se libera 60 s
  después del primero.
- Un almacén por tipo de clave (`ip`, `account`, `account-global`, `user`) con tope propio
  (`configure_store_limits`, desde `RATE_LIMIT_MAX_KEYS`): llenar el de cuentas con correos
  aleatorios no expulsa las claves por IP.
- `ip_bucket_key(ip, ipv4_prefix=24)`: red de la IP (IPv4 /24 por defecto, IPv6 siempre /64);
  `rate_limit` y el límite por cuenta la usan con `ipv4_prefix=32` (IPv4 exacta; el límite por
  cuenta pasó de /24 a /32 en la revisión de seguridad V10, N-3).
- `enforce` (comprueba y, con `count=True`, registra), `record` (registra sin comprobar),
  `reserve`/`release` (reserva atómica de un cupo y su devolución: el límite por cuenta del
  login, revisión Python M2) y `forget` (borra la clave y sus subclaves `clave|...`; unlock,
  S2-D10).
- `rate_limit(bucket, limit=5, window_s=60)`: dependencia por ruta (corre antes del handler,
  así el login no evalúa la contraseña con 429) que lanza `TooManyRequestsError` con
  `Retry-After` y mensaje genérico; lleva la marca `__apex_rate_limit__` que lee la prueba de
  arquitectura. Sus topes salen de `app.state.rate_limits` (`rate_limits_from(settings)`, E5).
  Un solo proceso (uvicorn sin `--workers`): los almacenes son de memoria y `up -d api` los
  vacía (docs/RUNBOOK.md).
El log del 429 de `rate_limit` registra bucket e IP; el de `enforce` solo el bucket (nunca el
correo ni la clave, salvo `log_key=True`).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from ipaddress import IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from typing import TYPE_CHECKING, Final, Literal

from fastapi import Request

from app.core.clock import current_clock
from app.core.errors import TooManyRequestsError

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger("app.ratelimit")

DEFAULT_LIMIT: Final = 5
DEFAULT_WINDOW_S: Final = 60
DEFAULT_MAX_KEYS: Final = 10000

KeyKind = Literal["ip", "account", "account-global", "user"]
KEY_KINDS: Final[tuple[KeyKind, ...]] = ("ip", "account", "account-global", "user")


def allow(
    history: Sequence[float],
    now: float,
    limit: int = DEFAULT_LIMIT,
    window_s: int = DEFAULT_WINDOW_S,
) -> tuple[bool, int]:
    """`(permitido, segundos de Retry-After)` para una historia de marcas de tiempo."""
    vigentes = [t for t in history if now - t < window_s]
    if len(vigentes) < limit:
        return True, 0
    espera = math.ceil(min(vigentes) + window_s - now)
    return False, max(1, espera)


def _es_de_confianza(ip: str, redes: Sequence[IPv4Network | IPv6Network]) -> bool:
    try:
        direccion = ip_address(ip)
    except ValueError:
        return False
    return any(direccion in red for red in redes)


def client_ip(request: Request, trusted_proxies: Sequence[IPv4Network | IPv6Network]) -> str:
    socket_ip = request.client.host if request.client else "0.0.0.0"  # noqa: S104 - sin cliente
    if not trusted_proxies or not _es_de_confianza(socket_ip, trusted_proxies):
        return socket_ip
    cabecera = request.headers.get("x-forwarded-for", "")
    for candidata in reversed([p.strip() for p in cabecera.split(",") if p.strip()]):
        try:
            ip_address(candidata)
        except ValueError:
            return socket_ip  # cabecera mal formada: no se confía en ella
        if not _es_de_confianza(candidata, trusted_proxies):
            return candidata
    return socket_ip


class SlidingWindowStore:
    def __init__(self, max_keys: int = DEFAULT_MAX_KEYS) -> None:
        self._max_keys = max_keys
        # Orden de uso: la primera clave es la usada hace más tiempo (expulsión O(1), L-11).
        self._marcas: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._marcas)

    def _historia(self, key: tuple[str, str], now: float, window_s: int) -> deque[float]:
        """La historia podada de la clave, creada si falta (expulsa la menos usada)."""
        historia = self._marcas.get(key)
        if historia is None:
            if len(self._marcas) >= self._max_keys:
                self._marcas.popitem(last=False)
            historia = deque()
            self._marcas[key] = historia
        else:
            self._marcas.move_to_end(key)
        while historia and now - historia[0] >= window_s:
            historia.popleft()
        return historia

    async def hit(
        self, key: tuple[str, str], now: float, limit: int, window_s: int
    ) -> tuple[bool, int]:
        async with self._lock:
            historia = self._historia(key, now, window_s)
            permitido, espera = allow(historia, now, limit, window_s)
            if permitido:
                historia.append(now)
            return permitido, espera

    async def peek(
        self, key: tuple[str, str], now: float, limit: int, window_s: int
    ) -> tuple[bool, int]:
        """Como `hit`, sin registrar el intento; una clave ausente no se crea."""
        async with self._lock:
            if key not in self._marcas:
                return allow((), now, limit, window_s)
            return allow(self._historia(key, now, window_s), now, limit, window_s)

    async def release(self, key: tuple[str, str], stamp: float) -> bool:
        """Quita una marca `stamp` de la clave (la de una reserva); `False` si ya no estaba."""
        async with self._lock:
            historia = self._marcas.get(key)
            if historia is None or stamp not in historia:
                return False
            historia.remove(stamp)
            return True

    async def add(self, key: tuple[str, str], now: float, window_s: int) -> None:
        """Registra una marca sin comprobar el tope (los fallos de login, H-4)."""
        async with self._lock:
            self._historia(key, now, window_s).append(now)

    async def forget(self, key: tuple[str, str]) -> int:
        """Borra la clave y sus subclaves `clave|...` del mismo bucket; devuelve cuántas."""
        bucket, clave = key
        prefijo = f"{clave}|"
        async with self._lock:
            borrar = [
                k
                for k in self._marcas
                if k[0] == bucket and (k[1] == clave or k[1].startswith(prefijo))
            ]
            for k in borrar:
                del self._marcas[k]
            return len(borrar)


_limits: dict[KeyKind, int] = dict.fromkeys(KEY_KINDS, DEFAULT_MAX_KEYS)
_stores: dict[KeyKind, SlidingWindowStore] = {}


def reset_store() -> None:
    """Vacía todos los almacenes (pruebas; en el api lo hace recrear el contenedor)."""
    _stores.clear()


def configure_store_limits(limits: Mapping[KeyKind, int]) -> None:
    """Tope de claves por tipo de almacén; vacía los almacenes para aplicar los topes."""
    for kind, tope in limits.items():
        if kind not in KEY_KINDS or tope <= 0:
            raise ValueError(f"tope de almacén inválido: {kind}")
        _limits[kind] = tope
    reset_store()


def store_for(kind: KeyKind) -> SlidingWindowStore:
    """El almacén de ese tipo de clave, creado con su tope la primera vez."""
    store = _stores.get(kind)
    if store is None:
        store = SlidingWindowStore(_limits[kind])
        _stores[kind] = store
    return store


def ip_bucket_key(ip: str, *, ipv4_prefix: int = 24) -> str:
    """Red de la IP: IPv4 con `ipv4_prefix`, IPv6 /64; una cadena que no es IP queda igual.

    Una IPv4 mapeada en IPv6 (`::ffff:a.b.c.d`) cuenta como su IPv4: si no, todos los clientes
    que el socket reporte así compartirían un solo /64.
    """
    try:
        leida = ip_address(ip)
    except ValueError:
        return ip
    mapeada = leida.ipv4_mapped if isinstance(leida, IPv6Address) else None
    direccion = mapeada or leida
    prefijo = ipv4_prefix if direccion.version == 4 else 64
    return str(ip_network(f"{direccion}/{prefijo}", strict=False))


def _ahora() -> float:
    return current_clock().now_utc().timestamp()


async def enforce(
    bucket: str,
    key: str,
    *,
    limit: int,
    window_s: int,
    kind: KeyKind = "account",
    count: bool = True,
    log_key: bool = False,
) -> None:
    """Límite por clave arbitraria: lanza `TooManyRequestsError`; con `log_key=False` el log
    guarda solo el bucket. Con `count=False` solo comprueba (H-4: antes de argon2)."""
    store = store_for(kind)
    ahora = _ahora()
    if count:
        permitido, espera = await store.hit((bucket, key), ahora, limit, window_s)
    else:
        permitido, espera = await store.peek((bucket, key), ahora, limit, window_s)
    if not permitido:
        extra: dict[str, object] = {"bucket": bucket, "retry_after": espera}
        if log_key:
            extra["rate_key"] = key
        logger.warning("rate limit", extra=extra)
        raise TooManyRequestsError(espera)


async def reserve(
    bucket: str, key: str, *, limit: int, window_s: int, kind: KeyKind = "account"
) -> float:
    """Reserva un cupo de forma atómica (comprueba y registra bajo el mismo candado) y devuelve
    la marca para `release`; sin cupo lanza `TooManyRequestsError` (log solo con el bucket).
    Revisión Python M2: una ráfaga paralela no puede pasar toda la comprobación antes de que
    alguna sume."""
    ahora = _ahora()
    permitido, espera = await store_for(kind).hit((bucket, key), ahora, limit, window_s)
    if not permitido:
        logger.warning("rate limit", extra={"bucket": bucket, "retry_after": espera})
        raise TooManyRequestsError(espera)
    return ahora


async def release(bucket: str, key: str, stamp: float, *, kind: KeyKind = "account") -> bool:
    """Devuelve el cupo de una reserva (`stamp` de `reserve`); `False` si ya no estaba."""
    return await store_for(kind).release((bucket, key), stamp)


async def record(bucket: str, key: str, *, window_s: int, kind: KeyKind = "account") -> None:
    """Registra un intento (un fallo de login, H-4) sin comprobar."""
    await store_for(kind).add((bucket, key), _ahora(), window_s)


async def forget(bucket: str, key: str, *, kind: KeyKind = "account") -> int:
    """Olvida la clave y sus subclaves `clave|...` (unlock, S2-D10); devuelve cuántas."""
    return await store_for(kind).forget((bucket, key))


def rate_limits_from(settings: Settings) -> dict[str, tuple[int, int]]:
    """`{bucket: (límite, ventana_s)}` de las rutas por IP (E5)."""
    return {
        "login": (settings.LOGIN_IP_LIMIT, settings.LOGIN_IP_WINDOW_S),
        "refresh": (settings.REFRESH_IP_LIMIT, DEFAULT_WINDOW_S),
        "reset": (settings.RESET_IP_LIMIT, DEFAULT_WINDOW_S),
        "forgot": (settings.FORGOT_IP_LIMIT, DEFAULT_WINDOW_S),
        "logout": (settings.LOGOUT_IP_LIMIT, DEFAULT_WINDOW_S),
    }


def rate_limit(
    bucket: str, limit: int = DEFAULT_LIMIT, window_s: int = DEFAULT_WINDOW_S
) -> Callable[..., Awaitable[None]]:
    """Dependencia de FastAPI: `dependencies=[Depends(rate_limit("login"))]`."""

    async def _dependencia(request: Request) -> None:
        estado = request.app.state
        redes: Sequence[IPv4Network | IPv6Network] = getattr(estado, "trusted_proxies", ())
        topes: Mapping[str, tuple[int, int]] = getattr(estado, "rate_limits", {})
        tope, ventana = topes.get(bucket, (limit, window_s))
        ip = client_ip(request, redes)
        clave = ip_bucket_key(ip, ipv4_prefix=32)  # IPv4 exacta, IPv6 por /64
        permitido, espera = await store_for("ip").hit((bucket, clave), _ahora(), tope, ventana)
        if not permitido:
            logger.warning("rate limit", extra={"bucket": bucket, "ip": ip, "retry_after": espera})
            raise TooManyRequestsError(espera)

    _dependencia.__apex_rate_limit__ = bucket  # type: ignore[attr-defined]
    return _dependencia
