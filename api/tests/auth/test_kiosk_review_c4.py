"""Correcciones de la revisión de C4 en el servidor (S7-C4b; S7-D41, S7-D42). Rojo C4b.

- M-1: la salida del quiosco no sirve para adivinar la contraseña. La sesión de la cookie (y su
  marca) se exige ANTES de argon2; el cupo se reserva ANTES de verificar y un acierto lo devuelve;
  la clave del tope es `usuario|inicio de la familia` (una tablet no bloquea al coach en otra).
- L-2: el logout de una sesión con marca deja `KioskExited` con `via = "logout"`.
- S7-D42: con la marca ya puesta, `POST /auth/kiosk` solo acepta el check-in de sesiones de hoy o
  de ayer en Bogotá (403 `kiosk_mode`); sin marca previa entra a cualquier ruta, como antes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.ratelimit import usage
from app.modules.auth import kiosk, sessions
from tests.auth._sesion import LOGOUT, post_auth
from tests.auth.test_kiosk import MALA, _entrar, _fila, _poner, _salir
from tests.conftest import CLAVE_PRUEBA, CrearUsuario
from tests.factories.classes import make_session

pytestmark = pytest.mark.usefixtures("reloj")


class Espia:
    """Doble de `verify_password_or_dummy`: cuenta llamadas y anota el uso del cupo al llamar."""

    def __init__(self, resultado: bool, clave: str | None = None) -> None:
        self.resultado = resultado
        self.clave = clave
        self.llamadas = 0
        self.uso_al_llamar: list[int] = []

    async def __call__(self, usuario: Any, password: str) -> bool:
        self.llamadas += 1
        if self.clave is not None:
            self.uso_al_llamar.append(
                await usage(kiosk.EXIT_BUCKET, self.clave, window_s=kiosk.EXIT_WINDOW_S)
            )
        return self.resultado


def _clave(user_id: UUID, fila: Any) -> str:
    return f"{user_id}|{fila.family_started_at}"


# M-1 · la salida no es un oráculo ----------------------------------------------------------


async def test_salir_sin_cookie_no_verifica_la_contrasena(
    app_http: AsyncClient, usuario_real: CrearUsuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    token = (await _poner(app_http, access, refresh)).json()["access_token"]
    espia = Espia(True)
    monkeypatch.setattr(sessions, "verify_password_or_dummy", espia)
    r = await post_auth(
        app_http,
        "/api/v1/auth/kiosk/exit",
        json={"password": CLAVE_PRUEBA},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh", r.text
    assert espia.llamadas == 0


async def test_salir_de_una_sesion_sin_marca_no_verifica_la_contrasena(
    app_http: AsyncClient, usuario_real: CrearUsuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)  # sin entrar al quiosco
    espia = Espia(True)
    monkeypatch.setattr(sessions, "verify_password_or_dummy", espia)
    r = await _salir(app_http, access, refresh)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh", r.text
    assert espia.llamadas == 0


async def test_el_cupo_se_reserva_antes_de_verificar_la_contrasena(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    token = (await _poner(app_http, access, refresh)).json()["access_token"]
    clave = _clave(coach.id, await _fila(session, refresh))
    espia = Espia(False, clave)
    monkeypatch.setattr(sessions, "verify_password_or_dummy", espia)
    for _ in range(3):
        assert (await _salir(app_http, token, refresh, MALA)).status_code == 401
    assert espia.uso_al_llamar == [1, 2, 3]  # el intento ya cuenta cuando argon2 corre
    assert await usage(kiosk.EXIT_BUCKET, clave, window_s=kiosk.EXIT_WINDOW_S) == 3


async def test_un_acierto_devuelve_su_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    token = (await _poner(app_http, access, refresh)).json()["access_token"]
    clave = _clave(coach.id, await _fila(session, refresh))
    for _ in range(3):
        assert (await _salir(app_http, token, refresh, MALA)).status_code == 401
    assert (await _salir(app_http, token, refresh)).status_code == 200
    assert await usage(kiosk.EXIT_BUCKET, clave, window_s=kiosk.EXIT_WINDOW_S) == 3


async def test_el_tope_es_por_usuario_y_sesion_no_solo_por_usuario(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    access_a, refresh_a = await _entrar(app_http, coach)
    token_a = (await _poner(app_http, access_a, refresh_a)).json()["access_token"]
    reloj.advance(minutes=1)  # el reloj de las pruebas está congelado: otra familia, otro inicio
    access_b, refresh_b = await _entrar(app_http, coach)  # otra tablet, otra familia
    token_b = (await _poner(app_http, access_b, refresh_b)).json()["access_token"]
    for _ in range(5):
        assert (await _salir(app_http, token_a, refresh_a, MALA)).status_code == 401
    assert (await _salir(app_http, token_a, refresh_a)).status_code == 429
    assert (await _salir(app_http, token_b, refresh_b)).status_code == 200


# L-2 · el logout de un quiosco queda auditado ------------------------------------------------


async def _eventos_de_quiosco(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT after FROM audit.audit_log WHERE record_id = :id AND action = 'update' "
            "AND after->>'event' LIKE 'Kiosk%' ORDER BY seq"
        ),
        {"id": user_id},
    )
    return [dict(f[0]) for f in filas.all()]


async def test_el_logout_con_marca_deja_kiosk_exited_via_logout(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    await _poner(app_http, access, refresh)
    assert (await post_auth(app_http, LOGOUT, cookie=refresh)).status_code == 204
    eventos = await _eventos_de_quiosco(session, coach.id)
    assert [e["event"] for e in eventos] == ["KioskEntered", "KioskExited"]
    assert eventos[-1]["via"] == "logout"


async def test_el_logout_sin_marca_no_deja_kiosk_exited(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    _, refresh = await _entrar(app_http, coach)
    assert (await post_auth(app_http, LOGOUT, cookie=refresh)).status_code == 204
    assert await _eventos_de_quiosco(session, coach.id) == []


async def test_la_salida_con_contrasena_deja_via_password(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    token = (await _poner(app_http, access, refresh)).json()["access_token"]
    assert (await _salir(app_http, token, refresh)).status_code == 200
    eventos = await _eventos_de_quiosco(session, coach.id)
    assert eventos[-1] == {"event": "KioskExited", "via": "password"}


# S7-D42 · cambiar de clase dentro del quiosco ---------------------------------------------


def _ruta(session_id: UUID) -> str:
    return f"/clases/{session_id}/checkin"


async def _clase(session: AsyncSession, dia: int) -> UUID:
    """Sesión del día `dia` de octubre de 2026 a las 06:00 de Bogotá (hoy es el 21)."""
    fila = await make_session(session, starts_at=datetime(2026, 10, dia, 11, 0, tzinfo=UTC))
    return fila.id


@pytest.mark.parametrize(("dia", "permitida"), [(21, True), (20, True), (19, False), (22, False)])
async def test_con_la_marca_solo_entra_a_sesiones_de_hoy_o_de_ayer(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
    dia: int,
    permitida: bool,
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    primera = await _poner(app_http, access, refresh, _ruta(await _clase(session, 21)))
    assert primera.status_code == 200, primera.text
    r = await _poner(
        app_http, primera.json()["access_token"], refresh, _ruta(await _clase(session, dia))
    )
    if permitida:
        assert r.status_code == 200 and r.json()["kiosk_path"].startswith("/clases/"), r.text
    else:
        assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
        assert (await _fila(session, refresh)).kiosk_path == _ruta_de(primera)


def _ruta_de(respuesta: Any) -> str:
    return str(respuesta.json()["kiosk_path"])


async def test_con_la_marca_una_sesion_inexistente_es_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    primera = await _poner(app_http, access, refresh, _ruta(await _clase(session, 21)))
    r = await _poner(app_http, primera.json()["access_token"], refresh, _ruta(uuid4()))
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text


async def test_sin_marca_previa_entra_a_cualquier_ruta_como_antes(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    r = await _poner(app_http, access, refresh, _ruta(await _clase(session, 18)))
    assert r.status_code == 200, r.text


# S7-C4c · M-1: `auth` no lee tablas de `classes`; L-3: solo sesiones programadas ---------------


async def test_sin_el_puerto_de_sesiones_el_cambio_de_clase_falla_explicito(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-1: sin el puerto que registra `classes` no se adivina nada: error explícito, y la marca
    no cambia."""
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    primera = await _poner(app_http, access, refresh, _ruta(await _clase(session, 21)))
    destino = _ruta(await _clase(session, 21))
    monkeypatch.setattr(kiosk, "_session_info", None)
    with pytest.raises(kiosk.KioskSessionInfoNotRegistered):
        await _poner(app_http, primera.json()["access_token"], refresh, destino)


async def test_el_puerto_lo_registra_classes_al_importarse() -> None:
    from app.modules.auth import service as auth_service
    from app.modules.classes import service as classes_service

    assert kiosk.kiosk_session_info_port() is classes_service.kiosk_session_info
    assert auth_service.set_kiosk_session_info is kiosk.set_kiosk_session_info


async def test_con_la_marca_una_sesion_cancelada_de_hoy_es_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    """L-3: la clase destino debe estar programada; una cancelada de hoy no vale."""
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    primera = await _poner(app_http, access, refresh, _ruta(await _clase(session, 21)))
    cancelada = await make_session(
        session,
        starts_at=datetime(2026, 10, 21, 17, 0, tzinfo=UTC),
        status="cancelled",
        cancel_reason="lluvia",
        cancelled_by=coach.id,
        cancelled_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
    )
    r = await _poner(app_http, primera.json()["access_token"], refresh, _ruta(cancelada.id))
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
