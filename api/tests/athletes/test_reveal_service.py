"""`athletes.service.reveal_metric` con PostgreSQL real (S9-A2, US-179; S9-D15, S9-D34; M-4, L-2).

- Devuelve el valor en claro de UN campo (`int` en peso, estatura y grasa; `str` en notas) y deja,
  en la misma transacción, una fila `reveal` de la auditoría con `after = {"field", "ip"}` (nunca
  el valor) y una fila `decrypt` de `crypto_ops` con `purpose = reveal` y `record_id` = la medición.
- Campo vacío: `value = None`, la fila `reveal` SÍ y la `decrypt` NO (sondear campos deja rastro).
- Medición de otro socio o inexistente: 404 `metric_not_found` sin ninguna fila; socio inexistente:
  `member_not_found`; medición anulada: 409 `metric_voided` sin ninguna fila.
- La anulación se relee DENTRO de la transacción (una copia vieja en la sesión no engaña) y la
  fila se bloquea con `FOR SHARE` para que una anulación concurrente no se cuele.
- M-4: de un socio dado de baja solo revela el admin; el coach recibe 403 `forbidden` sin fila
  `decrypt` ni `reveal`.
- L-2: un blob que no decodifica sale como `MetricDecodeError` opaco (el router lo vuelve 500
  `internal_error`), sin fila `reveal`, y su texto no lleva el valor.
- Ningún valor revelado llega a los registros del módulo.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import actor_scope
from app.core.errors import ForbiddenError
from app.modules.athletes import metrics, service
from app.modules.athletes.exceptions import MetricNotFound, MetricVoided
from app.modules.athletes.models import BodyMetric
from app.modules.athletes.rules import MetricDecodeError
from app.modules.members.exceptions import MemberNotFound
from tests.athletes._apoyo import (
    CLASE,
    IP,
    TABLA,
    alta,
    auditoria_de,
    ops_de,
    reveals_de,
    revelar,
)
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_metric
from tests.factories.triggers import disable_user_sql
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

# Valores del alta por omisión de `_apoyo.cuerpo` (derivados a mano): 62.500 g, 165 cm, 22 % y el
# texto de las notas.
VALORES = {
    "weight_g": 62_500,
    "height_cm": 165,
    "body_fat_pct": 22,
    "notes": "Primera medición del año",
}


@pytest.fixture
async def coach(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach")


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


# Valor y rastro ------------------------------------------------------------------------------


@pytest.mark.parametrize(("campo", "esperado"), list(VALORES.items()))
async def test_devuelve_el_valor_de_cada_campo_con_su_tipo(
    campo: str, esperado: int | str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)

    salida = await revelar(session, coach.id, miembro.id, medicion.id, campo)

    assert salida.field == campo
    assert salida.value == esperado
    assert type(salida.value) is type(esperado)


async def test_deja_una_fila_reveal_con_field_e_ip_y_sin_el_valor(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)

    await revelar(session, coach.id, miembro.id, medicion.id, "weight_g")

    (fila,) = await reveals_de(session, medicion.id)
    assert fila["user_id"] == coach.id
    assert fila["table_name"] == TABLA
    assert fila["subject_member_id"] == miembro.id
    assert fila["before"] is None
    assert fila["after"] == {"field": "weight_g", "ip": IP}
    volcado = str(fila)
    for claro in ("62500", "062500", "w062500", "Primera", "apx1."):
        assert claro not in volcado, claro


async def test_deja_una_fila_decrypt_con_el_id_de_la_medicion(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)

    await revelar(session, coach.id, miembro.id, medicion.id, "height_cm")

    (fila,) = await ops_de(session, medicion.id, "decrypt")
    assert (fila["record_id"], fila["purpose"], fila["data_class"]) == (
        medicion.id,
        "reveal",
        CLASE,
    )


async def test_un_campo_vacio_da_none_deja_reveal_y_no_deja_decrypt(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(
        session, coach.id, miembro.id, height_cm=None, body_fat_pct=None, notes=None
    )

    salida = await revelar(session, coach.id, miembro.id, medicion.id, "height_cm")

    assert (salida.field, salida.value) == ("height_cm", None)
    assert len(await reveals_de(session, medicion.id)) == 1
    assert await ops_de(session, medicion.id, "decrypt") == []


async def test_cada_peticion_suma_su_propia_fila_reveal(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)

    await revelar(session, coach.id, miembro.id, medicion.id, "weight_g")
    await revelar(session, coach.id, miembro.id, medicion.id, "notes")

    campos = [f["after"]["field"] for f in await reveals_de(session, medicion.id)]
    assert campos == ["weight_g", "notes"]
    assert len(await ops_de(session, medicion.id, "decrypt")) == 2


# Existencia ----------------------------------------------------------------------------------


async def test_una_medicion_de_otro_socio_da_404_sin_ninguna_fila(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    dueno = await socio(session, consentido=True)
    ajeno = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, dueno.id)

    with pytest.raises(MetricNotFound):
        await revelar(session, coach.id, ajeno.id, medicion.id, "weight_g")

    assert await reveals_de(session, medicion.id) == []
    assert await ops_de(session, medicion.id, "decrypt") == []


async def test_una_medicion_inexistente_da_404_sin_ninguna_fila(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    inexistente = uuid4()

    with pytest.raises(MetricNotFound):
        await revelar(session, coach.id, miembro.id, inexistente, "weight_g")

    assert await reveals_de(session, inexistente) == []
    assert await ops_de(session, inexistente, "decrypt") == []


async def test_un_socio_inexistente_da_member_not_found_sin_filas(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)

    with pytest.raises(MemberNotFound):
        await revelar(session, coach.id, uuid4(), medicion.id, "weight_g")

    assert await reveals_de(session, medicion.id) == []
    assert await ops_de(session, medicion.id, "decrypt") == []


# Anulada y relectura -------------------------------------------------------------------------


async def test_una_medicion_anulada_da_409_sin_ninguna_fila(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await make_metric(session, miembro.id, voided=True)
    metric_id, member_id = medicion.id, miembro.id

    with pytest.raises(MetricVoided):
        await revelar(session, coach.id, member_id, metric_id, "weight_g")

    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []


async def test_la_anulacion_se_relee_dentro_de_la_transaccion(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    """Una copia ORM vieja (sin `voided_at`) en la sesión no engaña: se relee con la fila real."""
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    session.expunge_all()
    vieja = await session.get(BodyMetric, metric_id)
    assert vieja is not None and vieja.voided_at is None
    await session.execute(
        text("UPDATE athletes.body_metrics SET voided_at = now(), voided_by = :a WHERE id = :i"),
        {"a": coach.id, "i": metric_id},
    )

    with actor_scope(coach.id), pytest.raises(MetricVoided):
        await service.reveal_metric(session, member_id, metric_id, "weight_g", ip=IP, role="coach")

    await session.rollback()
    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []


async def test_la_fila_se_lee_con_for_share_para_que_una_anulacion_no_se_cuele(
    session: AsyncSession, engine: AsyncEngine, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)
    sentencias: list[str] = []

    def espiar(conn: Any, cursor: Any, statement: str, *resto: Any) -> None:
        sentencias.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", espiar)
    try:
        await revelar(session, coach.id, miembro.id, medicion.id, "weight_g")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", espiar)

    lecturas = [
        s for s in sentencias if "athletes.body_metrics" in s and s.lstrip().startswith("SELECT")
    ]
    assert lecturas, sentencias
    assert any("FOR SHARE" in s for s in lecturas), lecturas


# M-4: socio dado de baja ---------------------------------------------------------------------


async def test_de_un_socio_dado_de_baja_el_admin_revela(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    medicion = await make_metric(session, baja.id)
    member_id, metric_id = baja.id, medicion.id

    salida = await revelar(session, admin.id, member_id, metric_id, "weight_g", role="admin")

    assert salida.value == 62_500
    assert len(await reveals_de(session, metric_id)) == 1
    assert len(await ops_de(session, metric_id, "decrypt")) == 1


async def test_de_un_socio_dado_de_baja_el_coach_recibe_403_sin_fila_decrypt(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    medicion = await make_metric(session, baja.id)
    member_id, metric_id = baja.id, medicion.id

    with pytest.raises(ForbiddenError):
        await revelar(session, coach.id, member_id, metric_id, "weight_g", role="coach")

    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []


async def test_de_un_socio_vivo_lo_revela_el_coach(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await make_metric(session, miembro.id)
    member_id, metric_id = miembro.id, medicion.id

    salida = await revelar(session, coach.id, member_id, metric_id, "height_cm", role="coach")

    assert salida.value == 165


# L-2: blob que no decodifica -----------------------------------------------------------------


async def test_un_blob_que_no_decodifica_da_error_opaco_sin_fila_reveal(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    await session.execute(text(disable_user_sql("athletes.body_metrics")))
    await session.execute(
        text("UPDATE athletes.body_metrics SET height_cm = weight_g WHERE id = :i"),
        {"i": metric_id},
    )

    with pytest.raises(MetricDecodeError) as excepcion:
        await revelar(session, coach.id, member_id, metric_id, "height_cm")

    assert "62500" not in str(excepcion.value) and "062500" not in str(excepcion.value)
    assert await reveals_de(session, metric_id) == []


# Registros -----------------------------------------------------------------------------------


async def test_el_valor_no_esta_en_los_registros(
    session: AsyncSession, coach: UsuarioPrueba, caplog: pytest.LogCaptureFixture
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id, weight_g=73_417, notes="Nota privada")
    caplog.set_level(logging.DEBUG)

    for campo in ("weight_g", "notes"):
        await revelar(session, coach.id, miembro.id, medicion.id, campo)

    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    for claro in ("73417", "073417", "Nota privada", "apx1."):
        assert claro not in texto, claro


async def test_la_auditoria_de_la_medicion_solo_suma_la_fila_reveal(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, coach.id, miembro.id)
    antes = len(await auditoria_de(session, medicion.id))

    await revelar(session, coach.id, miembro.id, medicion.id, "weight_g")

    assert len(await auditoria_de(session, medicion.id)) == antes + 1


# Revisión de seguridad de A2 (S9-D49): L-1 y L-2 ---------------------------------------------


async def test_el_reveal_toma_el_candado_del_socio_antes_de_leer_si_esta_de_baja(
    session: AsyncSession, coach: UsuarioPrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-1: sin el candado, una baja concurrente deja revelar una vez más al coach. Orden único de
    candados de `core/locks.py`: `lock_member` primero, como `add_metric`."""
    from app.modules.members import service as members_service

    miembro = await socio(session, consentido=True)
    medicion = await make_metric(session, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    orden: list[str] = []
    real_lock, real_ref = metrics.lock_member, members_service.get_ref

    async def lock(sesion: AsyncSession, mid: Any) -> None:
        orden.append("lock")
        assert mid == member_id
        await real_lock(sesion, mid)

    async def ref(sesion: AsyncSession, mid: Any) -> Any:
        orden.append("ref")
        return await real_ref(sesion, mid)

    monkeypatch.setattr(metrics, "lock_member", lock)
    monkeypatch.setattr(members_service, "get_ref", ref)

    await revelar(session, coach.id, member_id, metric_id, "weight_g")

    assert orden == ["lock", "ref"]


async def test_el_403_de_la_baja_deja_un_aviso_con_usuario_y_medicion_sin_valores(
    session: AsyncSession, coach: UsuarioPrueba, caplog: pytest.LogCaptureFixture
) -> None:
    """L-2: el 403 de M-4 no deja fila de auditoría; deja un `warning` de `app.athletes` con el
    usuario y la medición (S9-D35: el id de usuario va al log, no a la alerta), sin campo, valor,
    nombre ni id del socio."""
    baja = await socio(
        session, consentido=True, deleted_at=ANTES, status="inactive", nombre="Zulema"
    )
    medicion = await make_metric(session, baja.id)
    member_id, metric_id = baja.id, medicion.id
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ForbiddenError):
        await revelar(session, coach.id, member_id, metric_id, "weight_g", role="coach")

    avisos = [
        r for r in caplog.records if r.name == "app.athletes" and r.levelno == logging.WARNING
    ]
    assert len(avisos) == 1
    aviso = avisos[0]
    assert str(getattr(aviso, "user_id", None)) == str(coach.id)
    assert str(getattr(aviso, "metric_id", None)) == str(metric_id)
    volcado = aviso.getMessage() + str(aviso.__dict__)
    for ajeno in ("62500", "weight_g", "Zulema", str(member_id), "apx1."):
        assert ajeno not in volcado, ajeno
