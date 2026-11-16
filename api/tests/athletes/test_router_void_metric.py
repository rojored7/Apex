"""`POST /athletes/{member_id}/metrics/{metric_id}/void` por HTTP (S9-A3, US-178; S9-D13, S9-D33;
M-3, L-3). Contrato del blueprint §3, ruta 11.

- Admin: anula cualquiera (200 `MetricOut` con `voided_at`, `Cache-Control: no-store`).
- Coach (M-3): anula SOLO las suyas (`recorded_by` = él) y hasta 24 h después de crearlas (con
  `FrozenClock`; la hora 24 exacta aún cuenta); la de otro o la suya pasadas 24 h: 403 `forbidden`
  sin tocar la fila ni la auditoría. El admin anula la ajena y la vieja.
- `member` 403, sin token 401, quiosco 403 `kiosk_mode`; socio dado de baja 404 `member_not_found`.
- 404 `metric_not_found` (de otro socio o inexistente); 409 `metric_already_voided`; ids que no son
  UUID, 422.
- La cubeta `athletes-write` (30 por minuto): la 31 da 429.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from tests.athletes._apoyo import (
    actualizaciones_de,
    alta,
    fila_cruda,
    ruta_anular,
)
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_metric
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "id",
    "measured_on",
    "has_weight",
    "has_height",
    "has_body_fat",
    "has_notes",
    "recorded_by",
    "recorded_by_name",
    "voided_at",
    "created_at",
}
TOPE_ESCRITURAS = 30


async def _escena(
    session: AsyncSession, autor: UsuarioPrueba, **cambios: Any
) -> tuple[UUID, UUID, str]:
    """Socio con una medición registrada por `autor`: (member_id, metric_id, ruta de anular)."""
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, autor.id, miembro.id, **cambios)
    return miembro.id, medicion.id, ruta_anular(miembro.id, medicion.id)


def _cab(usuario: UsuarioPrueba, rol: str, reloj: FrozenClock) -> dict[str, str]:
    """Cabeceras con un token emitido AHORA (con el reloj ya movido): el de `cabeceras` nace al
    crear el usuario y vence a los 15 minutos del reloj congelado."""
    acceso = create_access_token(usuario.id, rol, None, reloj)
    return {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}


async def _creada(session: AsyncSession, metric_id: UUID) -> datetime:
    return (await fila_cruda(session, metric_id))["created_at"]


# Admin ---------------------------------------------------------------------------------------


async def test_el_admin_anula_y_recibe_la_medicion_anulada_sin_valores(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    _, metric_id, ruta = await _escena(session, admin)

    r = await app_http.post(ruta, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS
    assert cuerpo["id"] == str(metric_id)
    assert datetime.fromisoformat(cuerpo["voided_at"]) == reloj.now_utc()
    assert cuerpo["has_weight"] is True
    assert r.headers["cache-control"] == "no-store"
    assert "62500" not in r.text
    (fila,) = await actualizaciones_de(session, metric_id)
    assert fila["user_id"] == admin.id


async def test_el_admin_anula_la_de_otro_y_la_de_hace_mas_de_24_horas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    admin = await usuario_real("admin")
    _, metric_id, ruta = await _escena(session, coach)
    reloj.set(await _creada(session, metric_id) + timedelta(days=30))

    r = await app_http.post(ruta, headers=_cab(admin, "admin", reloj))

    assert r.status_code == 200, r.text
    assert (await fila_cruda(session, metric_id))["voided_by"] == admin.id


# M-3: el coach -------------------------------------------------------------------------------


async def test_el_coach_anula_la_suya_dentro_de_las_24_horas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    _, metric_id, ruta = await _escena(session, coach)
    reloj.set(await _creada(session, metric_id) + timedelta(hours=23, minutes=59))

    r = await app_http.post(ruta, headers=_cab(coach, "coach", reloj))

    assert r.status_code == 200, r.text
    assert (await fila_cruda(session, metric_id))["voided_by"] == coach.id


async def test_en_la_hora_24_exacta_el_coach_aun_puede_y_un_segundo_despues_no(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    _, justo, ruta_justo = await _escena(session, coach)
    _, tarde, ruta_tarde = await _escena(session, coach)
    reloj.set(await _creada(session, justo) + timedelta(hours=24))
    r_justo = await app_http.post(ruta_justo, headers=_cab(coach, "coach", reloj))
    reloj.set(await _creada(session, tarde) + timedelta(hours=24, seconds=1))
    r_tarde = await app_http.post(ruta_tarde, headers=_cab(coach, "coach", reloj))

    assert r_justo.status_code == 200, r_justo.text
    assert r_tarde.status_code == 403, r_tarde.text
    assert (await fila_cruda(session, tarde))["voided_at"] is None


async def test_el_coach_no_anula_la_de_otro_ni_la_suya_pasadas_24_horas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    _, ajena, ruta_ajena = await _escena(session, otro)
    _, vieja, ruta_vieja = await _escena(session, coach)
    reloj.set(await _creada(session, vieja) + timedelta(hours=25))
    h = _cab(coach, "coach", reloj)

    de_otro = await app_http.post(ruta_ajena, headers=h)
    pasada = await app_http.post(ruta_vieja, headers=h)

    for r in (de_otro, pasada):
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "forbidden"
        assert r.headers["cache-control"] == "no-store"
    for metric_id in (ajena, vieja):
        assert (await fila_cruda(session, metric_id))["voided_at"] is None
        assert await actualizaciones_de(session, metric_id) == []


# Roles ---------------------------------------------------------------------------------------


async def test_socio_403_y_sin_token_401_sin_anular(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    _, metric_id, ruta = await _escena(session, coach)
    rol_socio = await usuario_real("member")

    r = await app_http.post(ruta, headers=cabeceras(rol_socio))
    sin = await app_http.post(ruta)

    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert sin.status_code == 401 and sin.json()["error"]["code"] == "unauthorized"
    assert (await fila_cruda(session, metric_id))["voided_at"] is None


async def test_en_modo_quiosco_403_kiosk_mode_sin_anular(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    _, metric_id, ruta = await _escena(session, coach)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    r = await app_http.post(ruta, headers=cab)

    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode"
    assert (await fila_cruda(session, metric_id))["voided_at"] is None


# Existencia y estado -------------------------------------------------------------------------


async def test_socio_dado_de_baja_da_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    medicion = await make_metric(session, baja.id)
    metric_id = medicion.id

    r = await app_http.post(ruta_anular(baja.id, metric_id), headers=cabeceras(admin))

    assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"
    assert (await fila_cruda(session, metric_id))["voided_at"] is None


async def test_medicion_de_otro_socio_o_inexistente_da_404_metric_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    _, metric_id, _ = await _escena(session, admin)
    ajeno = await socio(session, consentido=True)
    ajeno_id = ajeno.id
    h = cabeceras(admin)

    de_otro = await app_http.post(ruta_anular(ajeno_id, metric_id), headers=h)
    inexistente = await app_http.post(ruta_anular(ajeno_id, UUID(int=0xBAD)), headers=h)

    for r in (de_otro, inexistente):
        assert r.status_code == 404 and r.json()["error"]["code"] == "metric_not_found"
    assert (await fila_cruda(session, metric_id))["voided_at"] is None


async def test_socio_inexistente_da_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    _, metric_id, _ = await _escena(session, admin)

    r = await app_http.post(ruta_anular(UUID(int=0x999), metric_id), headers=cabeceras(admin))

    assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"


async def test_repetir_da_409_metric_already_voided_y_el_reveal_409_metric_voided(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    member_id, metric_id, ruta = await _escena(session, admin)
    h = cabeceras(admin)
    assert (await app_http.post(ruta, headers=h)).status_code == 200

    otra_vez = await app_http.post(ruta, headers=h)
    reveal = await app_http.post(
        f"{ruta.removesuffix('/void')}/reveal", json={"field": "weight_g"}, headers=h
    )

    assert otra_vez.status_code == 409
    assert otra_vez.json()["error"]["code"] == "metric_already_voided"
    assert reveal.status_code == 409 and reveal.json()["error"]["code"] == "metric_voided"
    assert len(await actualizaciones_de(session, metric_id)) == 1
    assert member_id


async def test_ids_que_no_son_uuid_dan_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")

    r = await app_http.post(
        "/api/v1/athletes/no-es-uuid/metrics/tampoco/void", headers=cabeceras(admin)
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


# Cubeta --------------------------------------------------------------------------------------


async def test_la_cubeta_athletes_write_da_429_en_la_anulacion_31(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    miembro = await socio(session, consentido=True)
    # Treinta intentos sobre una medición inexistente (404) consumen cupo; el 31 da 429.
    ruta = ruta_anular(miembro.id, UUID(int=0xBAD))
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(ruta, headers=h)
        assert r.status_code == 404, (i, r.text)

    r = await app_http.post(ruta, headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers


async def test_sobre_una_ya_anulada_el_permiso_manda_sobre_el_409(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    """Seg L-2: quien no puede anular recibe 403 aunque la medición ya esté anulada (no se le
    revela el estado); el autor dentro de su ventana sí ve el 409."""
    autor = await usuario_real("coach")
    ajeno = await usuario_real("coach")
    admin = await usuario_real("admin")
    _, metric_id, ruta = await _escena(session, autor)
    assert (await app_http.post(ruta, headers=cabeceras(admin))).status_code == 200

    de_otro = await app_http.post(ruta, headers=cabeceras(ajeno))
    propia_dentro = await app_http.post(ruta, headers=cabeceras(autor))
    reloj.set(await _creada(session, metric_id) + timedelta(hours=25))
    propia_tarde = await app_http.post(ruta, headers=_cab(autor, "coach", reloj))

    assert (de_otro.status_code, de_otro.json()["error"]["code"]) == (403, "forbidden")
    assert (propia_dentro.status_code, propia_dentro.json()["error"]["code"]) == (
        409,
        "metric_already_voided",
    )
    assert (propia_tarde.status_code, propia_tarde.json()["error"]["code"]) == (403, "forbidden")
