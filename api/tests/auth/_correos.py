"""Kit de las pruebas de correos de cuenta (S5-B9, US-131). # Rojo B9

- `FabricaDeLaPrueba` / `instalar_fabrica`: un `async_sessionmaker` falso que presta SIEMPRE la
  sesión de la prueba (la de `usuario_real`, dentro de su transacción). `begin()` abre un
  savepoint y `commit()` hace `flush()`. Contrato que fija el Rojo: `forgot_deliver` abre su
  sesión con `async with session_factory() as s, s.begin():` y el router la toma de
  `db.get_sessionmaker()`.
- `entorno_correo`: `Settings` con SMTP falso instalado en `api_prueba.state.settings`, canal de
  correo habilitado y fábrica instalada.
- `post_cronometrado`: llama a la app por ASGI crudo y devuelve cuándo salió
  `http.response.start` (httpx espera a las tareas de fondo; el reloj real de producción no).
- `token_del_cuerpo`: el token que viaja en `/restablecer/<token>`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db
from app.core.config import Settings
from app.core.context import actor_scope
from app.modules.settings.service import update_section
from tests.core._canales_apoyo import SmtpFalso, con_smtp, instalar_smtp
from tests.notifications._apoyo_envio import CANALES_CON_CORREO

FORGOT = "/api/v1/auth/forgot"
NOMBRE_REMITENTE = CANALES_CON_CORREO["email"]["sender_name"]
_TOKEN = re.compile(r"/restablecer/([A-Za-z0-9_\-]+)")


class _SesionPrestada:
    """La sesión de la prueba con `begin()` como savepoint y `commit()` como `flush()`."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    def begin(self) -> Any:
        return self._sesion.begin_nested()

    async def commit(self) -> None:
        await self._sesion.flush()

    def __getattr__(self, nombre: str) -> Any:
        return getattr(self._sesion, nombre)


class _Contexto:
    def __init__(self, fabrica: FabricaDeLaPrueba) -> None:
        self._fabrica = fabrica

    async def __aenter__(self) -> _SesionPrestada:
        self._fabrica.entradas += 1
        if self._fabrica.puerta is not None:
            await self._fabrica.puerta()
        return _SesionPrestada(self._fabrica.sesion)

    async def __aexit__(self, *args: object) -> None:
        if self._fabrica.al_salir is not None:
            self._fabrica.al_salir()


@dataclass
class FabricaDeLaPrueba:
    sesion: AsyncSession
    entradas: int = 0
    puerta: Callable[[], Awaitable[None]] | None = None
    al_salir: Callable[[], None] | None = None

    def __call__(self) -> _Contexto:
        return _Contexto(self)


def instalar_fabrica(sesion: AsyncSession) -> FabricaDeLaPrueba:
    fabrica = FabricaDeLaPrueba(sesion)
    db.configure_sessionmaker(fabrica)  # type: ignore[arg-type]
    return fabrica


async def habilitar_canal_correo(
    sesion: AsyncSession, por: UUID, *, habilitado: bool = True
) -> None:
    """Guarda `channels` con el correo habilitado (o apagado) como el admin."""
    valor = {**CANALES_CON_CORREO, "email": {**CANALES_CON_CORREO["email"], "enabled": habilitado}}
    with actor_scope(por):
        await update_section(sesion, "channels", valor, 0, por)
        await sesion.flush()


@dataclass
class EntornoCorreo:
    smtp: SmtpFalso
    settings: Settings
    fabrica: FabricaDeLaPrueba


def entorno_correo(
    monkeypatch: pytest.MonkeyPatch, api_prueba: FastAPI, sesion: AsyncSession, *, con_smtp_: bool
) -> EntornoCorreo:
    """SMTP falso y fábrica instalados; `con_smtp_=False` deja la `Settings` sin servidor."""
    ajustes = con_smtp(api_prueba.state.settings) if con_smtp_ else api_prueba.state.settings
    api_prueba.state.settings = ajustes
    return EntornoCorreo(instalar_smtp(monkeypatch), ajustes, instalar_fabrica(sesion))


def hacer_que_send_mail_lance(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`send_mail` lanza `RuntimeError` con el cuerpo (y el enlace) en el mensaje: el código
    de `auth` debe capturarlo y registrar solo el tipo (M-7d). Devuelve los cuerpos vistos."""
    vistos: list[str] = []

    async def lanzar(*args: Any, **kwargs: Any) -> None:
        mensaje = args[1] if len(args) > 1 else kwargs["message"]
        vistos.append(mensaje.body)
        raise RuntimeError(f"boom {mensaje.body}")

    monkeypatch.setattr("app.core.mail.send_mail", lanzar)
    for modulo in ("app.modules.auth.links", "app.modules.auth.users"):
        monkeypatch.setattr(f"{modulo}.send_mail", lanzar, raising=False)
    return vistos


def token_del_cuerpo(cuerpo: str) -> str:
    encontrado = _TOKEN.search(cuerpo)
    assert encontrado is not None, "el correo no lleva un enlace /restablecer/<token>"
    return encontrado.group(1)


async def post_cronometrado(
    app: FastAPI, correo: str, ip: str, alerta: Callable[[], object] | None = None
) -> tuple[int, float, object]:
    """POST /auth/forgot por ASGI crudo: (status, segundos hasta `http.response.start`, lo que
    devolvió `alerta()` en ese instante). La app sigue (tareas de fondo) hasta el final."""
    cuerpo = json.dumps({"email": correo}).encode()
    alcance = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": FORGOT,
        "raw_path": FORGOT.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"t"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(cuerpo)).encode()),
        ],
        "client": (ip, 40000),
        "server": ("t", 80),
    }
    entregado = False
    inicio = time.perf_counter()
    resultado: dict[str, Any] = {}

    async def recibir() -> dict[str, Any]:
        nonlocal entregado
        if not entregado:
            entregado = True
            return {"type": "http.request", "body": cuerpo, "more_body": False}
        return {"type": "http.disconnect"}

    async def enviar(mensaje: dict[str, Any]) -> None:
        if mensaje["type"] == "http.response.start" and "t" not in resultado:
            resultado["t"] = time.perf_counter() - inicio
            resultado["status"] = mensaje["status"]
            resultado["instantanea"] = alerta() if alerta is not None else None

    await app(alcance, recibir, enviar)  # type: ignore[arg-type]
    return resultado["status"], resultado["t"], resultado["instantanea"]
