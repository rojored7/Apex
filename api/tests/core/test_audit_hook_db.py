"""Hook `after_flush` con PostgreSQL real (US-016 T9 y primera parte de T10)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

import pytest
from sqlalchemy import String, TypeDecorator, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import (
    AuditEntry,
    PlaintextInAuditError,
    install_audit_listeners,
    verify_chain,
)
from app.core.context import SYSTEM_USER_ID, MissingActorError, actor_scope
from app.core.db import Base, CommonColumnsMixin, SoftDeleteMixin

ACTOR = UUID(int=42)
SOCIO = UUID(int=77)


class CifradoFalso(TypeDecorator[str]):
    """Imita el contrato de US-028: el atributo guarda el blob y el tipo marca `is_encrypted`."""

    impl = String
    cache_ok = True
    is_encrypted = True

    def process_bind_param(self, value: object, dialect: object) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return value


class SocioAuditado(CommonColumnsMixin, SoftDeleteMixin, Base):
    __tablename__ = "socios_auditados"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True
    __audit_redact__: ClassVar[frozenset[str]] = frozenset({"secreto"})
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset({"ultimo_acceso"})
    __audit_subject__: ClassVar[str] = "id"

    nombre: Mapped[str] = mapped_column()
    notas: Mapped[str | None] = mapped_column(default=None)
    secreto: Mapped[str] = mapped_column(default="hash")
    ultimo_acceso: Mapped[datetime | None] = mapped_column(default=None)
    documento: Mapped[str | None] = mapped_column(CifradoFalso, default=None)


class PagoAuditado(CommonColumnsMixin, Base):
    __tablename__ = "pagos_auditados"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    member_id: Mapped[UUID] = mapped_column()
    amount_cop: Mapped[int] = mapped_column()


class CosaNoAuditada(CommonColumnsMixin, Base):
    __tablename__ = "cosas_no_auditadas"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    nombre: Mapped[str] = mapped_column()


TABLAS = [SocioAuditado.__table__, PagoAuditado.__table__, CosaNoAuditada.__table__]


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    install_audit_listeners()
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    await session.run_sync(lambda s: Base.metadata.create_all(s.connection(), tables=TABLAS))
    with actor_scope(ACTOR):
        yield session


async def _auditoria(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
    return [dict(m) for m in (await session.execute(consulta)).mappings().all()]


async def test_insercion_deja_insert_con_after_actor_y_sujeto(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana", notas="x")
    db.add(socio)
    await db.flush()
    filas = await _auditoria(db)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["action"] == "insert"
    assert fila["table_name"] == "worker.socios_auditados"
    assert fila["record_id"] == socio.id
    assert fila["user_id"] == ACTOR
    assert fila["subject_member_id"] == socio.id
    assert fila["before"] is None
    assert fila["after"]["nombre"] == "Ana" and fila["after"]["notas"] == "x"
    assert fila["after"]["id"] == str(socio.id)
    assert fila["after"]["secreto"] == "***"
    assert "created_at" not in fila["after"] and "updated_at" not in fila["after"]
    assert fila["after"]["created_by"] == str(ACTOR)


async def test_created_by_se_llena_con_el_actor(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana")
    db.add(socio)
    await db.flush()
    assert socio.created_by == ACTOR
    explicito = SocioAuditado(nombre="Eva", created_by=SYSTEM_USER_ID)
    db.add(explicito)
    await db.flush()
    assert explicito.created_by == SYSTEM_USER_ID


async def test_update_de_dos_columnas_solo_lleva_esas_dos(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana", notas="x")
    db.add(socio)
    await db.flush()
    socio.nombre = "Ana María"
    socio.notas = None
    await db.flush()
    filas = await _auditoria(db)
    assert [f["action"] for f in filas] == ["insert", "update"]
    assert filas[1]["before"] == {"nombre": "Ana", "notas": "x"}
    assert filas[1]["after"] == {"nombre": "Ana María", "notas": None}
    assert filas[1]["record_id"] == socio.id and filas[1]["subject_member_id"] == socio.id


async def test_mismo_valor_o_columna_excluida_no_deja_fila(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana")
    db.add(socio)
    await db.flush()
    socio.nombre = "Ana"
    await db.flush()
    socio.ultimo_acceso = datetime(2026, 1, 1, tzinfo=UTC)
    await db.flush()
    assert [f["action"] for f in await _auditoria(db)] == ["insert"]


async def test_modelo_no_auditado_no_deja_filas(db: AsyncSession) -> None:
    db.add(CosaNoAuditada(nombre="x"))
    await db.flush()
    assert await _auditoria(db) == []


async def test_borrado_logico_es_update_y_fisico_es_delete(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana")
    db.add(socio)
    await db.flush()
    baja = datetime(2026, 10, 21, tzinfo=UTC)
    socio.deleted_at = baja
    await db.flush()
    await db.delete(socio)
    await db.flush()
    filas = await _auditoria(db)
    assert [f["action"] for f in filas] == ["insert", "update", "delete"]
    assert filas[1]["before"] == {"deleted_at": None}
    assert filas[1]["after"] == {"deleted_at": "2026-10-21T00:00:00.000000Z"}
    assert filas[2]["after"] is None
    assert filas[2]["before"]["nombre"] == "Ana" and filas[2]["before"]["id"] == str(socio.id)
    assert verify_chain(filas).ok is True


async def test_sujeto_por_member_id_y_sin_sujeto(db: AsyncSession) -> None:
    db.add(PagoAuditado(member_id=SOCIO, amount_cop=120_000))
    await db.flush()
    fila = (await _auditoria(db))[0]
    assert fila["subject_member_id"] == SOCIO
    assert fila["after"]["amount_cop"] == 120_000


async def test_sin_actor_el_flush_falla(db: AsyncSession) -> None:
    from app.core.context import current_actor

    token = current_actor.set(None)
    try:
        db.add(SocioAuditado(nombre="Ana"))
        with pytest.raises(MissingActorError):
            await db.flush()
    finally:
        current_actor.reset(token)
    await db.rollback()


async def test_rollback_no_deja_auditoria(session: AsyncSession) -> None:
    install_audit_listeners()
    await session.run_sync(lambda s: Base.metadata.create_all(s.connection(), tables=TABLAS))
    antes = len(await _auditoria(session))
    async with session.begin_nested():
        with actor_scope(ACTOR):
            session.add(SocioAuditado(nombre="Ana"))
            await session.flush()
        assert len(await _auditoria(session)) == antes + 1
        await session.rollback()
    assert len(await _auditoria(session)) == antes


async def test_dos_flushes_mantienen_la_cadena(db: AsyncSession) -> None:
    for n in range(3):
        db.add(SocioAuditado(nombre=f"S{n}"))
        await db.flush()
    db.add(PagoAuditado(member_id=SOCIO, amount_cop=1))
    db.add(PagoAuditado(member_id=SOCIO, amount_cop=2))
    await db.flush()
    filas = await _auditoria(db)
    assert [f["seq"] for f in filas] == [1, 2, 3, 4, 5]
    assert verify_chain(filas).ok is True


async def test_columna_cifrada_entra_como_blob_y_el_claro_rompe_el_flush(db: AsyncSession) -> None:
    socio = SocioAuditado(nombre="Ana", documento="apx1.k1.A256GCM.bm9uY2U.Y3Q")
    db.add(socio)
    await db.flush()
    fila = (await _auditoria(db))[0]
    assert fila["after"]["documento"].startswith("apx1.")
    assert "1020304" not in str(fila["after"])

    socio.documento = "1020304"
    with pytest.raises(PlaintextInAuditError):
        await db.flush()
    await db.rollback()


async def test_record_toma_el_actor_del_contexto(db: AsyncSession) -> None:
    from app.core.audit import record

    fila = await record(
        db,
        action="reveal",
        table_name="members",
        record_id=SOCIO,
        before=None,
        after={"field": "document"},
        subject_member_id=SOCIO,
    )
    assert fila.user_id == ACTOR
    guardada = (await _auditoria(db))[0]
    assert guardada["subject_member_id"] == SOCIO and guardada["user_id"] == ACTOR
    assert verify_chain([guardada]).ok is True
