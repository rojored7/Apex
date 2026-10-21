"""Pruebas de `core/db.py` con PostgreSQL real (US-012, T9)."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import APP_SCHEMAS, Base, CommonColumnsMixin, SoftDeleteMixin


class CosaDePrueba(CommonColumnsMixin, SoftDeleteMixin, Base):
    __tablename__ = "cosas_de_prueba"
    __table_args__ = {"schema": "worker"}

    nombre: Mapped[str] = mapped_column()


async def _crear_tabla(session: AsyncSession) -> None:
    # create_all solo en pruebas; se revierte con el savepoint de la prueba.
    await session.run_sync(
        lambda s: Base.metadata.create_all(s.connection(), tables=[CosaDePrueba.__table__])
    )


def test_los_nueve_esquemas_de_v01() -> None:
    assert APP_SCHEMAS == (
        "audit",
        "crypto",
        "auth",
        "settings",
        "members",
        "plans",
        "memberships",
        "payments",
        "worker",
    )


def test_el_id_existe_al_construir_el_objeto() -> None:
    cosa = CosaDePrueba(nombre="x", created_by=uuid4())
    assert isinstance(cosa.id, UUID)
    fijo = uuid4()
    assert CosaDePrueba(nombre="y", created_by=uuid4(), id=fijo).id == fijo


def test_el_mixin_mapea_timestamptz_y_uuid() -> None:
    tabla = CosaDePrueba.__table__
    assert isinstance(tabla.c.created_at.type, TIMESTAMP)
    assert tabla.c.created_at.type.timezone is True
    assert tabla.c.updated_at.type.timezone is True
    assert tabla.c.created_by.nullable is False
    assert tabla.c.deleted_at.nullable is True
    assert tabla.primary_key.name == "pk_cosas_de_prueba"


async def test_las_fechas_son_timestamptz_y_llegan_en_utc(session: AsyncSession) -> None:
    await _crear_tabla(session)
    filas = await session.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'worker' AND table_name = 'cosas_de_prueba' "
            "AND column_name IN ('created_at', 'updated_at', 'deleted_at')"
        )
    )
    tipos = dict(filas.all())
    assert tipos == {
        "created_at": "timestamp with time zone",
        "updated_at": "timestamp with time zone",
        "deleted_at": "timestamp with time zone",
    }

    cosa = CosaDePrueba(nombre="hola", created_by=uuid4())
    session.add(cosa)
    await session.flush()
    await session.refresh(cosa)
    assert isinstance(cosa.created_at, datetime)
    assert cosa.created_at.tzinfo is not None
    assert cosa.created_at.utcoffset() == timedelta(0)
    assert cosa.updated_at.utcoffset() == timedelta(0)


async def test_aislamiento_a_inserta(session: AsyncSession) -> None:
    await _crear_tabla(session)
    session.add(CosaDePrueba(nombre="de la prueba a", created_by=uuid4()))
    await session.flush()
    total = await session.scalar(select(CosaDePrueba).where(CosaDePrueba.nombre == "de la prueba a"))
    assert total is not None


async def test_aislamiento_b_no_ve_lo_de_a(session: AsyncSession) -> None:
    await _crear_tabla(session)
    filas = (await session.execute(select(CosaDePrueba))).scalars().all()
    assert filas == []
