"""`POST /auth/kiosk` con la ruta de resultados (S8-B3; S8-D15, S7-D42). Base real."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth.test_kiosk import _entrar, _fila, _poner
from tests.conftest import CrearUsuario
from tests.factories.classes import make_session

pytestmark = pytest.mark.usefixtures("reloj")


def _checkin(session_id: UUID) -> str:
    return f"/clases/{session_id}/checkin"


def _resultados(session_id: UUID) -> str:
    return f"/clases/{session_id}/resultados"


async def _clase(session: AsyncSession, dia: int) -> UUID:
    """Sesión del día `dia` de octubre de 2026 a las 06:00 de Bogotá (hoy es el 21)."""
    fila = await make_session(session, starts_at=datetime(2026, 10, dia, 11, 0, tzinfo=UTC))
    return fila.id


async def test_entrar_a_resultados(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    ruta = _resultados(await _clase(session, 21))
    r = await _poner(app_http, access, refresh, ruta)
    assert r.status_code == 200, r.text
    assert r.json()["kiosk_path"] == ruta
    assert (await _fila(session, refresh)).kiosk_path == ruta


async def test_pasar_de_checkin_a_resultados_sin_contrasena(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    clase = await _clase(session, 21)
    primera = await _poner(app_http, access, refresh, _checkin(clase))
    assert primera.status_code == 200, primera.text
    r = await _poner(app_http, primera.json()["access_token"], refresh, _resultados(clase))
    assert r.status_code == 200, r.text
    assert r.json()["kiosk_path"] == _resultados(clase)
    assert (await _fila(session, refresh)).kiosk_path == _resultados(clase)


async def test_sesion_de_anteayer_403_kiosk_mode(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    primera = await _poner(app_http, access, refresh, _checkin(await _clase(session, 21)))
    vieja = await _clase(session, 19)
    r = await _poner(app_http, primera.json()["access_token"], refresh, _resultados(vieja))
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text


@pytest.mark.parametrize("sufijo", ["otro", "resultado", "checkin/x", "resultados/", "Resultados"])
async def test_ruta_con_otro_sufijo_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, sufijo: str
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    r = await _poner(app_http, access, refresh, f"/clases/{uuid4()}/{sufijo}")
    assert r.status_code == 422, r.text
