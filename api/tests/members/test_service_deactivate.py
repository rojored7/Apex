"""`members.service.deactivate` y `reactivate` con PostgreSQL real (S3-B10; US-076; D21, L-1, N-20,
S3-D54, S3-D70; blueprint B10).

Baja (`deactivate`, con `reloj`):
- la fila sigue, con `deleted_at` = el reloj (UTC) y `status='inactive'`; una fila `update` de
  auditoría con `deleted_at` y `status` antes y después; `MemberDeactivated(member_id)`;
- sale de la lista por defecto y de la búsqueda por documento, teléfono, correo y nombre, y su
  documento queda libre para un socio nuevo;
- las filas de `memberships.memberships` y `payments.payments` del socio no cambian (SQL crudo
  antes y después, con las fábricas; N-20);
- una baja repetida da `MemberAlreadyDeactivated` (409); un id inexistente `MemberNotFound`.
Reactivar (`reactivate`):
- vuelve a `active` con `deleted_at` nulo, devuelve la ficha enmascarada, audita `update` y emite
  `MemberUpdated(changed_fields=("deleted_at", "status"))`;
- con el documento tomado por otro socio vivo da `MemberDocumentDuplicated` con `existing_id` y
  el socio sigue dado de baja; sobre un vivo da `MemberNotDeactivated` (409).
L-1 (S3-D54), con `dos_sesiones` y `bus_confirmado`: `deactivate` y `reactivate` toman
`lock_member`. Una venta que llega mientras la baja tiene el candado espera y, al confirmarse la
baja, recibe `MemberInactive` (422 `member_inactive`), nunca una membresía sobre un dado de baja;
al revés, la baja espera a la venta y la membresía queda intacta. Sin 55P03 ni 40P01.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.members import service
from app.modules.members.exceptions import (
    MemberAlreadyDeactivated,
    MemberDocumentDuplicated,
    MemberNotDeactivated,
    MemberNotFound,
)
from app.modules.members.schemas import MemberDetailOut, MemberListQuery
from app.modules.memberships import service as memberships_service
from app.modules.memberships.exceptions import MemberInactive
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN, make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.members._apoyo import (
    CAMPOS_DETALLE,
    MASCARAS_KNOWN,
    auditoria_del_socio,
    crear,
    entrada,
    fila_socio,
    peticion,
)

ACTOR = UUID("0000000a-0000-4000-8000-00000000b10f")


@pytest.fixture
async def admin(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("admin")


async def dar_de_baja(session: AsyncSession, actor: UUID, member_id: UUID) -> None:
    with peticion(session, actor):
        resultado = await service.deactivate(session, member_id)
        await session.commit()
    assert resultado is None


async def reactivar(session: AsyncSession, actor: UUID, member_id: UUID) -> MemberDetailOut:
    with peticion(session, actor):
        salida = await service.reactivate(session, member_id)
        await session.commit()
    return salida


async def fallar(session: AsyncSession, actor: UUID, llamada: Awaitable[Any], error: type) -> Any:
    with pytest.raises(error) as capturado, actor_scope(actor):
        await llamada
    await session.rollback()
    return capturado.value


async def _crudas(session: AsyncSession, sql: str, member_id: UUID) -> list[dict[str, Any]]:
    filas = (await session.execute(text(sql), {"m": member_id})).mappings().all()
    return [dict(f) for f in filas]


# Baja -----------------------------------------------------------------------------------------


async def test_la_baja_fija_deleted_at_del_reloj_e_inactive(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    fila = await fila_socio(session, socio.id)
    assert fila["deleted_at"] == reloj.now_utc()
    assert fila["deleted_at"].utcoffset() == timedelta(0)
    assert fila["status"] == "inactive"
    assert fila["document"] is not None  # la baja no borra datos (N-20)


async def test_la_baja_audita_update_con_deleted_at_y_status(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    (fila,) = await auditoria_del_socio(session, socio.id, "update")
    assert fila["user_id"] == admin.id
    assert set(fila["before"]) == {"deleted_at", "status"}
    assert fila["before"]["deleted_at"] is None and fila["before"]["status"] == "active"
    assert fila["after"]["status"] == "inactive" and fila["after"]["deleted_at"] is not None


async def test_la_baja_emite_member_deactivated(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    socio = await make_member(session)
    recibidos = capturar_eventos(service.MemberDeactivated)
    await dar_de_baja(session, admin.id, socio.id)
    assert recibidos == [service.MemberDeactivated(member_id=socio.id, occurred_at=T0)]


async def test_el_dado_de_baja_sale_de_la_lista_y_de_las_busquedas(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    terminos = (KNOWN["document"], "3007654321", "lucia.gomez@correo.co", "Lucía Gómez")
    for termino in terminos:
        assert await service.search_ids(session, termino) == {socio.id}, termino
    await dar_de_baja(session, admin.id, socio.id)
    pagina = await service.list(session, MemberListQuery(), PageParams(limit=50, offset=0))
    assert socio.id not in {fila.id for fila in pagina.items}
    for termino in terminos:
        assert await service.search_ids(session, termino) == set(), termino
    bajas = await service.list(
        session, MemberListQuery(status="deleted"), PageParams(limit=50, offset=0)
    )
    assert socio.id in {fila.id for fila in bajas.items}


async def test_su_documento_queda_libre_para_un_socio_nuevo(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    nuevo = await crear(session, admin.id, entrada())
    assert nuevo.id != socio.id
    assert await service.id_by_document(session, KNOWN["document"]) == nuevo.id


async def test_la_baja_no_toca_membresias_ni_pagos(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active")
    await make_payment(session, membresia, amount=60_000)
    sql_m = "SELECT * FROM memberships.memberships WHERE member_id = :m ORDER BY id"
    sql_p = "SELECT * FROM payments.payments WHERE member_id = :m ORDER BY id"
    antes = (await _crudas(session, sql_m, socio.id), await _crudas(session, sql_p, socio.id))
    assert antes[0] and antes[1]
    await dar_de_baja(session, admin.id, socio.id)
    despues = (await _crudas(session, sql_m, socio.id), await _crudas(session, sql_p, socio.id))
    assert despues == antes


async def test_una_baja_repetida_da_409(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    antes = await fila_socio(session, socio.id)
    session.expunge_all()
    error = await fallar(
        session, admin.id, service.deactivate(session, socio.id), MemberAlreadyDeactivated
    )
    assert (error.status, error.code) == (409, "member_already_deactivated")
    assert await fila_socio(session, socio.id) == antes


async def test_un_id_inexistente_da_404_en_baja_y_reactivacion(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    inexistente = UUID("00000000-0000-4000-8000-00000000b110")
    await fallar(session, admin.id, service.deactivate(session, inexistente), MemberNotFound)
    await fallar(session, admin.id, service.reactivate(session, inexistente), MemberNotFound)


# Reactivar ------------------------------------------------------------------------------------


async def test_reactivar_vuelve_a_active_y_devuelve_la_ficha(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    recibidos = capturar_eventos(service.MemberUpdated)
    reactivados = capturar_eventos(service.MemberReactivated)
    salida = await reactivar(session, admin.id, socio.id)
    fila = await fila_socio(session, socio.id)
    assert (fila["status"], fila["deleted_at"]) == ("active", None)
    assert isinstance(salida, MemberDetailOut)
    assert set(salida.model_dump()) == CAMPOS_DETALLE
    assert (salida.status, salida.deleted_at) == ("active", None)
    assert salida.document == MASCARAS_KNOWN["document"]
    assert recibidos == [
        service.MemberUpdated(
            member_id=socio.id, changed_fields=("deleted_at", "status"), occurred_at=T0
        )
    ]
    # Fase 4 del Sprint 3 (M1, PM1; S3-D89): el evento propio que invalida el resumen.
    assert reactivados == [service.MemberReactivated(member_id=socio.id, occurred_at=T0)]
    updates = await auditoria_del_socio(session, socio.id, "update")
    assert len(updates) == 2
    assert updates[-1]["after"]["status"] == "active"
    assert updates[-1]["after"]["deleted_at"] is None
    assert await service.search_ids(session, KNOWN["document"]) == {socio.id}


async def test_reactivar_con_el_documento_tomado_da_409_con_existing_id(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await dar_de_baja(session, admin.id, socio.id)
    nuevo = await crear(session, admin.id, entrada())
    session.expunge_all()
    error = await fallar(
        session, admin.id, service.reactivate(session, socio.id), MemberDocumentDuplicated
    )
    assert (error.status, error.code, error.field) == (
        409,
        "member_document_duplicated",
        "document",
    )
    assert error.existing_id == nuevo.id
    fila = await fila_socio(session, socio.id)
    assert fila["deleted_at"] is not None and fila["status"] == "inactive"


async def test_reactivar_un_vivo_da_409(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    error = await fallar(
        session, admin.id, service.reactivate(session, socio.id), MemberNotDeactivated
    )
    assert (error.status, error.code) == (409, "member_not_deactivated")


# L-1 (S3-D54): baja frente a venta, con commit real ----------------------------------------


_ESPERA_DEL_SOCIO = (
    "SELECT count(*) FROM pg_locks, (SELECT hashtextextended(:m, 0) AS h) AS llave "
    "WHERE locktype = 'advisory' AND NOT granted AND objsubid = 1 "
    "AND classid::text::bigint = (llave.h >> 32) & 4294967295 "
    "AND objid::text::bigint = llave.h & 4294967295"
)
"""Conexiones esperando EL candado del socio (`lock_member`: `hashtextextended(<uuid>, 0)`), no
cualquier candado asesor (la cadena de auditoría también lo es)."""


async def _esperando_candado_asesor(engine: AsyncEngine, member_id: UUID) -> None:
    """Espera (hasta 5 s) a que otra conexión quede bloqueada en `lock_member(member_id)`."""
    for _ in range(100):
        async with engine.connect() as conexion:
            if await conexion.scalar(text(_ESPERA_DEL_SOCIO), {"m": str(member_id)}):
                return
        await asyncio.sleep(0.05)
    raise AssertionError("la segunda transacción no quedó esperando el candado del socio")


async def _vender(sesion: AsyncSession, member_id: UUID, plan_id: UUID) -> Any:
    with actor_scope(ACTOR):
        try:
            await sesion.execute(text("SET LOCAL lock_timeout = '5s'"))
            salida = await memberships_service.sell(sesion, member_id=member_id, plan_id=plan_id)
            await sesion.commit()
        except Exception as error:
            await sesion.rollback()
            return error
    return salida


async def _membresias(engine: AsyncEngine, member_id: UUID) -> int:
    async with engine.connect() as conexion:
        consulta = text("SELECT count(*) FROM memberships.memberships WHERE member_id = :m")
        return int(await conexion.scalar(consulta, {"m": member_id}) or 0)


async def test_la_venta_que_llega_durante_la_baja_recibe_member_inactive(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera, document=unique_document(), phone=None, email=None)
    plan = await make_plan(primera)
    with actor_scope(ACTOR):
        await service.deactivate(primera, socio.id)  # toma el candado y no confirma todavía
    venta = asyncio.create_task(_vender(segunda, socio.id, plan.id))
    try:
        await _esperando_candado_asesor(engine, socio.id)
    finally:
        await primera.commit()
    resultado = await venta
    assert isinstance(resultado, MemberInactive), resultado
    assert (resultado.status, resultado.code) == (422, "member_inactive")
    assert await _membresias(engine, socio.id) == 0


async def test_la_baja_que_llega_durante_la_venta_espera_y_no_toca_la_membresia(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera, document=unique_document(), phone=None, email=None)
    plan = await make_plan(primera)
    with actor_scope(ACTOR):
        await memberships_service.sell(primera, member_id=socio.id, plan_id=plan.id)

    async def baja() -> Any:
        with actor_scope(ACTOR):
            try:
                await segunda.execute(text("SET LOCAL lock_timeout = '5s'"))
                await service.deactivate(segunda, socio.id)
                await segunda.commit()
            except Exception as error:
                await segunda.rollback()
                return error
        return None

    tarea = asyncio.create_task(baja())
    try:
        await _esperando_candado_asesor(engine, socio.id)
    finally:
        await primera.commit()
    assert await tarea is None
    async with engine.connect() as conexion:
        fila = (
            (
                await conexion.execute(
                    text("SELECT deleted_at, status FROM members.members WHERE id = :m"),
                    {"m": socio.id},
                )
            )
            .mappings()
            .one()
        )
        estados = list(
            await conexion.scalars(
                text("SELECT status FROM memberships.memberships WHERE member_id = :m"),
                {"m": socio.id},
            )
        )
    assert fila["deleted_at"] is not None and fila["status"] == "inactive"
    assert estados == ["pending_payment"]


async def test_reactivar_toma_el_candado_del_socio(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    """Con el candado del socio tomado por otra transacción, `reactivate` espera."""
    from app.core.locks import lock_member

    primera, segunda = dos_sesiones
    socio = await make_member(
        primera,
        document=unique_document(),
        phone=None,
        email=None,
        deleted_at=T0 - timedelta(days=1),
        status="inactive",
    )
    await lock_member(primera, socio.id)

    async def reactivar_en_segunda() -> Any:
        with actor_scope(ACTOR):
            salida = await service.reactivate(segunda, socio.id)
            await segunda.commit()
        return salida

    tarea = asyncio.create_task(reactivar_en_segunda())
    try:
        await _esperando_candado_asesor(engine, socio.id)
    finally:
        await primera.commit()
    salida = await tarea
    assert salida.status == "active"


async def test_la_baja_no_cambia_una_membresia_futura(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """La baja deja la membresía que ya tenía tal cual, también una futura (N-20)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    futura = await make_membership(
        session, socio, plan, status="active", start=date(2026, 11, 1), end=date(2026, 11, 30)
    )
    await dar_de_baja(session, admin.id, socio.id)
    estado = await session.scalar(
        text("SELECT status FROM memberships.memberships WHERE id = :id"), {"id": futura.id}
    )
    assert estado == "active"
