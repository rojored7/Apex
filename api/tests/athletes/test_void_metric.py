"""`athletes.service.void_metric` con PostgreSQL real (S9-A3, US-178; S9-D13, S9-D33; M-3, L-3).

- Anular llena `voided_at` y `voided_by` (terminal) y no toca los blobs: la medición sale de la
  lista y del conteo, y `include_voided=true` la devuelve.
- Anular otra vez: 409 `metric_already_voided`; `reveal` de la anulada: 409 `metric_voided`.
- Auditoría: una fila `update` con el sujeto y sin ningún valor en claro.
- El trigger de la base rechaza desanular (`voided_at = NULL`).
- Socio dado de baja o inexistente: `member_not_found`; medición de otro socio: `metric_not_found`.
- Orden único de candados: socio, fila de la medición `FOR UPDATE`, UPDATE y recién después la
  cadena de auditoría (el mismo orden que `reveal_metric`).
- L-3 (dos conexiones) vive en `test_void_concurrency.py`: necesita llaves con commit real.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.modules.athletes import metrics, service
from app.modules.athletes.exceptions import MetricAlreadyVoided, MetricNotFound, MetricVoided
from app.modules.members.exceptions import MemberNotFound
from tests.athletes._apoyo import (
    TABLA,
    actualizaciones_de,
    alta,
    anular,
    auditoria_de,
    claros_en,
    fila_cruda,
    revelar,
)
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_metric
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

PAGINA = PageParams(limit=50, offset=0)


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


# Efecto de anular ----------------------------------------------------------------------------


async def test_anular_llena_voided_at_y_voided_by_y_devuelve_la_medicion_anulada(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    antes = await fila_cruda(session, metric_id)

    salida = await anular(session, admin.id, member_id, metric_id)

    assert salida.id == metric_id
    assert salida.voided_at is not None
    assert salida.voided_at >= antes["created_at"]  # reloj de la base (L1)
    assert (salida.has_weight, salida.has_height, salida.has_body_fat, salida.has_notes) == (
        True,
        True,
        True,
        True,
    )
    despues = await fila_cruda(session, metric_id)
    assert despues["voided_at"] == salida.voided_at
    assert despues["voided_by"] == admin.id
    # No se borra ni se recifra: los cuatro blobs quedan idénticos.
    for campo in ("weight_g", "height_cm", "body_fat_pct", "notes"):
        assert despues[campo] == antes[campo], campo


async def test_sale_de_la_lista_y_del_conteo_y_include_voided_la_devuelve(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    member_id = miembro.id
    viva = await alta(session, admin.id, member_id, weight_g=70_000)
    anulada = await alta(session, admin.id, member_id, weight_g=71_000)
    viva_id, anulada_id = viva.id, anulada.id

    await anular(session, admin.id, member_id, anulada_id)

    session.expunge_all()
    lista = await service.list_metrics(session, member_id, PAGINA)
    assert (lista.total, [m.id for m in lista.items]) == (1, [viva_id])
    todas = await service.list_metrics(session, member_id, PAGINA, include_voided=True)
    assert todas.total == 2
    assert {m.id: m.voided_at is not None for m in todas.items} == {
        viva_id: False,
        anulada_id: True,
    }


async def test_anular_otra_vez_da_409_metric_already_voided_y_no_cambia_la_fila(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    await anular(session, admin.id, member_id, metric_id)
    primera = (await fila_cruda(session, metric_id))["voided_at"]
    reloj.advance(hours=1)

    with pytest.raises(MetricAlreadyVoided) as e:
        await anular(session, admin.id, member_id, metric_id)

    assert (e.value.status, e.value.code) == (409, "metric_already_voided")
    assert (await fila_cruda(session, metric_id))["voided_at"] == primera
    assert len(await actualizaciones_de(session, metric_id)) == 1


async def test_reveal_de_una_anulada_da_409_metric_voided(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    await anular(session, admin.id, member_id, metric_id)

    with pytest.raises(MetricVoided):
        await revelar(session, admin.id, member_id, metric_id, "weight_g")


# Auditoría y trigger -------------------------------------------------------------------------


async def test_la_auditoria_deja_una_fila_update_con_el_sujeto_y_sin_valores(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id

    await anular(session, admin.id, member_id, metric_id)

    acciones = [f["action"] for f in await auditoria_de(session, metric_id)]
    assert acciones == ["insert", "update"]
    (fila,) = await actualizaciones_de(session, metric_id)
    assert (fila["user_id"], fila["table_name"], fila["subject_member_id"]) == (
        admin.id,
        TABLA,
        member_id,
    )
    assert fila["after"]["voided_by"] == str(admin.id)
    assert fila["after"]["voided_at"] is not None
    for lado in ("before", "after"):
        assert claros_en(fila[lado] or {}, ("62500", "062500", "w062500", "Primera")) == [], lado


async def test_el_trigger_rechaza_desanular(session: AsyncSession, admin: UsuarioPrueba) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    await anular(session, admin.id, member_id, metric_id)

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "UPDATE athletes.body_metrics SET voided_at = NULL, voided_by = NULL "
                    "WHERE id = :i"
                ),
                {"i": metric_id},
            )

    assert (await fila_cruda(session, metric_id))["voided_at"] is not None


# Existencia ----------------------------------------------------------------------------------


async def test_de_un_socio_dado_de_baja_da_member_not_found_y_no_anula(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    medicion = await make_metric(session, baja.id)
    member_id, metric_id = baja.id, medicion.id

    with pytest.raises(MemberNotFound):
        await anular(session, admin.id, member_id, metric_id)

    assert (await fila_cruda(session, metric_id))["voided_at"] is None


async def test_de_otro_socio_o_inexistente_da_metric_not_found(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    metric_id = medicion.id
    ajeno = await socio(session, consentido=True)
    ajeno_id = ajeno.id

    with pytest.raises(MetricNotFound):
        await anular(session, admin.id, ajeno_id, metric_id)
    with pytest.raises(MetricNotFound):
        await anular(session, admin.id, ajeno_id, UUID(int=0xBAD))

    assert (await fila_cruda(session, metric_id))["voided_at"] is None


async def test_ninguna_anulacion_descifra(session: AsyncSession, admin: UsuarioPrueba) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id

    await anular(session, admin.id, member_id, metric_id)

    n = await session.scalar(
        text("SELECT count(*) FROM crypto.crypto_ops WHERE record_id = :r AND verb = 'decrypt'"),
        {"r": metric_id},
    )
    assert n == 0


# Orden de candados ---------------------------------------------------------------------------


async def test_orden_de_candados_socio_fila_update_y_al_final_la_cadena(
    session: AsyncSession,
    engine: AsyncEngine,
    admin: UsuarioPrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S9-D49: igual que `reveal_metric`, el socio y la fila de la medición se bloquean ANTES de
    que la auditoría tome el candado de su cadena (la que escribe el `INSERT` en `audit_log`)."""
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    orden: list[str] = []
    real_lock = metrics.lock_member

    async def lock(sesion: AsyncSession, mid: Any) -> None:
        orden.append("socio")
        await real_lock(sesion, mid)

    def espiar(conn: Any, cursor: Any, statement: str, *resto: Any) -> None:
        s = " ".join(statement.split())
        if s.startswith("SELECT") and "FROM athletes.body_metrics" in s and "FOR UPDATE" in s:
            orden.append("fila")
        elif s.startswith("UPDATE athletes.body_metrics"):
            orden.append("update")
        elif s.startswith("INSERT INTO audit.audit_log"):
            orden.append("auditoria")

    monkeypatch.setattr(metrics, "lock_member", lock)
    event.listen(engine.sync_engine, "before_cursor_execute", espiar)
    try:
        await anular(session, admin.id, member_id, metric_id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", espiar)

    assert orden[0] == "socio"
    assert orden.index("fila") < orden.index("update") < orden.index("auditoria"), orden


# Registros (Seg L-3) -------------------------------------------------------------------------

_BASE_LOG = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _extras(registro: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in registro.__dict__.items() if k not in _BASE_LOG}


async def test_el_403_deja_un_warning_con_solo_usuario_y_medicion(
    session: AsyncSession,
    admin: UsuarioPrueba,
    usuario_real: CrearUsuario,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session, consentido=True, nombre="Zulema")
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ForbiddenError):
        await anular(session, coach.id, member_id, metric_id, role="coach")

    avisos = [
        r for r in caplog.records if r.name == "app.athletes" and r.levelno >= logging.WARNING
    ]
    assert len(avisos) == 1
    assert _extras(avisos[0]) == {"user_id": str(coach.id), "metric_id": str(metric_id)}
    volcado = avisos[0].getMessage() + str(avisos[0].__dict__)
    for ajeno in ("Zulema", str(member_id), "62500", "weight_g", "apx1."):
        assert ajeno not in volcado, ajeno


async def test_la_anulacion_deja_un_info_con_solo_la_medicion(
    session: AsyncSession, admin: UsuarioPrueba, caplog: pytest.LogCaptureFixture
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    caplog.set_level(logging.DEBUG)

    await anular(session, admin.id, member_id, metric_id)

    infos = [r for r in caplog.records if r.name == "app.athletes" and r.levelno == logging.INFO]
    assert len(infos) == 1
    assert _extras(infos[0]) == {"metric_id": str(metric_id)}
    assert str(member_id) not in infos[0].getMessage() + str(infos[0].__dict__)
