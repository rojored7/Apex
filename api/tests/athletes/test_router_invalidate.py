"""`POST /athletes/{member_id}/records/{record_id}/invalidate` por HTTP (S9-B5; S9-D13, S9-D33).

Contrato del blueprint §3, ruta 10 (sin cuerpo; sin texto libre):
- Admin: invalida cualquier récord manual vivo, también el de otro y el viejo (200 `RecordOut` con
  `invalidated_reason = manual_error`, `Cache-Control: no-store`).
- Coach (M-3): solo el que registró él (`created_by`) y hasta 24 h después de crearlo (con
  `FrozenClock`; la hora 24 exacta aún cuenta); el de otro o el suyo pasadas 24 h: 403 `forbidden`
  sin tocar la fila ni la auditoría. El 403 manda sobre el 409.
- `member` 403, sin token 401, quiosco 403 `kiosk_mode`.
- 404 `member_not_found` (inexistente o dado de baja), 404 `record_not_found` (de otro socio o
  inexistente), 409 `record_is_derived`, 409 `record_already_invalidated`; ids que no son UUID, 422.
- La cubeta `athletes-write` (30 por minuto): la 31 da 429.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from tests.athletes._apoyo import ATHLETES, auditoria_de_records
from tests.athletes._apoyo_derivar import records_de
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_record
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

TOPE_ESCRITURAS = 30
CAMPOS = {
    "id",
    "kind",
    "movement_id",
    "movement_name",
    "benchmark_id",
    "benchmark_name",
    "score_type",
    "value_g",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
    "achieved_on",
    "source",
    "result_id",
    "result_source",
    "wod_id",
    "is_current",
    "invalidated_at",
    "invalidated_reason",
    "recorded_by",
    "recorded_by_name",
    "created_at",
}


def _ruta(member_id: UUID | str, record_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/records/{record_id}/invalidate"


def _cab(usuario: UsuarioPrueba, rol: str, reloj: FrozenClock) -> dict[str, str]:
    """Token emitido AHORA (con el reloj ya movido): el de `cabeceras` vence a los 15 minutos."""
    acceso = create_access_token(usuario.id, rol, None, reloj)
    return {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}


async def _manual(session: AsyncSession, autor: UsuarioPrueba, **cambios: Any) -> tuple[UUID, UUID]:
    """(member_id, record_id) de un RM manual vivo registrado por `autor`."""
    miembro = await socio(session)
    record = await make_record(session, miembro.id, kind="rm", actor=autor.id, **cambios)
    return miembro.id, record.id


async def _creado(session: AsyncSession, record_id: UUID) -> Any:
    return (
        await session.execute(
            text("SELECT created_at FROM athletes.personal_records WHERE id = :i"), {"i": record_id}
        )
    ).scalar_one()


async def _estado(session: AsyncSession, record_id: UUID) -> tuple[Any, int]:
    """(`invalidated_reason`, filas de auditoría) del récord."""
    razon = await session.scalar(
        text("SELECT invalidated_reason FROM athletes.personal_records WHERE id = :i"),
        {"i": record_id},
    )
    return razon, len(await auditoria_de_records(session, record_id))


# Admin ----------------------------------------------------------------------------------------


async def test_el_admin_invalida_y_recibe_el_record_invalidado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    member_id, record_id = await _manual(session, admin, value_g=100_000)

    r = await app_http.post(_ruta(member_id, record_id), headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS
    assert cuerpo["id"] == str(record_id)
    assert cuerpo["invalidated_reason"] == "manual_error"
    assert cuerpo["invalidated_at"] is not None
    assert cuerpo["is_current"] is False
    assert cuerpo["value_g"] == 100_000
    filas = await records_de(session, member_id)
    assert filas[0]["invalidated_by"] == admin.id


async def test_el_admin_invalida_el_de_otro_y_el_viejo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    member_id, record_id = await _manual(session, coach)
    reloj.set(await _creado(session, record_id) + timedelta(days=30))

    r = await app_http.post(_ruta(member_id, record_id), headers=_cab(admin, "admin", reloj))

    assert r.status_code == 200, r.text
    assert (await _estado(session, record_id))[0] == "manual_error"


# Coach (M-3) ----------------------------------------------------------------------------------


async def test_el_coach_invalida_el_suyo_dentro_de_24_horas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    member_id, record_id = await _manual(session, coach)
    reloj.set(await _creado(session, record_id) + timedelta(hours=23, minutes=59))

    r = await app_http.post(_ruta(member_id, record_id), headers=_cab(coach, "coach", reloj))

    assert r.status_code == 200, r.text
    assert r.json()["invalidated_reason"] == "manual_error"


async def test_la_hora_24_exacta_aun_cuenta_y_un_segundo_despues_es_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    m_justo, justo = await _manual(session, coach)
    m_tarde, tarde = await _manual(session, coach)
    reloj.set(await _creado(session, justo) + timedelta(hours=24))
    r_justo = await app_http.post(_ruta(m_justo, justo), headers=_cab(coach, "coach", reloj))
    reloj.set(await _creado(session, tarde) + timedelta(hours=24, seconds=1))
    r_tarde = await app_http.post(_ruta(m_tarde, tarde), headers=_cab(coach, "coach", reloj))

    assert r_justo.status_code == 200, r_justo.text
    assert r_tarde.status_code == 403, r_tarde.text
    assert r_tarde.json()["error"]["code"] == "forbidden"
    assert (await _estado(session, tarde))[0] is None


async def test_un_coach_no_invalida_el_de_otro_y_no_deja_rastro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    dueno = await usuario_real("coach")
    otro = await usuario_real("coach")
    member_id, record_id = await _manual(session, dueno)
    antes = await _estado(session, record_id)

    r = await app_http.post(_ruta(member_id, record_id), headers=_cab(otro, "coach", reloj))

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await _estado(session, record_id) == antes, "ni la fila ni la auditoría cambian"


async def test_sobre_uno_ya_invalidado_el_permiso_manda_sobre_el_409(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    dueno = await usuario_real("coach")
    ajeno = await usuario_real("coach")
    member_id, record_id = await _manual(session, dueno)
    await app_http.post(_ruta(member_id, record_id), headers=cabeceras(admin))

    r_ajeno = await app_http.post(_ruta(member_id, record_id), headers=_cab(ajeno, "coach", reloj))
    r_dueno = await app_http.post(_ruta(member_id, record_id), headers=_cab(dueno, "coach", reloj))

    assert r_ajeno.status_code == 403, r_ajeno.text
    assert r_dueno.status_code == 409, r_dueno.text
    assert r_dueno.json()["error"]["code"] == "record_already_invalidated"


# Acceso ---------------------------------------------------------------------------------------


async def test_member_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    persona = await usuario_real("member")
    member_id, record_id = await _manual(session, admin)

    r_member = await app_http.post(_ruta(member_id, record_id), headers=cabeceras(persona))
    r_anonimo = await app_http.post(_ruta(member_id, record_id), headers={"Origin": ORIGEN})

    assert r_member.status_code == 403 and r_member.json()["error"]["code"] == "forbidden"
    assert r_anonimo.status_code == 401
    assert (await _estado(session, record_id))[0] is None


async def test_en_modo_quiosco_403_kiosk_mode_sin_tocar_el_record(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    member_id, record_id = await _manual(session, coach)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)

    r = await app_http.post(
        _ruta(member_id, record_id), headers={"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}
    )

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "kiosk_mode"
    assert (await _estado(session, record_id))[0] is None


# Errores --------------------------------------------------------------------------------------


async def test_socio_inexistente_o_dado_de_baja_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    member_id, record_id = await _manual(session, admin)
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"), {"i": member_id}
    )

    de_baja = await app_http.post(_ruta(member_id, record_id), headers=h)
    inexistente = await app_http.post(_ruta(uuid4(), record_id), headers=h)

    for r in (de_baja, inexistente):
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "member_not_found"
        assert r.headers["cache-control"] == "no-store"
    assert (await _estado(session, record_id))[0] is None


async def test_record_de_otro_socio_o_inexistente_404_record_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    _, record_id = await _manual(session, admin)
    otro_socio = await socio(session)
    otro_id = otro_socio.id  # el rollback del 404 expira los objetos de la sesión

    de_otro = await app_http.post(_ruta(otro_id, record_id), headers=h)
    inexistente = await app_http.post(_ruta(otro_id, uuid4()), headers=h)

    for r in (de_otro, inexistente):
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "record_not_found"
    assert (await _estado(session, record_id))[0] is None


async def test_un_derivado_da_409_record_is_derived(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    miembro = await socio(session)
    derivado = await make_record(session, miembro.id, kind="rm", source="derived", actor=admin.id)
    miembro_id, derivado_id = miembro.id, derivado.id  # el rollback del 409 expira los objetos

    r = await app_http.post(_ruta(miembro_id, derivado_id), headers=cabeceras(admin))

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "record_is_derived"
    assert (await _estado(session, derivado_id))[0] is None


async def test_repetir_da_409_record_already_invalidated(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    member_id, record_id = await _manual(session, admin)
    primera = await app_http.post(_ruta(member_id, record_id), headers=h)
    antes = await _estado(session, record_id)

    segunda = await app_http.post(_ruta(member_id, record_id), headers=h)

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["error"]["code"] == "record_already_invalidated"
    assert await _estado(session, record_id) == antes


@pytest.mark.parametrize("que", ["socio", "record"])
async def test_ids_que_no_son_uuid_dan_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    que: str,
) -> None:
    admin = await usuario_real("admin")
    member_id, record_id = await _manual(session, admin)
    ruta = _ruta("no-es-uuid", record_id) if que == "socio" else _ruta(member_id, "no-es-uuid")

    r = await app_http.post(ruta, headers=cabeceras(admin))

    assert r.status_code == 422, r.text
    assert (await _estado(session, record_id))[0] is None


async def test_no_acepta_cuerpo_con_texto_libre(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """La ruta no tiene cuerpo: un motivo escrito sobre el cuerpo de un socio sería dato de
    salud (S9-D13). Un cuerpo enviado se ignora y no llega a la auditoría."""
    admin = await usuario_real("admin")
    member_id, record_id = await _manual(session, admin)

    r = await app_http.post(
        _ruta(member_id, record_id),
        json={"reason": "Pesaba 70 kg y tenía una lesión"},
        headers=cabeceras(admin),
    )

    assert r.status_code == 200, r.text
    filas = await auditoria_de_records(session, record_id)
    assert "lesión" not in str(filas) and "Pesaba" not in str(filas)


async def test_la_cubeta_athletes_write_da_429_en_la_invalidacion_31(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    miembro = await socio(session)
    ruta = _ruta(miembro.id, UUID(int=0xBAD))
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(ruta, headers=h)
        assert r.status_code == 404, (i, r.text)

    r = await app_http.post(ruta, headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers
