"""Límite de intentos por IP con ventana deslizante (US-036; N-14, N-31, N-44).

- `allow(history, now, limit, window_s)`: pura. Cuentan los intentos con `now - t < window_s`;
  si se rechaza, `Retry-After = ceil(history[0] + window_s - now)`, mínimo 1.
- `client_ip(request, trusted_proxies)`: si `request.client.host` está en una red de
  confianza, se recorre `X-Forwarded-For` de derecha a izquierda y se toma la primera IP que
  no sea de confianza; si no, la IP del socket y la cabecera se ignora. Con
  `TRUSTED_PROXIES` vacío todo cuenta contra la IP del proxy: más restrictivo, nunca más abierto.
- `SlidingWindowStore`: `deque` por (bucket, IP), poda en cada acceso, tope de claves (expulsa
  la más antigua) y `asyncio.Lock`. Registra todo intento procesado; el rechazado no se
  registra, así la ventana se libera 60 s después del primero.
- `rate_limit(bucket, limit=5, window_s=60)`: dependencia por ruta (corre antes del handler,
  así el login no evalúa la contraseña con 429) que lanza `TooManyRequestsError` con
  `Retry-After` y mensaje genérico; lleva la marca `__apex_rate_limit__` que lee la prueba de
  arquitectura. Un solo proceso (uvicorn sin `--workers`): el almacén es de memoria.
El log del 429 registra bucket e IP, nunca el correo.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import Final

from fastapi import Request

from app.core.clock import current_clock
from app.core.errors import TooManyRequestsError

logger = logging.getLogger("app.ratelimit")

DEFAULT_LIMIT: Final = 5
DEFAULT_WINDOW_S: Final = 60
DEFAULT_MAX_KEYS: Final = 10000


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
        self._marcas: dict[tuple[str, str], deque[float]] = {}
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._marcas)

    async def hit(
        self, key: tuple[str, str], now: float, limit: int, window_s: int
    ) -> tuple[bool, int]:
        async with self._lock:
            historia = self._marcas.get(key)
            if historia is None:
                if len(self._marcas) >= self._max_keys:
                    mas_vieja = min(
                        self._marcas, key=lambda k: self._marcas[k][0] if self._marcas[k] else 0.0
                    )
                    del self._marcas[mas_vieja]
                historia = deque()
                self._marcas[key] = historia
            while historia and now - historia[0] >= window_s:
                historia.popleft()
            permitido, espera = allow(historia, now, limit, window_s)
            if permitido:
                historia.append(now)
            return permitido, espera


_store: SlidingWindowStore | None = None


def _get_store(max_keys: int) -> SlidingWindowStore:
    global _store
    if _store is None:
        _store = SlidingWindowStore(max_keys)
    return _store


def reset_store() -> None:
    global _store
    _store = None


def rate_limit(
    bucket: str, limit: int = DEFAULT_LIMIT, window_s: int = DEFAULT_WINDOW_S
) -> Callable[..., Awaitable[None]]:
    """Dependencia de FastAPI: `dependencies=[Depends(rate_limit("login"))]`."""

    async def _dependencia(request: Request) -> None:
        estado = request.app.state
        redes: Sequence[IPv4Network | IPv6Network] = getattr(estado, "trusted_proxies", ())
        max_keys = int(getattr(estado, "rate_limit_max_keys", DEFAULT_MAX_KEYS))
        ip = client_ip(request, redes)
        ahora = current_clock().now_utc().timestamp()
        permitido, espera = await _get_store(max_keys).hit((bucket, ip), ahora, limit, window_s)
        if not permitido:
            logger.warning("rate limit", extra={"bucket": bucket, "ip": ip, "retry_after": espera})
            raise TooManyRequestsError(espera)

    _dependencia.__apex_rate_limit__ = bucket  # type: ignore[attr-defined]
    return _dependencia
