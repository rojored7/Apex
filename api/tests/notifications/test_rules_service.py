"""`notifications.service` de reglas con PostgreSQL real (S5-B6, US-121; S5-D24, S5-D25).
# Rojo B6

- `create_rule`: `RuleOut`, `created_by` = actor, auditoría `insert`; `validate_rule` corre en el
  service (signo del desfase: `RuleValidationError`, `field="offset_days"`); plantilla inexistente
  da 422 con `field="template_id"`; una activa duplicada (mismo disparador, desfase y canal) da
  `DuplicateActiveRule` (409, `existing_id`); una inactiva o una de otro canal no chocan.
- `update_rule`: se valida la regla RESULTANTE (cambiar solo el disparador deja el desfase viejo);
  reactivar una regla cuya clave ya tiene otra activa da 409; la propia regla no choca consigo.
- Carrera: dos altas activas iguales a la vez; el único parcial decide y la perdedora recibe 409.
- `get_rule` / `list_rules`: filtros `is_active`, `channel`, `trigger`, `q` (nombre), orden
  `offset_days, channel, id` y paginación.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.pagination import PageParams
from app.modules.notifications import service
from app.modules.notifications.exceptions import (
    DuplicateActiveRule,
    RuleNotFound,
    RuleValidationError,
)
from app.modules.notifications.models import NotificationRule
from app.modules.notifications.schemas import RuleFilters, RuleOut, RulePatch
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.notifications import make_rule, make_template
from tests.notifications._apoyo import (
    CAMPOS_REGLA,
    T_REGLAS,
    contar,
    en_peticion,
    fila,
    filas_de_auditoria,
    regla_in,
)


@pytest.fixture
async def admin(usuario_real: CrearUsuario, reloj: FrozenClock) -> UsuarioPrueba:
    return await usuario_real("admin")


# create_rule ------------------------------------------------------------------------------------


async def test_create_rule_devuelve_el_contrato_y_guarda_la_fila(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    plantilla = await make_template(session)
    salida = await en_peticion(
        session, admin.id, lambda: service.create_rule(session, regla_in(plantilla.id))
    )
    assert isinstance(salida, RuleOut)
    assert set(salida.model_dump()) == CAMPOS_REGLA
    assert (salida.trigger, salida.offset_days, salida.channel) == (
        "membership_expiring",
        -3,
        "whatsapp_link",
    )
    assert salida.template_id == plantilla.id and salida.is_active is True
    assert (await fila(session, T_REGLAS, salida.id))["created_by"] == admin.id


async def test_create_rule_audita_un_insert_a_nombre_del_actor(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    plantilla = await make_template(session)
    await en_peticion(
        session, admin.id, lambda: service.create_rule(session, regla_in(plantilla.id))
    )
    assert await filas_de_auditoria(session, T_REGLAS) == [("insert", admin.id)]


@pytest.mark.parametrize(
    ("trigger", "offset"),
    [("membership_expiring", 1), ("membership_expired", 0), ("membership_expired", -1)],
)
async def test_create_rule_con_el_signo_equivocado_da_422_y_no_escribe(
    session: AsyncSession, admin: UsuarioPrueba, trigger: str, offset: int
) -> None:
    plantilla = await make_template(session)
    datos = regla_in(plantilla.id, trigger=trigger, offset_days=offset)
    with pytest.raises(RuleValidationError) as capturado:
        await en_peticion(session, admin.id, lambda: service.create_rule(session, datos))
    assert capturado.value.field == "offset_days"
    assert await contar(session, T_REGLAS) == 0


async def test_create_rule_con_plantilla_inexistente_da_422_con_template_id(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    with pytest.raises(RuleValidationError) as capturado:
        await en_peticion(
            session, admin.id, lambda: service.create_rule(session, regla_in(uuid4()))
        )
    assert (capturado.value.status, capturado.value.field) == (422, "template_id")
    await session.rollback()
    assert await contar(session, T_REGLAS) == 0


async def test_create_rule_activa_duplicada_da_409_con_el_id_de_la_existente(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    existente = await make_rule(session)
    with pytest.raises(DuplicateActiveRule) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.create_rule(session, regla_in(existente.template_id, name="Otra")),
        )
    error = capturado.value
    assert (error.status, error.code, error.existing_id) == (
        409,
        "duplicate_active_rule",
        existente.id,
    )
    await session.rollback()
    assert await contar(session, T_REGLAS) == 1


@pytest.mark.parametrize(
    "cambio",
    [
        {"is_active": False},
        {"channel": "email"},
        {"offset_days": 0},
        {"trigger": "membership_expired", "offset_days": 1},
    ],
)
async def test_create_rule_que_difiere_en_la_clave_o_esta_inactiva_no_choca(
    session: AsyncSession, admin: UsuarioPrueba, cambio: dict[str, object]
) -> None:
    existente = await make_rule(session)
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.create_rule(session, regla_in(existente.template_id, **cambio)),
    )
    assert salida.id != existente.id
    assert await contar(session, T_REGLAS) == 2


async def test_create_rule_inactiva_puede_repetirse_las_veces_que_haga_falta(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    plantilla = await make_template(session)
    for _ in range(2):
        await en_peticion(
            session,
            admin.id,
            lambda: service.create_rule(session, regla_in(plantilla.id, is_active=False)),
        )
    assert await contar(session, T_REGLAS) == 2


# update_rule ------------------------------------------------------------------------------------


async def test_update_rule_aplica_solo_lo_enviado_y_audita(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session, name="Vence en 3 días")
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.update_rule(session, base.id, RulePatch(name="Aviso previo")),
    )
    assert salida.name == "Aviso previo"
    assert (salida.trigger, salida.offset_days, salida.channel) == (
        "membership_expiring",
        -3,
        "whatsapp_link",
    )
    assert await filas_de_auditoria(session, T_REGLAS) == [
        ("insert", SYSTEM_USER_ID),
        ("update", admin.id),
    ]


async def test_update_rule_sin_cambios_no_audita(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session)
    antes = await filas_de_auditoria(session, T_REGLAS)
    await en_peticion(session, admin.id, lambda: service.update_rule(session, base.id, RulePatch()))
    assert await filas_de_auditoria(session, T_REGLAS) == antes


async def test_update_rule_valida_la_regla_resultante_y_no_solo_los_campos_enviados(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session, trigger="membership_expiring", offset_days=-3)
    with pytest.raises(RuleValidationError) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_rule(session, base.id, RulePatch(trigger="membership_expired")),
        )
    assert capturado.value.field == "offset_days"
    await session.rollback()
    assert (await fila(session, T_REGLAS, base.id))["trigger"] == "membership_expiring"


async def test_update_rule_cambia_disparador_y_desfase_a_la_vez(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session, trigger="membership_expiring", offset_days=-3)
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.update_rule(
            session, base.id, RulePatch(trigger="membership_expired", offset_days=7)
        ),
    )
    assert (salida.trigger, salida.offset_days) == ("membership_expired", 7)


async def test_update_rule_con_plantilla_inexistente_da_422_con_template_id(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session)
    with pytest.raises(RuleValidationError) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_rule(session, base.id, RulePatch(template_id=uuid4())),
        )
    assert capturado.value.field == "template_id"
    await session.rollback()


async def test_update_rule_a_una_clave_activa_ajena_da_409(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    ocupante = await make_rule(session, offset_days=0, name="Vence hoy")
    base = await make_rule(session, template_id=ocupante.template_id, offset_days=-3)
    with pytest.raises(DuplicateActiveRule) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_rule(session, base.id, RulePatch(offset_days=0)),
        )
    assert capturado.value.existing_id == ocupante.id
    await session.rollback()


async def test_reactivar_una_regla_cuya_clave_ya_tiene_otra_activa_da_409(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    activa = await make_rule(session)
    inactiva = await make_rule(session, template_id=activa.template_id, is_active=False)
    with pytest.raises(DuplicateActiveRule):
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_rule(session, inactiva.id, RulePatch(is_active=True)),
        )
    await session.rollback()


async def test_desactivar_y_luego_activar_otra_con_la_misma_clave_es_posible(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    primera = await make_rule(session)
    segunda = await make_rule(session, template_id=primera.template_id, is_active=False)
    await en_peticion(
        session,
        admin.id,
        lambda: service.update_rule(session, primera.id, RulePatch(is_active=False)),
    )
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.update_rule(session, segunda.id, RulePatch(is_active=True)),
    )
    assert salida.is_active is True


async def test_update_rule_no_choca_consigo_misma(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session)
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.update_rule(
            session, base.id, RulePatch(offset_days=-3, channel="whatsapp_link", name="Nuevo")
        ),
    )
    assert salida.name == "Nuevo"


async def test_update_rule_inexistente_da_404(session: AsyncSession, admin: UsuarioPrueba) -> None:
    with pytest.raises(RuleNotFound) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_rule(session, uuid4(), RulePatch(name="X")),
        )
    assert (capturado.value.status, capturado.value.code) == (404, "rule_not_found")


# Carrera ----------------------------------------------------------------------------------------


async def test_dos_altas_activas_iguales_a_la_vez_dejan_una_y_la_otra_recibe_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    plantilla = await make_template(primera)

    async def alta(sesion: AsyncSession, nombre: str) -> RuleOut | DuplicateActiveRule:
        with actor_scope(SYSTEM_USER_ID):
            try:
                salida = await service.create_rule(sesion, regla_in(plantilla.id, name=nombre))
                await sesion.commit()
                return salida
            except DuplicateActiveRule as error:
                await sesion.rollback()
                return error

    resultados = await asyncio.gather(alta(primera, "A"), alta(segunda, "B"))
    creadas = [r for r in resultados if isinstance(r, RuleOut)]
    perdedoras = [r for r in resultados if isinstance(r, DuplicateActiveRule)]
    assert len(creadas) == 1 and len(perdedoras) == 1
    total = await primera.scalar(select(func.count()).select_from(NotificationRule))
    assert total == 1


# get_rule y list_rules --------------------------------------------------------------------------


async def test_get_rule_devuelve_la_regla_o_404(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_rule(session, name="Vence en 3 días")
    assert (await service.get_rule(session, base.id)).name == "Vence en 3 días"
    with pytest.raises(RuleNotFound):
        await service.get_rule(session, uuid4())


async def _sembrar_cuatro(session: AsyncSession) -> None:
    plantilla = await make_template(session)
    await make_rule(session, plantilla, name="Vence hoy", offset_days=0)
    await make_rule(session, plantilla, name="Vence en 3 días", offset_days=-3)
    await make_rule(
        session, plantilla, name="Venció hace 1 día", trigger="membership_expired", offset_days=1
    )
    await make_rule(
        session,
        plantilla,
        name="Venció por correo",
        trigger="membership_expired",
        offset_days=7,
        channel="email",
        is_active=False,
    )


async def test_list_rules_ordena_por_desfase(session: AsyncSession, admin: UsuarioPrueba) -> None:
    await _sembrar_cuatro(session)
    pagina = await service.list_rules(session, RuleFilters(), PageParams())
    assert pagina.total == 4
    assert [r.offset_days for r in pagina.items] == [-3, 0, 1, 7]


@pytest.mark.parametrize(
    ("filtros", "nombres"),
    [
        (RuleFilters(is_active=False), ["Venció por correo"]),
        (RuleFilters(is_active=True), ["Vence en 3 días", "Vence hoy", "Venció hace 1 día"]),
        (RuleFilters(channel="email"), ["Venció por correo"]),
        (RuleFilters(trigger="membership_expiring"), ["Vence en 3 días", "Vence hoy"]),
        (RuleFilters(q="VENCIO"), ["Venció hace 1 día", "Venció por correo"]),
        (RuleFilters(q="hoy", is_active=True), ["Vence hoy"]),
        (RuleFilters(q="%"), []),
    ],
)
async def test_list_rules_aplica_los_filtros(
    session: AsyncSession,
    admin: UsuarioPrueba,
    filtros: RuleFilters,
    nombres: list[str],
) -> None:
    await _sembrar_cuatro(session)
    pagina = await service.list_rules(session, filtros, PageParams())
    assert [r.name for r in pagina.items] == nombres
    assert pagina.total == len(nombres)


async def test_list_rules_pagina(session: AsyncSession, admin: UsuarioPrueba) -> None:
    await _sembrar_cuatro(session)
    pagina = await service.list_rules(session, RuleFilters(), PageParams(limit=2, offset=1))
    assert (pagina.total, pagina.limit, pagina.offset) == (4, 2, 1)
    assert [r.offset_days for r in pagina.items] == [0, 1]
