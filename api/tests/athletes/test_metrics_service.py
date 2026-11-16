"""`athletes.service.add_metric` y `list_metrics` con PostgreSQL real (S9-A1, US-178). Rojo A1.

- Las cuatro columnas guardan un blob `apx1.` con `aad = id` y el claro de ancho fijo con marca de
  campo (S9-D4, S9-D32); hay cuatro filas `encrypt` de `athlete.metric` con el id de la medición.
- La auditoría guarda el blob, nunca el valor; la lista no descifra (cero filas nuevas en
  `crypto_ops`).
- Todos los blobs de un campo miden lo mismo (62.500 y 100.000 g; notas de 5 y de 100 caracteres).
- Socio dado de baja: 404 al escribir y la lista se lee. Sin autorización de datos: 409
  `consent_required` y cero filas `encrypt` (H-1, S9-D29).
- M-2: el blob de `weight_g` copiado a las otras tres columnas de la misma fila no revela nada.
- L-2: la puerta `_decrypt_metric_field` rechaza un campo fuera de la tupla, otro `purpose` y una
  fila anulada.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.crypto import bus
from app.core.pagination import PageParams
from app.modules.athletes import metrics, service
from app.modules.athletes.exceptions import ConsentRequired, MetricValidationError, MetricVoided
from app.modules.athletes.models import BodyMetric
from app.modules.athletes.rules import MetricDecodeError
from app.modules.members.exceptions import MemberNotFound
from tests.athletes._apoyo import (
    CLASE,
    ENCRIPTADAS,
    alta,
    auditoria_de,
    claros_en,
    encripts_de_la_clase,
    fila_cruda,
    ops_de,
)
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_metric
from tests.factories.triggers import disable_user_sql
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

PAGINA = PageParams(limit=25, offset=0)


@pytest.fixture
async def coach(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach")


# Alta ----------------------------------------------------------------------------------------


async def test_el_alta_guarda_un_blob_apx1_en_las_cuatro_columnas(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)

    fila = await fila_cruda(session, salida.id)
    assert (fila["member_id"], fila["recorded_by"], fila["created_by"]) == (
        miembro.id,
        coach.id,
        coach.id,
    )
    assert fila["measured_on"] == date(2026, 10, 20)
    assert (fila["voided_at"], fila["voided_by"]) == (None, None)
    for campo in ENCRIPTADAS:
        assert fila[campo].startswith("apx1."), campo
        assert fila[campo].split(".")[2] == "A256GCM"
    assert claros_en(fila, ("62500", "062500", "165", "22", "Primera")) == []


async def test_el_claro_cifrado_es_el_de_ancho_fijo_con_marca_y_aad_es_el_id(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id, notes="abcde")

    fila = await fila_cruda(session, salida.id)
    aad = bus.aad_for(salida.id)
    assert bus.decrypt(fila["weight_g"], aad).decode("utf-8") == "w062500"
    assert bus.decrypt(fila["height_cm"], aad).decode("utf-8") == "h165"
    assert bus.decrypt(fila["body_fat_pct"], aad).decode("utf-8") == "f22"
    assert bus.decrypt(fila["notes"], aad).decode("utf-8") == "n0005abcde" + " " * 118
    with pytest.raises(Exception, match=r"."):
        bus.decrypt(fila["weight_g"], bus.aad_for(uuid4()))


async def test_hay_cuatro_filas_encrypt_de_la_clase_con_el_id_de_la_medicion(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    antes = await encripts_de_la_clase(session)
    salida = await alta(session, coach.id, miembro.id)

    filas = await ops_de(session, salida.id, "encrypt")
    assert len(filas) == 4
    assert {f["data_class"] for f in filas} == {CLASE}
    assert {f["user_id"] for f in filas} == {coach.id}
    assert await encripts_de_la_clase(session) == antes + 4
    assert await ops_de(session, salida.id, "decrypt") == []


async def test_una_medicion_con_un_solo_campo_cifra_solo_ese_campo(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(
        session, coach.id, miembro.id, height_cm=170, weight_g=None, body_fat_pct=None, notes=None
    )

    fila = await fila_cruda(session, salida.id)
    assert fila["height_cm"].startswith("apx1.")
    assert (fila["weight_g"], fila["body_fat_pct"], fila["notes"]) == (None, None, None)
    assert len(await ops_de(session, salida.id, "encrypt")) == 1
    assert (salida.has_weight, salida.has_height, salida.has_body_fat, salida.has_notes) == (
        False,
        True,
        False,
        False,
    )


async def test_la_salida_trae_las_marcas_has_y_nunca_el_valor(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)

    assert (salida.has_weight, salida.has_height, salida.has_body_fat, salida.has_notes) == (
        True,
        True,
        True,
        True,
    )
    assert salida.recorded_by == coach.id and salida.voided_at is None
    assert set(type(salida).model_fields) == {
        "id",
        "measured_on",
        "has_weight",
        "has_height",
        "has_body_fat",
        "has_notes",
        "recorded_by",
        "recorded_by_name",
        "voided_at",
        "created_at",
    }


async def test_la_auditoria_guarda_el_blob_y_el_sujeto_nunca_el_valor(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)

    filas = await auditoria_de(session, salida.id)
    assert [f["action"] for f in filas] == ["insert"]
    (fila,) = filas
    assert (fila["user_id"], fila["subject_member_id"]) == (coach.id, miembro.id)
    for campo in ENCRIPTADAS:
        assert fila["after"][campo].startswith("apx1."), campo
    # Solo se buscan los valores que no son blobs (un blob base64 puede llevar "165" por azar).
    assert claros_en(fila["after"], ("62500", "062500", "165", "22", "Primera")) == []
    assert fila["before"] is None


async def test_todos_los_blobs_de_un_campo_miden_lo_mismo(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    una = await alta(session, coach.id, miembro.id, weight_g=62_500, notes="a" * 5)
    otra = await alta(session, coach.id, miembro.id, weight_g=100_000, notes="b" * 100)

    f1, f2 = await fila_cruda(session, una.id), await fila_cruda(session, otra.id)
    assert len(f1["weight_g"]) == len(f2["weight_g"])
    assert len(f1["notes"]) == len(f2["notes"])
    assert f1["weight_g"] != f2["weight_g"]


async def test_un_valor_invalido_no_deja_fila_ni_operaciones(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    antes = await encripts_de_la_clase(session)

    with pytest.raises(MetricValidationError) as excepcion:
        await alta(session, coach.id, miembro.id, weight_g=19_999)

    assert excepcion.value.field == "weight_g"
    total = await session.scalar(text("SELECT count(*) FROM athletes.body_metrics"))
    assert total == 0
    assert await encripts_de_la_clase(session) == antes


# Socio inexistente, dado de baja y sin autorización -------------------------------------------


async def test_un_socio_inexistente_da_member_not_found(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    with pytest.raises(MemberNotFound):
        await alta(session, coach.id, uuid4())


async def test_un_socio_dado_de_baja_no_admite_altas_pero_su_lista_se_lee(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    existente = await alta(session, coach.id, miembro.id)
    # Se da de baja después del alta (S9-D14: las lecturas incluyen a los dados de baja).
    await session.execute(
        text("UPDATE members.members SET deleted_at = :t, status = 'inactive' WHERE id = :i"),
        {"t": ANTES, "i": miembro.id},
    )

    with pytest.raises(MemberNotFound):
        await alta(session, coach.id, miembro.id)
    pagina = await service.list_metrics(session, miembro.id, PAGINA)
    assert [m.id for m in pagina.items] == [existente.id]


async def test_la_lista_de_un_socio_inexistente_da_member_not_found(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound):
        await service.list_metrics(session, uuid4(), PAGINA)


async def test_sin_autorizacion_de_datos_da_consent_required_y_cero_filas_encrypt(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    """H-1 (S9-D29): el 409 sale ANTES de codificar y cifrar."""
    miembro = await socio(session, consentido=False)
    antes = await encripts_de_la_clase(session)

    with pytest.raises(ConsentRequired) as excepcion:
        await alta(session, coach.id, miembro.id)

    assert (excepcion.value.status, excepcion.value.code) == (409, "consent_required")
    assert await encripts_de_la_clase(session) == antes
    assert await session.scalar(text("SELECT count(*) FROM athletes.body_metrics")) == 0


async def test_la_lista_y_las_medidas_ya_guardadas_no_dependen_de_la_autorizacion_actual(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    existente = await alta(session, coach.id, miembro.id)
    await session.execute(
        text("UPDATE members.members SET data_consent_at = NULL WHERE id = :i"), {"i": miembro.id}
    )

    pagina = await service.list_metrics(session, miembro.id, PAGINA)
    assert [m.id for m in pagina.items] == [existente.id]


async def test_el_alta_toma_el_candado_del_socio_antes_de_comprobar_que_existe(
    session: AsyncSession, coach: UsuarioPrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-A de la revisión de A1: sin el candado, una baja simultánea deja una medición en un socio
    dado de baja. Orden único de candados: `lock_member` primero (`core/locks.py`)."""
    from app.modules.members import service as members_service

    miembro = await socio(session, consentido=True)
    orden: list[str] = []
    real_lock, real_exists = metrics.lock_member, members_service.ensure_exists

    async def lock(sesion: AsyncSession, member_id: Any) -> None:
        orden.append("lock")
        assert member_id == miembro_id
        await real_lock(sesion, member_id)

    async def existe(sesion: AsyncSession, member_id: Any, **kw: Any) -> None:
        orden.append("existe")
        await real_exists(sesion, member_id, **kw)

    miembro_id = miembro.id
    monkeypatch.setattr(metrics, "lock_member", lock)
    monkeypatch.setattr(members_service, "ensure_exists", existe)

    await alta(session, coach.id, miembro_id)

    assert orden == ["lock", "existe"]


# Lista ---------------------------------------------------------------------------------------


async def test_la_lista_no_descifra_ni_agrega_operaciones(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    await alta(session, coach.id, miembro.id)
    total_antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))

    session.expunge_all()
    pagina = await service.list_metrics(session, miembro.id, PAGINA)
    await session.commit()

    assert pagina.total == 1
    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == total_antes


async def test_la_lista_ordena_por_fecha_descendente_y_pagina(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    vieja = await alta(session, coach.id, miembro.id, measured_on="2026-09-01")
    nueva = await alta(session, coach.id, miembro.id, measured_on="2026-10-15")

    pagina = await service.list_metrics(session, miembro.id, PAGINA)
    assert [m.id for m in pagina.items] == [nueva.id, vieja.id]
    assert (pagina.total, pagina.limit, pagina.offset) == (2, 25, 0)
    segunda = await service.list_metrics(session, miembro.id, PageParams(limit=1, offset=1))
    assert [m.id for m in segunda.items] == [vieja.id] and segunda.total == 2


async def test_la_lista_solo_trae_las_del_socio_y_oculta_las_anuladas_por_defecto(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    otro = await socio(session, consentido=True)
    viva = await alta(session, coach.id, miembro.id)
    anulada = await make_metric(session, miembro.id, voided=True)
    await alta(session, coach.id, otro.id)

    por_defecto = await service.list_metrics(session, miembro.id, PAGINA)
    assert [m.id for m in por_defecto.items] == [viva.id]
    todas = await service.list_metrics(session, miembro.id, PAGINA, include_voided=True)
    assert {m.id for m in todas.items} == {viva.id, anulada.id}
    marcada = next(m for m in todas.items if m.id == anulada.id)
    assert marcada.voided_at is not None


# M-2 y la puerta de descifrado ----------------------------------------------------------------


async def _fila_orm(session: AsyncSession, metric_id: Any) -> BodyMetric:
    session.expunge_all()
    return (await session.scalars(select(BodyMetric).where(BodyMetric.id == metric_id))).one()


async def test_la_puerta_devuelve_el_valor_de_cada_campo_y_deja_rastro_decrypt(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)

    fila = await _fila_orm(session, salida.id)
    with actor_scope(coach.id):  # las filas `decrypt` de `crypto_ops` salen al confirmar
        assert metrics._decrypt_metric_field(fila, "weight_g", "reveal") == 62_500
        assert metrics._decrypt_metric_field(fila, "height_cm", "reveal") == 165
        assert metrics._decrypt_metric_field(fila, "body_fat_pct", "reveal") == 22
        assert metrics._decrypt_metric_field(fila, "notes", "reveal") == "Primera medición del año"
        await session.commit()
    filas = await ops_de(session, salida.id, "decrypt")
    assert len(filas) == 4 and {f["purpose"] for f in filas} == {"reveal"}


@pytest.mark.parametrize("copiado_a", ["height_cm", "body_fat_pct", "notes"])
async def test_un_blob_de_peso_copiado_a_otra_columna_de_la_misma_fila_no_revela_nada(
    session: AsyncSession, coach: UsuarioPrueba, copiado_a: str
) -> None:
    """M-2: mismo id, misma llave y mismo AAD: el blob abre, pero la marca de campo lo delata."""
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)
    await session.execute(text(disable_user_sql("athletes.body_metrics")))
    await session.execute(
        text(f"UPDATE athletes.body_metrics SET {copiado_a} = weight_g WHERE id = :i"),  # noqa: S608
        {"i": salida.id},
    )

    fila = await _fila_orm(session, salida.id)
    with pytest.raises(MetricDecodeError) as excepcion:
        metrics._decrypt_metric_field(fila, copiado_a, "reveal")
    assert "62500" not in str(excepcion.value) and "062500" not in str(excepcion.value)


@pytest.mark.parametrize("campo", ["member_id", "id", "measured_on", "voided_by", "", "WEIGHT_G"])
async def test_la_puerta_rechaza_un_campo_fuera_de_la_tupla_de_cuatro(
    session: AsyncSession, coach: UsuarioPrueba, campo: str
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)
    fila = await _fila_orm(session, salida.id)
    antes = len(await ops_de(session, salida.id, "decrypt"))

    with pytest.raises(ValueError, match="campo"):
        metrics._decrypt_metric_field(fila, campo, "reveal")  # type: ignore[arg-type]

    await session.commit()
    assert len(await ops_de(session, salida.id, "decrypt")) == antes


@pytest.mark.parametrize("proposito", ["mask", "export", "", "REVEAL"])
async def test_la_puerta_rechaza_otro_purpose(
    session: AsyncSession, coach: UsuarioPrueba, proposito: str
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)
    fila = await _fila_orm(session, salida.id)

    with pytest.raises(ValueError, match="purpose"):
        metrics._decrypt_metric_field(fila, "weight_g", proposito)  # type: ignore[arg-type]
    assert await ops_de(session, salida.id, "decrypt") == []


async def test_la_puerta_rechaza_una_fila_anulada_sin_descifrar(session: AsyncSession) -> None:
    anulada = await make_metric(session, voided=True)
    fila = await _fila_orm(session, anulada.id)

    with pytest.raises(MetricVoided) as excepcion:
        metrics._decrypt_metric_field(fila, "weight_g", "reveal")

    assert (excepcion.value.status, excepcion.value.code) == (409, "metric_voided")
    await session.commit()
    assert await ops_de(session, anulada.id, "decrypt") == []


async def test_la_puerta_rechaza_un_objeto_que_no_es_una_medicion(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    """L-D: `isinstance(metric, BodyMetric)` ANTES de todo; un `Member` (que también tiene columnas
    cifradas) no pasa por la puerta de las medidas."""
    from tests.factories.members import make_member

    ajeno = await make_member(session)
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))

    with pytest.raises(TypeError):
        metrics._decrypt_metric_field(ajeno, "weight_g", "reveal")  # type: ignore[arg-type]

    await session.commit()
    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == antes


async def test_la_puerta_acepta_un_solo_campo_por_llamada(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=True)
    salida = await alta(session, coach.id, miembro.id)
    fila = await _fila_orm(session, salida.id)

    for pedido in (("weight_g", "height_cm"), ["weight_g"], {"weight_g"}):
        with pytest.raises((ValueError, TypeError)):
            metrics._decrypt_metric_field(fila, pedido, "reveal")  # type: ignore[arg-type]
