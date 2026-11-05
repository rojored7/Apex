"""`TelegramAlertSink`: alertas del equipo por Telegram (S5-B4; S5-D29, S5-D58, S5-D203, M-8).

- `render_message(code, context, front_base_url)`: pura, en español, solo enteros, nombres de job y
  el enlace a `/avisos/hoy` (únicamente en `notify_summary`). Nunca nombres de personas ni claves
  ajenas. Un código desconocido da la línea genérica `APEX · alerta <code>` sin contexto.
- `TelegramAlertSink.send` es síncrono: agenda un `asyncio.Task` guardado en un conjunto (sin
  bucle en marcha, la alerta se descarta con una línea fija). La tarea atrapa TODA excepción y
  registra solo su tipo: la URL del bot lleva el token (M-8). `flush()` espera las pendientes.
- POST `{api_base}/bot{token}/sendMessage` con `httpx.AsyncClient` (sin `parse_mode`, sin seguir
  redirecciones).
- `register_from_settings(settings)` registra el sink solo con token Y chat (idempotente: reemplaza
  el sink de Telegram anterior); `flush()` de módulo espera las tareas de todos los sinks de
  Telegram registrados (apagado del api y del worker).

Con `core/crypto/openbao_provider.py`, el único archivo que importa `httpx`. Solo lo importan las
raíces de composición (`main.py`, `worker/main.py`).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Final

import httpx
from pydantic import SecretStr

from app.core import alerts
from app.core.clock import current_clock
from app.core.config import TELEGRAM_OFFICIAL_API, Settings

logger = logging.getLogger("app.alerts.telegram")

# httpx registra `HTTP Request: POST <url>` con el token del bot en la ruta: se silencia aquí, en
# el único sitio que le habla a Telegram (S5-D58).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_NOMBRE: Final = re.compile(r"[A-Za-z0-9_.-]{1,40}")
_FECHA: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_CONTEOS: Final[tuple[str, ...]] = ("generados", "enviados", "fallidos", "omitidos", "pendientes")
_MAX_TEXTO: Final = 4096
EnabledGate = Callable[[], Awaitable[bool]]
"""Puerta async que dice si Telegram está encendido por el admin (S5-D265d)."""
_gate: EnabledGate | None = None


def set_enabled_gate(gate: EnabledGate | None) -> None:
    """Registra (o quita, con `None`) la puerta que consulta el sink antes de cada envío. La
    registran `main.py` y `worker/runtime.py` (`core` no importa módulos)."""
    global _gate
    _gate = gate


def get_enabled_gate() -> EnabledGate | None:
    return _gate


MAX_PENDING: Final = 20
"""Tareas vivas por sink (S5-D206): con la cola llena, la alerta se descarta."""
DEDUP_WINDOW: Final = timedelta(seconds=60)
"""Una misma alerta repetida dentro de la ventana no crea otra tarea (S5-D206)."""


def _entero(contexto: Mapping[str, object], clave: str) -> int:
    valor = contexto.get(clave)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def _nombre(contexto: Mapping[str, object], clave: str, defecto: str = "desconocido") -> str:
    valor = contexto.get(clave)
    if isinstance(valor, str) and _NOMBRE.fullmatch(valor):
        return valor
    return defecto


def _job_failed(contexto: Mapping[str, object]) -> str:
    partes = [f"APEX · el job {_nombre(contexto, 'job')} falló"]
    intentos = _entero(contexto, "attempts")
    if intentos:
        partes.append(f"tras {intentos} intentos")
    fecha = contexto.get("run_date")
    if isinstance(fecha, str) and _FECHA.fullmatch(fecha):
        partes.append(f"(corrida del {fecha})")
    tipo = contexto.get("error_type")
    if isinstance(tipo, str) and tipo.isidentifier():
        partes.append(f"[{tipo}]")
    return " ".join(partes) + "."


def _notify_summary(contexto: Mapping[str, object], front_base_url: str) -> str:
    cifras = ", ".join(f"{c} {_entero(contexto, c)}" for c in _CONTEOS)
    enlace = f"{front_base_url.rstrip('/')}/avisos/hoy"
    return f"APEX · resumen de avisos de hoy: {cifras}. Revisa: {enlace}"


_FIJOS: Final[dict[str, str]] = {
    "backup_unhealthy": "APEX · el respaldo tiene problemas. Revisa el servicio de respaldo.",
    "crypto_sealed": "APEX · el custodio de llaves está sellado: el api opera sin llaves.",
    "crypto_recovered": "APEX · el custodio de llaves se recuperó: el api volvió a operar.",
    "crypto_forbidden": "APEX · el custodio de llaves rechazó el acceso del servicio.",
    "crypto_unwrap_failed": "APEX · el custodio de llaves no pudo abrir las llaves de datos.",
    "mail_unconfigured": (
        "APEX · el correo está activo pero faltan las credenciales SMTP: los avisos esperan."
    ),
}


def render_message(code: str, context: Mapping[str, object], front_base_url: str) -> str:
    """El texto de la alerta (hasta 4096 caracteres); pura y sin datos de personas."""
    if code == "job_failed":
        texto = _job_failed(context)
    elif code == "notify_summary":
        texto = _notify_summary(context, front_base_url)
    elif code in _FIJOS:
        texto = _FIJOS[code]
    else:
        texto = f"APEX · alerta {code if _NOMBRE.fullmatch(code) else 'desconocida'}"
    return texto[:_MAX_TEXTO]


class TelegramAlertSink:
    """Sink de `core.alerts` hacia el chat del equipo (nunca hacia un socio)."""

    def __init__(
        self,
        token: SecretStr,
        chat_id: str,
        *,
        timeout_s: float,
        front_base_url: str,
        api_base: str = TELEGRAM_OFFICIAL_API,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout_s = timeout_s
        self._front_base_url = front_base_url
        self._api_base = api_base.rstrip("/")
        self._tasks: set[asyncio.Task[None]] = set()
        self._recientes: dict[tuple[str, str], datetime] = {}
        self.dropped = 0
        self.skipped = 0

    def __repr__(self) -> str:
        return "TelegramAlertSink()"

    def send(self, code: str, context: Mapping[str, object]) -> None:
        """Agenda el envío y vuelve de inmediato; no espera a la red."""
        if self._es_repetida(code, context):
            return
        if len(self._tasks) >= MAX_PENDING:
            self.dropped += 1
            logger.warning("alerta de telegram descartada: cola llena")
            return
        texto = render_message(code, context, self._front_base_url)
        try:
            bucle = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("alerta de telegram descartada: no hay bucle en marcha")
            return
        tarea = bucle.create_task(self._publicar_si_esta_encendido(texto))
        self._tasks.add(tarea)
        tarea.add_done_callback(self._tasks.discard)

    def _es_repetida(self, code: str, context: Mapping[str, object]) -> bool:
        """Misma alerta (código y job) dentro de `DEDUP_WINDOW`: no crea tarea (S5-D206)."""
        ahora = current_clock().now_utc()
        self._recientes = {k: t for k, t in self._recientes.items() if ahora - t < DEDUP_WINDOW}
        clave = (code, _nombre(context, "job", ""))
        if clave in self._recientes:
            return True
        self._recientes[clave] = ahora
        return False

    async def _publicar_si_esta_encendido(self, texto: str) -> None:
        """Consulta la puerta (S5-D265d): apagado por el admin, no envía y cuenta `skipped`. Si la
        puerta falla se envía igual: una alerta del equipo vale más que un ajuste sin leer."""
        if _gate is not None:
            try:
                encendido = await _gate()
            except Exception as error:
                logger.warning(
                    "puerta de telegram no leída", extra={"error_type": type(error).__name__}
                )
                encendido = True
            if not encendido:
                self.skipped += 1
                return
        await self._publicar(texto)

    async def _publicar(self, texto: str) -> None:
        """Atrapa todo: solo el tipo de la excepción llega al log (la URL lleva el token)."""
        try:
            url = f"{self._api_base}/bot{self._token.get_secret_value()}/sendMessage"
            async with httpx.AsyncClient(
                timeout=self._timeout_s, follow_redirects=False, trust_env=False
            ) as c:
                respuesta = await c.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": texto,
                        "disable_web_page_preview": True,
                    },
                )
            if respuesta.status_code >= 300:
                logger.warning(
                    "telegram rechazó la alerta", extra={"http_status": respuesta.status_code}
                )
        except Exception as error:
            logger.warning(
                "alerta de telegram no enviada", extra={"error_type": type(error).__name__}
            )

    async def flush(self) -> None:
        """Espera las tareas pendientes de ESTE bucle (las de otro ya no se pueden esperar)."""
        bucle = asyncio.get_running_loop()
        propias = [t for t in self._tasks if t.get_loop() is bucle]
        if propias:
            await asyncio.gather(*propias, return_exceptions=True)


def register_from_settings(settings: Settings) -> bool:
    """Registra el sink si hay token Y chat; reemplaza el sink de Telegram previo (idempotente)."""
    if settings.TELEGRAM_BOT_TOKEN is None or settings.TELEGRAM_CHAT_ID is None:
        return False
    for previo in alerts.sinks_of_type(TelegramAlertSink):
        alerts.unregister_sink(previo)
    alerts.register_sink(
        TelegramAlertSink(
            settings.TELEGRAM_BOT_TOKEN,
            settings.TELEGRAM_CHAT_ID,
            timeout_s=float(settings.NOTIFY_NET_TIMEOUT_S),
            front_base_url=settings.FRONT_BASE_URL,
            api_base=settings.TELEGRAM_API_BASE,
        )
    )
    return True


async def flush() -> None:
    """Espera las tareas de todos los `TelegramAlertSink` registrados."""
    for sink in alerts.sinks_of_type(TelegramAlertSink):
        await sink.flush()
