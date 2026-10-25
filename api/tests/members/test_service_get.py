"""`members.service.get` (la ficha) y `detail._decrypt_fields` con PostgreSQL real (S3-B9b;
US-073 criterios 1 a 6; D20, D-4, N-01, N-20, Q6; blueprint B9 y demo 6).

- Los cinco campos de `KNOWN` vuelven enmascarados (`CC •••• 2046`, `••• ••• 4321`,
  `l•••@•••.co`, `••/••/1991`, `Registrado`); ningún valor en claro ni blob en la salida.
- `crypto_ops`: cinco filas `decrypt` con `purpose='mask'`, el `record_id` del socio, la
  `data_class` de cada campo y el actor como `user_id`; sin lote (`batch_id` nulo, D20); ninguna
  con `purpose='reveal'`; ninguna fila `reveal` (ni ninguna otra) en `audit.audit_log`.
- Los campos nulos no se descifran ni dejan fila y salen `None`.
- Un socio dado de baja devuelve su ficha con `deleted_at` (N-20).
- `membership_status`, `plan_name` y `membership_end_date` salen de `status_for` (la membresía
  que decide; vigente más futura muestra la vigente); sin membresías, `none` y nulos.
- `warnings == []` (solo el alta y la edición los llevan) y las claves son `CAMPOS_DETALLE`.
- Un id inexistente da `MemberNotFound` sin descifrar nada.
- `_decrypt_fields(socio, campos, purpose)`: solo los campos pedidos y no nulos, en claro y con
  su tipo (`date`, mapeo), una fila `decrypt` por campo con el `purpose` recibido.

Cada ficha se lee como una petición: sesión sin objetos cargados (`expunge_all`), actor y commit
(la bitácora `crypto_ops` se vacía en `before_commit`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import detail, service
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.models import Member
from app.modules.members.schemas import MemberDetailOut
from tests.conftest import T0, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import CAMPOS_DETALLE, MASCARAS_KNOWN, operaciones

CINCO = ("document", "phone", "email", "birth_date", "emergency_contact")


@pytest.fixture
async def coach(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("coach")


async def ficha(session: AsyncSession, actor: UUID, member_id: UUID) -> MemberDetailOut:
    """Una petición: sesión limpia, `service.get` bajo el actor y commit."""
    session.expunge_all()
    with actor_scope(actor):
        salida = await service.get(session, member_id)
        await session.commit()
    return salida


async def _descifrados(session: AsyncSession, record_id: UUID) -> list[dict[str, Any]]:
    return await operaciones(session, verb="decrypt", record_id=record_id)


async def _auditoria(session: AsyncSession, record_id: UUID) -> list[dict[str, Any]]:
    consulta = text("SELECT action FROM audit.audit_log WHERE record_id = :id ORDER BY seq")
    return [dict(f) for f in (await session.execute(consulta, {"id": record_id})).mappings()]


# Máscaras y bitácora (D20) ------------------------------------------------------------------


async def test_los_cinco_campos_vuelven_enmascarados(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    salida = await ficha(session, coach.id, socio.id)
    for campo, mascara in MASCARAS_KNOWN.items():
        assert getattr(salida, campo) == mascara, campo
    assert (salida.first_name, salida.last_name, salida.document_type) == ("Lucía", "Gómez", "CC")
    texto = salida.model_dump_json()
    for valor in (*KNOWN_NORMALIZED, "apx1."):
        assert valor not in texto, valor


async def test_cinco_filas_decrypt_con_proposito_mask_record_id_y_actor(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    antes = len(await _descifrados(session, socio.id))
    await ficha(session, coach.id, socio.id)
    filas = (await _descifrados(session, socio.id))[antes:]
    assert len(filas) == 5, filas
    assert {f["purpose"] for f in filas} == {"mask"}
    assert {f["record_id"] for f in filas} == {socio.id}
    assert {f["user_id"] for f in filas} == {coach.id}
    assert {f["result"] for f in filas} == {"ok"}
    assert all(f["batch_id"] is None for f in filas)  # D20: sin lote, cada fila con su socio
    assert sorted(f["data_class"] for f in filas) == sorted(f"member.{c}" for c in CINCO)


async def test_la_ficha_nunca_deja_reveal_ni_auditoria(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    auditoria_antes = await _auditoria(session, socio.id)
    await ficha(session, coach.id, socio.id)
    await ficha(session, coach.id, socio.id)
    assert await operaciones(session, purpose="reveal", record_id=socio.id) == []
    assert await _auditoria(session, socio.id) == auditoria_antes
    assert all(f["action"] != "reveal" for f in auditoria_antes)
    agrupado = await session.execute(
        text(
            "SELECT verb, purpose, count(*) AS n FROM crypto.crypto_ops WHERE record_id = :id "
            "AND verb = 'decrypt' GROUP BY 1, 2"
        ),
        {"id": socio.id},
    )
    assert [tuple(f) for f in agrupado] == [("decrypt", "mask", 10)]


async def test_los_campos_nulos_no_se_descifran_ni_dejan_fila(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(
        session,
        document=unique_document(),
        phone=None,
        email=None,
        birth_date=None,
        emergency_contact=None,
    )
    salida = await ficha(session, coach.id, socio.id)
    assert salida.document is not None and salida.document.startswith("CC •••• ")
    assert (salida.phone, salida.email, salida.birth_date, salida.emergency_contact) == (
        None,
        None,
        None,
        None,
    )
    filas = await _descifrados(session, socio.id)
    assert [f["data_class"] for f in filas] == ["member.document"]


async def test_el_contrato_de_la_ficha(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session, sex="f")
    salida = await ficha(session, coach.id, socio.id)
    assert set(salida.model_dump()) == CAMPOS_DETALLE
    assert salida.id == socio.id
    assert salida.warnings == []
    assert salida.status == "active" and salida.sex == "f" and salida.deleted_at is None
    assert salida.created_at == socio.created_at and salida.updated_at == socio.updated_at


async def test_sin_consentimiento_tampoco_hay_avisos(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """Los avisos son del alta y la edición; la ficha no los recalcula (`warnings == []`)."""
    socio = await make_member(session, data_consent_at=None)
    salida = await ficha(session, coach.id, socio.id)
    assert salida.warnings == [] and salida.data_consent_at is None


# Dados de baja (N-20) e inexistentes -------------------------------------------------------


async def test_un_dado_de_baja_devuelve_su_ficha_con_deleted_at(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    baja = T0 - timedelta(days=2)
    socio = await make_member(session, deleted_at=baja, status="inactive")
    salida = await ficha(session, coach.id, socio.id)
    assert salida.deleted_at == baja
    assert salida.status == "inactive"
    assert salida.document == MASCARAS_KNOWN["document"]


async def test_un_id_inexistente_da_member_not_found_sin_descifrar(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    await make_member(session)
    antes = len(await operaciones(session, verb="decrypt"))
    session.expunge_all()
    with actor_scope(coach.id):
        with pytest.raises(MemberNotFound) as error:
            await service.get(session, uuid4())
        await session.commit()
    assert error.value.status == 404 and error.value.code == "member_not_found"
    assert len(await operaciones(session, verb="decrypt")) == antes


# Estado de membresía (status_for, G-03, G-04) ------------------------------------------------


async def test_estado_plan_y_fin_salen_de_la_membresia_que_decide(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """Vigente Trimestral más renovación Mensual pendiente: decide la vigente (Q1)."""
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    socio = await make_member(session)
    await make_membership(
        session,
        socio,
        trimestral,
        status="active",
        start=date(2026, 9, 1),
        end=date(2026, 11, 29),
    )
    await make_membership(
        session,
        socio,
        mensual,
        status="pending_payment",
        start=date(2026, 11, 30),
        end=date(2026, 12, 29),
    )
    salida = await ficha(session, coach.id, socio.id)
    assert (salida.membership_status, salida.plan_name, salida.membership_end_date) == (
        "active",
        "Trimestral",
        date(2026, 11, 29),
    )


async def test_por_vencer_en_la_ficha(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    mensual = await make_plan(session, name="Mensual")
    socio = await make_member(session)
    await make_membership(
        session, socio, mensual, status="active", start=date(2026, 9, 26), end=date(2026, 10, 25)
    )
    salida = await ficha(session, coach.id, socio.id)
    assert (salida.membership_status, salida.plan_name, salida.membership_end_date) == (
        "expiring",
        "Mensual",
        date(2026, 10, 25),
    )


async def test_sin_membresias_la_ficha_dice_none(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    mensual = await make_plan(session, name="Mensual")
    socio = await make_member(session)
    await make_membership(session, socio, mensual, status="cancelled")
    salida = await ficha(session, coach.id, socio.id)
    assert (salida.membership_status, salida.plan_name, salida.membership_end_date) == (
        "none",
        None,
        None,
    )


async def test_el_dado_de_baja_conserva_su_estado_de_membresia(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    mensual = await make_plan(session, name="Mensual")
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1))
    await make_membership(
        session, socio, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    salida = await ficha(session, coach.id, socio.id)
    assert salida.deleted_at is not None
    assert (salida.membership_status, salida.plan_name) == ("active", "Mensual")


# `_decrypt_fields` (D-4) -------------------------------------------------------------------


async def _cargar(session: AsyncSession, member_id: UUID) -> Member:
    session.expunge_all()
    socio = await session.scalar(select(Member).where(Member.id == member_id))
    assert socio is not None
    return socio


async def test_decrypt_fields_descifra_solo_los_pedidos_y_no_nulos(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    creado = await make_member(session, email=None)
    socio = await _cargar(session, creado.id)
    with actor_scope(coach.id):
        valores = detail._decrypt_fields(socio, ("document", "email", "birth_date"), "mask")
        await session.commit()
    assert valores == {"document": KNOWN["document"], "birth_date": KNOWN["birth_date"]}
    filas = await _descifrados(session, creado.id)
    assert sorted(f["data_class"] for f in filas) == ["member.birth_date", "member.document"]


async def test_decrypt_fields_devuelve_el_contacto_como_mapeo_y_usa_el_proposito_recibido(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    creado = await make_member(session)
    socio = await _cargar(session, creado.id)
    with actor_scope(coach.id):
        valores = detail._decrypt_fields(socio, ("emergency_contact", "phone"), "reveal")
        await session.commit()
    assert valores == {
        "emergency_contact": dict(KNOWN["emergency_contact"]),
        "phone": KNOWN["phone"],
    }
    filas = await _descifrados(session, creado.id)
    assert {(f["purpose"], f["user_id"]) for f in filas} == {("reveal", coach.id)}
    assert len(filas) == 2


async def test_decrypt_fields_sin_campos_no_deja_filas(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    creado = await make_member(session)
    socio = await _cargar(session, creado.id)
    with actor_scope(coach.id):
        assert detail._decrypt_fields(socio, (), "mask") == {}
        await session.commit()
    assert await _descifrados(session, creado.id) == []


def test_los_campos_cifrados_de_la_ficha_son_los_cinco_del_modelo() -> None:
    assert detail.CAMPOS_CIFRADOS == CINCO
    assert detail.MASK_PURPOSE == "mask"
