"""Anulación de un resultado por un admin (S8-B3b, S8-D46 b, M-1 de la revisión de B3). Base real.

`POST /results/{id}/void` (solo admin, `admin-write`, motivo de 1 a 200): el resultado pasa a
`status = voided`, `is_current = false`, sin sucesor; la base lo permite solo para esa transición.
Leaderboard, ficha y TV lo excluyen; la asistencia y la sesión vuelven a poder quitarse o
cancelarse.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.errors import DomainError
from app.core.pagination import PageParams
from app.core.security import create_access_token
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import SessionCancel
from app.modules.results import service
from app.modules.results.events import WodResultVoided
from app.modules.results.schemas import VoidIn
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

MOTIVO = "Se registró en el socio equivocado"


async def _anular(session: AsyncSession, e: Escena, result_id: UUID, motivo: str = MOTIVO) -> Any:
    with actor_scope(e.coach):
        return await service.void_result(session, result_id, VoidIn(reason=motivo), by=e.coach)


async def _falla(coro: Any) -> DomainError:
    with pytest.raises(DomainError) as info:
        await coro
    return info.value


async def _fila(session: AsyncSession, result_id: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM results.wod_results WHERE id = :i")
    return dict((await session.execute(consulta, {"i": result_id})).mappings().one())


async def test_anular_deja_el_resultado_anulado_sin_sucesor(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    salida = await _anular(session, e, uno.id)
    assert (salida.status, salida.is_current) == ("voided", False)
    assert salida.void_reason == MOTIVO and salida.voided_by == e.coach
    assert salida.voided_at is not None
    fila = await _fila(session, uno.id)
    assert fila["status"] == "voided" and fila["is_current"] is False
    assert fila["seconds"] == 300 and fila["validated_by"] is not None  # la marca no se toca
    sucesores = await session.scalar(
        text("SELECT count(*) FROM results.wod_results WHERE supersedes_id = :i"), {"i": uno.id}
    )
    assert sucesores == 0


async def test_auditoria_update_con_el_motivo(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    await _anular(session, e, uno.id)
    filas = await session.execute(
        text(
            "SELECT action, before->>'status', after->>'status', after->>'void_reason', "
            "subject_member_id::text FROM audit.audit_log "
            "WHERE table_name = 'results.wod_results' AND record_id = :i ORDER BY seq"
        ),
        {"i": uno.id},
    )
    assert [tuple(f) for f in filas.all()] == [
        ("insert", None, "validated", None, str(e.socio_id)),
        ("update", "validated", "voided", MOTIVO, str(e.socio_id)),
    ]


async def test_evento_sin_motivo_ni_log_con_el_motivo(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    vistos: list[Any] = []

    async def recoger(evento: WodResultVoided, _s: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(WodResultVoided, recoger)  # el bus se restaura solo (`restaurar_bus`)
    with caplog.at_level(logging.DEBUG):
        await _anular(session, e, uno.id, "motivo-secreto-123")
    assert len(vistos) == 1
    assert (vistos[0].result_id, vistos[0].member_id) == (uno.id, e.socio_id)
    assert "motivo-secreto-123" not in repr(vistos[0])
    assert "motivo-secreto-123" not in caplog.text


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 201, "con\x00nulo"])
def test_motivo_invalido_422(motivo: str) -> None:
    with pytest.raises(ValueError):
        VoidIn(reason=motivo)


def test_motivo_en_los_limites() -> None:
    assert VoidIn(reason="x").reason == "x"
    assert len(VoidIn(reason="y" * 200).reason) == 200
    assert VoidIn(reason="  con espacios  ").reason == "con espacios"


async def test_404_inexistente(session: AsyncSession) -> None:
    e = await escena(session)
    error = await _falla(_anular(session, e, uuid4()))
    assert (error.status, error.code) == (404, "result_not_found")


async def test_409_ya_anulado(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    await _anular(session, e, uno.id)
    error = await _falla(_anular(session, e, uno.id))
    assert (error.status, error.code) == (409, "result_already_voided")


async def test_409_un_resultado_corregido_no_se_anula(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    await registrar(session, e, seconds=280, supersedes_id=uno.id)
    error = await _falla(_anular(session, e, uno.id))
    assert (error.status, error.code) == (409, "result_not_voidable")
    assert (await _fila(session, uno.id))["status"] == "validated"


async def test_tras_anular_se_puede_registrar_de_nuevo_sin_supersedes(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    await _anular(session, e, uno.id)
    nuevo = await registrar(session, e, seconds=250)
    assert nuevo.is_current and nuevo.supersedes_id is None and nuevo.id != uno.id
    # El anulado no puede ser el `supersedes_id` de nada.
    error = await _falla(registrar(session, e, seconds=240, supersedes_id=uno.id))
    assert error.status == 409 and error.code == "invalid_supersedes"


async def test_leaderboard_ficha_y_resultados_excluyen_al_anulado(session: AsyncSession) -> None:
    e = await escena(session)
    uno = await registrar(session, e, seconds=300)
    await _anular(session, e, uno.id)
    tablero = await service.leaderboard(session, e.wod_id, PageParams())
    assert tablero.total == 0
    ficha = await service.list_member_results(session, e.socio_id, PageParams())
    assert ficha.total == 0
    vigentes = await service.list_wod_results(session, e.wod_id, PageParams())
    assert vigentes.total == 0
    todos = await service.list_wod_results(session, e.wod_id, PageParams(), include_superseded=True)
    assert [(f.status, f.is_current) for f in todos.items] == [("voided", False)]


async def test_tras_anular_la_asistencia_y_la_sesion_se_liberan(session: AsyncSession) -> None:
    e = await escena(session)
    assert e.clase_id is not None
    uno = await registrar(session, e)
    asistencia = await session.scalar(
        text("SELECT id FROM classes.attendance WHERE session_id = :s AND removed_at IS NULL"),
        {"s": e.clase_id},
    )
    with actor_scope(e.coach):
        with pytest.raises(DomainError) as bloqueada:
            await classes_service.remove_attendance(
                session, asistencia, None, by=e.coach, role="admin"
            )
    assert bloqueada.value.code == "locked_by_results"
    await _anular(session, e, uno.id)
    with actor_scope(e.coach):
        await classes_service.remove_attendance(session, asistencia, None, by=e.coach, role="admin")
        await classes_service.cancel_session(
            session, e.clase_id, SessionCancel(reason="Lluvia"), by=e.coach
        )
    estado = await session.scalar(
        text("SELECT status FROM classes.class_sessions WHERE id = :s"), {"s": e.clase_id}
    )
    assert estado == "cancelled"


# Ruta -----------------------------------------------------------------------------------------


async def test_ruta_admin_200_y_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    admin = await usuario_real("admin")
    r = await app_http.post(
        f"/api/v1/results/{uno.id}/void", json={"reason": MOTIVO}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert cuerpo["status"] == "voided" and cuerpo["is_current"] is False
    assert cuerpo["void_reason"] == MOTIVO and cuerpo["voided_by"] == str(admin.id)
    otra_vez = await app_http.post(
        f"/api/v1/results/{uno.id}/void", json={"reason": MOTIVO}, headers=cabeceras(admin)
    )
    assert otra_vez.status_code == 409
    assert otra_vez.json()["error"]["code"] == "result_already_voided"


async def test_ruta_coach_y_member_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    for rol in ("coach", "member"):
        usuario = await usuario_real(rol)
        r = await app_http.post(
            f"/api/v1/results/{uno.id}/void", json={"reason": MOTIVO}, headers=cabeceras(usuario)
        )
        assert r.status_code == 403, (rol, r.text)
    assert (await _fila(session, uno.id))["status"] == "validated"


async def test_ruta_no_permitida_en_quiosco(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    admin = await usuario_real("admin")
    acceso = create_access_token(admin.id, "admin", None, reloj, kiosk=True)
    r = await app_http.post(
        f"/api/v1/results/{uno.id}/void",
        json={"reason": MOTIVO},
        headers={"Authorization": f"Bearer {acceso}", "Origin": ORIGEN},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
    assert (await _fila(session, uno.id))["status"] == "validated"


async def test_ruta_422_con_field_y_404(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno = await registrar(session, e)
    admin = await usuario_real("admin")
    for cuerpo in ({}, {"reason": ""}, {"reason": "x" * 201}, {"reason": "ok", "extra": 1}):
        r = await app_http.post(
            f"/api/v1/results/{uno.id}/void", json=cuerpo, headers=cabeceras(admin)
        )
        assert r.status_code == 422, (cuerpo, r.text)
        assert r.json()["error"]["field"] in {"reason", "extra"}
    r = await app_http.post(
        f"/api/v1/results/{uuid4()}/void", json={"reason": MOTIVO}, headers=cabeceras(admin)
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "result_not_found"
