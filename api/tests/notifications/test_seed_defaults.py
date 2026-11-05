"""`notifications.service.seed_defaults` (S5-B6, US-120 y US-121; S5-D25, S5-D34). # Rojo B6

- Primera corrida: las plantillas "Vence pronto" y "Venció" y las cinco reglas (`-3` y `0`
  `membership_expiring`; `1`, `7` y `15` `membership_expired`), todas `whatsapp_link`, activas y
  con la plantilla que corresponde; `SeedResult(2, 5)`.
- Los textos sembrados usan solo variables válidas.
- Idempotente: la segunda corrida da `SeedResult(0, 0)`, no cambia ninguna fila y no audita.
- Respeta lo que el admin ya tocó: una plantilla editada no se pisa, una regla desactivada no se
  reactiva ni se duplica, una regla activa con la misma clave y otro nombre cuenta como existente.
- Auditada: un `insert` por fila a nombre del actor (7 en total).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.notifications import service
from app.modules.notifications.rules import validate_template_vars
from app.modules.notifications.schemas import SeedResult
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.notifications import (
    CHANNEL,
    DEFAULT_RULES,
    DEFAULT_TEMPLATES,
    EXPIRED,
    SOON,
    make_rule,
    make_template,
)
from tests.notifications._apoyo import (
    T_PLANTILLAS,
    T_REGLAS,
    contar,
    en_peticion,
    filas_de_auditoria,
)


@pytest.fixture
async def admin(usuario_real: CrearUsuario, reloj: FrozenClock) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _reglas(session: AsyncSession) -> list[tuple[str, int, str, str, bool]]:
    consulta = text(
        "SELECT r.trigger, r.offset_days, r.channel, t.name AS plantilla, r.is_active "
        "FROM notifications.notification_rules r "
        "JOIN notifications.notification_templates t ON t.id = r.template_id "
        "ORDER BY r.offset_days"
    )
    return [
        (f["trigger"], f["offset_days"], f["channel"], f["plantilla"], f["is_active"])
        for f in (await session.execute(consulta)).mappings()
    ]


async def _sembrar(session: AsyncSession, actor: UsuarioPrueba) -> SeedResult:
    return await en_peticion(session, actor.id, lambda: service.seed_defaults(session))


async def test_la_primera_corrida_crea_dos_plantillas_y_cinco_reglas(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    resultado = await _sembrar(session, admin)
    assert resultado == SeedResult(templates_created=2, rules_created=5)
    nombres = (await session.execute(text(f"SELECT name FROM {T_PLANTILLAS}"))).scalars().all()  # noqa: S608
    assert sorted(nombres) == sorted([SOON, EXPIRED])
    esperadas = [(d.trigger, d.offset_days, CHANNEL, d.template, True) for d in DEFAULT_RULES]
    assert await _reglas(session) == sorted(esperadas, key=lambda r: r[1])


async def test_los_textos_sembrados_solo_usan_variables_validas(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await _sembrar(session, admin)
    filas = (
        await session.execute(text(f"SELECT name, subject, body FROM {T_PLANTILLAS}"))  # noqa: S608
    ).mappings()
    for f in filas:
        validate_template_vars(f["subject"], "subject")
        validate_template_vars(f["body"], "body")
        assert "{nombre}" in f["body"] and f["subject"].strip() and f["body"].strip()
    assert {f for f in DEFAULT_TEMPLATES} == {SOON, EXPIRED}


async def test_la_segunda_corrida_no_crea_ni_cambia_nada(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await _sembrar(session, admin)
    antes = (
        await session.execute(
            text(f"SELECT id, updated_at FROM {T_PLANTILLAS} ORDER BY id")  # noqa: S608
        )
    ).all()
    auditoria = len(await filas_de_auditoria(session, T_REGLAS))
    resultado = await _sembrar(session, admin)
    assert resultado == SeedResult(templates_created=0, rules_created=0)
    assert await contar(session, T_PLANTILLAS) == 2 and await contar(session, T_REGLAS) == 5
    despues = (
        await session.execute(
            text(f"SELECT id, updated_at FROM {T_PLANTILLAS} ORDER BY id")  # noqa: S608
        )
    ).all()
    assert despues == antes
    assert len(await filas_de_auditoria(session, T_REGLAS)) == auditoria


async def test_la_siembra_queda_auditada_con_un_insert_por_fila_a_nombre_del_actor(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await _sembrar(session, admin)
    assert await filas_de_auditoria(session, T_PLANTILLAS) == [("insert", admin.id)] * 2
    assert await filas_de_auditoria(session, T_REGLAS) == [("insert", admin.id)] * 5


async def test_una_plantilla_editada_por_el_admin_no_se_pisa(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    editada = await make_template(
        session, name=SOON, subject="Mi asunto", body="Mi cuerpo {nombre}"
    )
    resultado = await _sembrar(session, admin)
    assert resultado == SeedResult(templates_created=1, rules_created=5)
    fila = (
        (
            await session.execute(
                text(f"SELECT subject, body FROM {T_PLANTILLAS} WHERE id = :i"),  # noqa: S608
                {"i": editada.id},
            )
        )
        .mappings()
        .one()
    )
    assert (fila["subject"], fila["body"]) == ("Mi asunto", "Mi cuerpo {nombre}")
    reglas_a_la_editada = await session.scalar(
        text(f"SELECT count(*) FROM {T_REGLAS} WHERE template_id = :i"),  # noqa: S608
        {"i": editada.id},
    )
    assert reglas_a_la_editada == 2


async def test_una_regla_desactivada_no_se_reactiva_ni_se_duplica(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await _sembrar(session, admin)
    await session.execute(
        text(f"UPDATE {T_REGLAS} SET is_active = false WHERE offset_days = 7")  # noqa: S608
    )
    resultado = await _sembrar(session, admin)
    assert resultado == SeedResult(templates_created=0, rules_created=0)
    assert await contar(session, T_REGLAS) == 5
    activas = await session.scalar(
        text(f"SELECT count(*) FROM {T_REGLAS} WHERE offset_days = 7 AND is_active")  # noqa: S608
    )
    assert activas == 0


async def test_una_regla_activa_con_la_misma_clave_y_otro_nombre_cuenta_como_existente(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await make_rule(session, name="Mi aviso propio", trigger="membership_expiring", offset_days=-3)
    resultado = await _sembrar(session, admin)
    assert resultado.rules_created == 4
    assert await contar(session, T_REGLAS) == 5
    clave = await session.scalar(
        text(
            f"SELECT count(*) FROM {T_REGLAS} "  # noqa: S608
            "WHERE trigger = 'membership_expiring' AND offset_days = -3 AND is_active"
        )
    )
    assert clave == 1


async def test_dos_siembras_concurrentes_crean_una_sola_vez(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """S5-D215: el candado asesor serializa la siembra; la segunda espera y no crea nada."""
    primera, segunda = dos_sesiones

    async def sembrar(sesion: AsyncSession) -> SeedResult:
        with actor_scope(SYSTEM_USER_ID):
            try:
                resultado = await service.seed_defaults(sesion)
                await sesion.commit()
                return resultado
            except BaseException:
                await sesion.rollback()
                raise

    resultados = await asyncio.gather(sembrar(primera), sembrar(segunda))
    assert sorted((r.templates_created, r.rules_created) for r in resultados) == [(0, 0), (2, 5)]
    assert await contar(primera, T_PLANTILLAS) == 2 and await contar(primera, T_REGLAS) == 5


async def test_un_choque_residual_de_integridad_se_traduce_a_un_error_de_dominio(
    session: AsyncSession, admin: UsuarioPrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5-D215: si algo se cuela pese al candado, el mensaje es fijo y reintentable."""
    from sqlalchemy.exc import IntegrityError

    from app.modules.notifications.exceptions import SeedInProgress

    original = session.flush

    async def flush_roto(*args: object, **kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicada"))

    monkeypatch.setattr(session, "flush", flush_roto)
    with pytest.raises(SeedInProgress) as capturado:
        await en_peticion(session, admin.id, lambda: service.seed_defaults(session))
    assert capturado.value.message == "siembra en curso por otro proceso; reintente"
    assert (capturado.value.status, capturado.value.code) == (409, "seed_in_progress")
    monkeypatch.setattr(session, "flush", original)
    await session.rollback()
