"""Kit de las pruebas de canales de B4 (correo SMTP y Telegram). Rojo B4.

- `settings_canales(**cambios)`: `Settings` mínima sin base ni archivos (`_env_file=None`) con los
  datos de correo y Telegram del test; `ENV=dev` salvo que se pida otra cosa.
- `SmtpFalso` y `instalar_smtp`: doble de `smtplib.SMTP` que registra lo que se le hace y puede
  fallar en una etapa (`init`, `starttls`, `login`, `send_message`).
- `TelegramFalso` e `instalar_telegram`: sustituye `httpx.AsyncClient` por un cliente con
  `httpx.MockTransport`, para que la prueba vea las peticiones y los argumentos del cliente.
"""

from __future__ import annotations

import smtplib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Self

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, _a_config_error

SMTP_COMPLETO: dict[str, Any] = {
    "SMTP_HOST": "smtp.ejemplo.test",
    "SMTP_PORT": 587,
    "SMTP_USER": "apex",
    "SMTP_PASSWORD": "clave-smtp-no-real",
    "SMTP_FROM": "apex@ejemplo.test",
}
TOKEN_BOT = "123456:AAH-token-no-real-1234567890"  # noqa: S105
CHAT_ID = "-1001234567890"


def settings_canales(**cambios: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql+asyncpg://apex:clave@db:5432/apex",
        "JWT_PRIVATE_KEY_PATH": Path("/run/apex/keys/jwt_ed25519.pem"),
        "CRYPTO_PROVIDER": "local",
        "CRYPTO_LOCAL_KEK_PATH": Path("/run/apex/keys/kek.bin"),
        "UPLOADS_DIR": Path("/data/uploads"),
        "CORS_ORIGINS": ["http://localhost"],
        "ENV": "dev",
        "FRONT_BASE_URL": "https://gym.ejemplo.test",
    }
    try:
        return Settings(_env_file=None, **{**base, **cambios})  # type: ignore[arg-type]
    except ValidationError as exc:  # como `load_settings`: ConfigError sin valores
        raise _a_config_error(exc) from None


@dataclass
class SmtpFalso:
    """Registro compartido de todas las conexiones SMTP que abre el código bajo prueba."""

    fallo: BaseException | None = None
    etapa: str = "send_message"
    conexiones: list[ConexionSmtp] = field(default_factory=list)

    @property
    def mensajes(self) -> list[EmailMessage]:
        return [m for c in self.conexiones for m in c.mensajes]


class ConexionSmtp:
    def __init__(self, registro: SmtpFalso, host: str, port: int, **kwargs: Any) -> None:
        self.registro = registro
        self.host, self.port, self.kwargs = host, port, kwargs
        self.hilo = threading.get_ident()
        self.eventos: list[str] = []
        self.contexto: Any = None
        self.credenciales: tuple[str, str] | None = None
        self.mensajes: list[EmailMessage] = []
        self.cerrada = False
        registro.conexiones.append(self)
        self._falla("init")

    def _falla(self, etapa: str) -> None:
        if self.registro.fallo is not None and self.registro.etapa == etapa:
            raise self.registro.fallo

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ehlo(self, *args: object) -> tuple[int, bytes]:
        self.eventos.append("ehlo")
        return 250, b"ok"

    def starttls(self, *args: object, context: Any = None, **kwargs: Any) -> tuple[int, bytes]:
        self._falla("starttls")
        self.eventos.append("starttls")
        self.contexto = context
        return 220, b"ok"

    def login(self, user: str, password: str, **kwargs: Any) -> tuple[int, bytes]:
        self._falla("login")
        self.eventos.append("login")
        self.credenciales = (user, password)
        return 235, b"ok"

    def send_message(self, msg: EmailMessage, *args: object, **kwargs: Any) -> dict[str, Any]:
        self._falla("send_message")
        self.eventos.append("send_message")
        self.mensajes.append(msg)
        return {}

    def quit(self) -> tuple[int, bytes]:
        self.close()
        return 221, b"bye"

    def close(self) -> None:
        self.cerrada = True


def instalar_smtp(monkeypatch: pytest.MonkeyPatch) -> SmtpFalso:
    """Sustituye `smtplib.SMTP` (y prohíbe `SMTP_SSL`: el contrato es STARTTLS en 587)."""
    registro = SmtpFalso()

    def fabrica(host: str = "", port: int = 0, **kwargs: Any) -> ConexionSmtp:
        return ConexionSmtp(registro, host, port, **kwargs)

    def sin_ssl(*args: object, **kwargs: object) -> None:
        raise AssertionError("el correo usa smtplib.SMTP + STARTTLS, nunca SMTP_SSL")

    monkeypatch.setattr(smtplib, "SMTP", fabrica)
    monkeypatch.setattr(smtplib, "SMTP_SSL", sin_ssl)
    return registro


@dataclass
class TelegramFalso:
    """Lo que ve el servidor de Telegram falso: peticiones y argumentos del cliente."""

    manejador: Callable[[httpx.Request], Any]
    peticiones: list[httpx.Request] = field(default_factory=list)
    clientes: list[dict[str, Any]] = field(default_factory=list)


def instalar_telegram(
    monkeypatch: pytest.MonkeyPatch,
    manejador: Callable[[httpx.Request], Any] | None = None,
) -> TelegramFalso:
    """Reemplaza `httpx.AsyncClient` por uno con `MockTransport`; el módulo bajo prueba debe usar
    `httpx.AsyncClient(...)` (como `openbao_provider.py`)."""
    original = httpx.AsyncClient

    def responder(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    falso = TelegramFalso(manejador=manejador or responder)

    def anotado(peticion: httpx.Request) -> httpx.Response:
        falso.peticiones.append(peticion)
        return falso.manejador(peticion)

    class Cliente(original):  # type: ignore[valid-type, misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            falso.clientes.append(dict(kwargs))
            kwargs["transport"] = httpx.MockTransport(anotado)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Cliente)
    return falso


def con_smtp(base: Settings) -> Settings:
    """`base` con el SMTP de prueba; `model_copy` no valida, así que la clave va como `SecretStr`
    (S5-B8: el canal de correo llama `get_secret_value()`)."""
    from pydantic import SecretStr

    cambios = {**SMTP_COMPLETO, "SMTP_PASSWORD": SecretStr(SMTP_COMPLETO["SMTP_PASSWORD"])}
    return base.model_copy(update=cambios)
