"""`dashboard.service.last_movements` (S4A-B8, US-110; S4A-D28, S4A-D54).

Frases calculadas a mano con el catálogo de S4A-D28 (copiado en `test_movement_phrase.py`),
actor = parte local del correo (`ana.perez`, `juan.rios`), socio = `short_name`, monto =
`format_cop`. La activación por cobertura no lleva actor.

Escenario de US-110 (`venta_de_laura`): el plan "Plan Mensual" y la socia Laura Gómez Restrepo
los crean las fábricas (sistema: no salen); Ana vende sin pago y luego registra 120.000 en
efectivo, que activa la membresía. La cadena queda (seq desc): activa (ana), pago (ana), venta
(ana) → tres frases.

Escenario completo (`sembrar_actividad`, socia Lucía Gómez, plan "Mensual Auditoría"): las
frases de `ESPERADAS_ACTIVIDAD` (el `reveal` de la fila 6 no sale).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.dashboard.schemas import MovementOut
from app.modules.members import service as members_service
from tests.audit._apoyo import (
    ANA_EMAIL,
    CORREO_NUEVO,
    JUAN_EMAIL,
    MOTIVO_ANULACION,
    TELEFONO_NUEVO,
    Actividad,
    sembrar_actividad,
)
from tests.conftest import UsuarioPrueba
from tests.dashboard._apoyo import CAMPOS_MOVEMENT
from tests.dashboard.conftest import (
    dashboard_service,
    memberships_service,
    payments_service,
)
from tests.factories.audit_chain import make_audit_chain
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member
from tests.factories.plans import make_plan

SOCIOS: Final = "members.members"
MEMBRESIAS: Final = "memberships.memberships"
PAGOS: Final = "payments.payments"
ESPERADAS_LAURA: Final = [
    "La membresía Plan Mensual de Laura G. quedó al día",
    "ana.perez registró un pago de $ 120.000 de Laura G.",
    "ana.perez vendió Plan Mensual a Laura G.",
]
ESPERADAS_ACTIVIDAD: Final = [
    (11, MEMBRESIAS, "ana.perez actualizó la membresía Mensual Auditoría de Lucía G."),
    (10, PAGOS, "ana.perez anuló un pago de Lucía G."),
    (9, MEMBRESIAS, "La membresía Mensual Auditoría de Lucía G. quedó al día"),
    (8, PAGOS, "juan.rios registró un pago de $ 120.000 de Lucía G."),
    (7, MEMBRESIAS, "ana.perez vendió Mensual Auditoría a Lucía G."),
    (5, SOCIOS, "juan.rios actualizó los datos de Lucía G."),
    (4, SOCIOS, "ana.perez registró a Lucía G."),
]
REFERENCIA: Final = "NEQ-REF-55821"


@pytest.fixture
async def venta_de_laura(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, ana: UsuarioPrueba
) -> UUID:
    plan = await make_plan(session, name="Plan Mensual")
    laura = await make_member(
        session,
        first_name="Laura",
        last_name="Gómez Restrepo",
        document="9200000001",
        phone=None,
        email=None,
    )
    plan_id, laura_id = plan.id, laura.id
    session.expunge_all()
    with actor_scope(ana.id):
        venta = await memberships_service.sell(
            session,
            member_id=laura_id,
            plan_id=plan_id,
            role="admin",
        )
        await session.commit()
    session.expunge_all()
    with actor_scope(ana.id):
        await payments_service.register(
            session, membership_id=venta.id, amount_cop=120_000, method="cash", role="admin"
        )
        await session.commit()
    session.expunge_all()
    return laura_id


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def _frases(session: AsyncSession) -> list[str]:
    return [m.phrase for m in await dashboard_service.last_movements(session, with_finances=True)]


# Escenario de US-110 ------------------------------------------------------------------------


async def test_venta_y_pago_de_laura_dan_las_frases_esperadas_la_mas_reciente_primero(
    session: AsyncSession, venta_de_laura: UUID
) -> None:
    movimientos = await dashboard_service.last_movements(session, with_finances=True)
    assert [m.phrase for m in movimientos] == ESPERADAS_LAURA
    assert [m.table_name for m in movimientos] == [MEMBRESIAS, PAGOS, MEMBRESIAS]
    assert all(m.member_id == venta_de_laura for m in movimientos)
    assert [m.seq for m in movimientos] == sorted((m.seq for m in movimientos), reverse=True)
    assert all(isinstance(m, MovementOut) for m in movimientos)
    assert all(set(m.model_dump()) == CAMPOS_MOVEMENT for m in movimientos)


async def test_tres_entradas_dan_tres_frases(session: AsyncSession, venta_de_laura: UUID) -> None:
    assert len(await dashboard_service.last_movements(session, with_finances=True)) == 3


async def test_sin_entradas_da_lista_vacia(
    session: AsyncSession, audit_chain_factory: object, reloj: FrozenClock
) -> None:
    assert await dashboard_service.last_movements(session, with_finances=True) == []


# Escenario completo -------------------------------------------------------------------------


async def test_la_actividad_completa_da_el_catalogo_y_sin_el_reveal(
    session: AsyncSession, actividad: Actividad
) -> None:
    movimientos = await dashboard_service.last_movements(session, with_finances=True)
    assert [(m.seq, m.table_name, m.phrase) for m in movimientos] == ESPERADAS_ACTIVIDAD
    assert 6 not in {m.seq for m in movimientos}
    por_seq = {m.seq: m for m in movimientos}
    assert {s: por_seq[s].record_id for s in (7, 9, 11)} == dict.fromkeys(
        (7, 9, 11), actividad.membership_id
    )
    assert {s: por_seq[s].record_id for s in (8, 10)} == dict.fromkeys(
        (8, 10), actividad.payment_id
    )
    assert all(m.member_id == actividad.member_id for m in movimientos)


async def test_el_sistema_no_aparece_y_el_limite_de_10_se_llena_con_lo_demas(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    """Después de la actividad (7 frases de ana y juan), 30 escrituras del sistema y 5 de ana
    más recientes: salen las 5 de ana y las 5 más recientes de la actividad; ninguna del
    sistema aunque sean más nuevas que estas."""
    await make_audit_chain(session, 30, table_name=SOCIOS, user_id=SYSTEM_USER_ID)
    ultima = await make_audit_chain(session, 5, table_name=PAGOS, user_id=ana.id)
    await make_audit_chain(session, 30, table_name=MEMBRESIAS, user_id=SYSTEM_USER_ID)

    movimientos = await dashboard_service.last_movements(session, with_finances=True)

    assert len(movimientos) == 10
    seqs = [m.seq for m in movimientos]
    assert seqs[:5] == list(range(ultima, ultima - 5, -1))
    assert seqs[5:] == [11, 10, 9, 8, 7]
    assert all(not m.phrase.startswith("Sistema") for m in movimientos)
    filas = {s for s in range(ultima + 1, ultima + 31)} | set(range(ultima - 34, ultima - 4))
    assert not filas & set(seqs)


async def test_un_reveal_no_aparece(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    with actor_scope(juan.id):
        await juan_revela(session, actividad.member_id)
    movimientos = await dashboard_service.last_movements(session, with_finances=True)
    assert [m.seq for m in movimientos] == [s for s, _, _ in ESPERADAS_ACTIVIDAD]


async def juan_revela(session: AsyncSession, member_id: UUID) -> None:
    await members_service.reveal(session, member_id, "document", ip="198.51.100.41")
    await session.commit()


# Sin datos personales -------------------------------------------------------------------------


async def test_la_respuesta_serializada_no_lleva_datos_personales_blobs_ni_textos_del_pago(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    session.expunge_all()
    with actor_scope(juan.id):
        await payments_service.register(
            session,
            membership_id=actividad.membership_id,
            amount_cop=120_000,
            method="nequi",
            reference=REFERENCIA,
            role="coach",
        )
        await session.commit()
    session.expunge_all()

    movimientos = await dashboard_service.last_movements(session, with_finances=True)
    texto = "".join(m.model_dump_json() for m in movimientos)

    assert movimientos, "la prueba no revisaría nada"
    prohibidos = (
        "apx1.",
        "reference",
        "void_reason",
        REFERENCIA,
        MOTIVO_ANULACION,
        TELEFONO_NUEVO,
        CORREO_NUEVO,
        KNOWN["emergency_contact"]["name"],
        *KNOWN_NORMALIZED,
        ANA_EMAIL,
        JUAN_EMAIL,
        "@",
        "ejemplo.local",
    )
    for prohibido in prohibidos:
        assert prohibido not in texto, prohibido


async def test_el_actor_es_la_parte_local_y_nunca_el_correo(
    session: AsyncSession, actividad: Actividad
) -> None:
    frases = await _frases(session)
    assert any(f.startswith("ana.perez ") for f in frases)
    assert any(f.startswith("juan.rios ") for f in frases)
    assert all("@" not in f for f in frases)


async def test_un_socio_dado_de_baja_conserva_su_nombre(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    session.expunge_all()
    with actor_scope(ana.id):
        await members_service.deactivate(session, actividad.member_id)
        await session.commit()
    session.expunge_all()

    frases = await _frases(session)

    assert frases[0] == "ana.perez dio de baja a Lucía G."
    assert frases[1:] == [f for _, _, f in ESPERADAS_ACTIVIDAD][:9]
    assert all("un socio" not in f for f in frases)


async def test_una_reactivacion_dice_reactivo(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    for paso in (members_service.deactivate, members_service.reactivate):
        session.expunge_all()
        with actor_scope(ana.id):
            await paso(session, actividad.member_id)
            await session.commit()
    session.expunge_all()

    frases = await _frases(session)

    assert frases[:2] == ["ana.perez reactivó a Lucía G.", "ana.perez dio de baja a Lucía G."]


async def test_anular_la_membresia_dice_anulo(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    session.expunge_all()
    with actor_scope(ana.id):
        await memberships_service.cancel(
            session, membership_id=actividad.membership_id, reason="Se vendió por error"
        )
        await session.commit()
    session.expunge_all()

    frases = await _frases(session)

    assert frases[0] == "ana.perez anuló la membresía Mensual Auditoría de Lucía G."
    assert "Se vendió por error" not in "".join(frases)


# Coach sin montos (S4A-D118) ------------------------------------------------------------------


async def test_sin_finanzas_las_frases_de_pago_no_llevan_monto(
    session: AsyncSession, venta_de_laura: UUID
) -> None:
    coach = await dashboard_service.last_movements(session, with_finances=False)
    admin = await dashboard_service.last_movements(session, with_finances=True)
    assert [m.phrase for m in coach] == [
        "La membresía Plan Mensual de Laura G. quedó al día",
        "ana.perez registró un pago de Laura G.",
        "ana.perez vendió Plan Mensual a Laura G.",
    ]
    assert [m.phrase for m in admin] == ESPERADAS_LAURA
    assert all("$" not in m.phrase for m in coach)
    sin_frase = [m.model_dump(exclude={"phrase"}) for m in coach]
    assert sin_frase == [m.model_dump(exclude={"phrase"}) for m in admin]


async def test_sin_finanzas_la_anulacion_de_pago_sigue_igual(
    session: AsyncSession, actividad: Actividad
) -> None:
    coach = await dashboard_service.last_movements(session, with_finances=False)
    por_seq = {m.seq: m.phrase for m in coach}
    assert por_seq[10] == "ana.perez anuló un pago de Lucía G."
    assert por_seq[8] == "juan.rios registró un pago de Lucía G."
    assert all("$" not in frase for frase in por_seq.values())
