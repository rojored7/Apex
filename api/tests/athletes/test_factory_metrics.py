"""La fábrica `make_metric` (S9-A1; hallazgo 6 de la crítica 1). Rojo A1.

La guarda de la base prohíbe nacer anulada y cambiar el claro de una medición, así que la fábrica
inserta por el ORM con blobs reales del bus y, si se pide anulada, hace después un `UPDATE` de
`voided_at` y `voided_by` (la rama permitida). Nunca apaga una guarda: las cuatro quedan en `'A'`.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.crypto import bus
from tests.athletes._apoyo import CLASE, ENCRIPTADAS, fila_cruda
from tests.factories import FACTORIES
from tests.factories.athletes import make_metric
from tests.factories.triggers import BODY_METRICS_TRIGGERS
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

ESTADO_TRIGGERS = text(
    "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
    "WHERE NOT tgisinternal AND tgname = ANY(:n)"
)


async def _llave_activa(session: AsyncSession) -> str:
    consulta = text(
        "SELECT id::text FROM crypto.crypto_keys WHERE purpose = 'encrypt' "
        "AND data_class = :c AND state = 'active'"
    )
    return str(await session.scalar(consulta, {"c": CLASE}))


def test_la_fabrica_esta_registrada_para_la_tabla() -> None:
    assert FACTORIES["athletes.body_metrics"] is make_metric


async def test_crea_una_medicion_viva_con_las_cuatro_columnas_cifradas_con_la_llave_activa(
    session: AsyncSession,
) -> None:
    miembro = await socio(session, consentido=True)

    medida = await make_metric(session, miembro.id)

    fila = await fila_cruda(session, medida.id)
    activa = await _llave_activa(session)
    assert fila["member_id"] == miembro.id
    assert (fila["voided_at"], fila["voided_by"]) == (None, None)
    for campo in ENCRIPTADAS:
        partes = fila[campo].split(".")
        assert partes[0] == "apx1" and partes[1] == activa and partes[2] == "A256GCM", campo
    aad = bus.aad_for(medida.id)
    assert bus.decrypt(fila["weight_g"], aad).decode("utf-8") == "w062500"
    assert bus.decrypt(fila["height_cm"], aad).decode("utf-8") == "h165"
    assert bus.decrypt(fila["body_fat_pct"], aad).decode("utf-8") == "f22"


async def test_crea_una_anulada_con_voided_at_y_voided_by_sin_apagar_ninguna_guarda(
    session: AsyncSession,
) -> None:
    miembro = await socio(session, consentido=True)
    quien = uuid4()

    medida = await make_metric(session, miembro.id, voided=True, actor=quien)

    fila = await fila_cruda(session, medida.id)
    assert fila["voided_at"] is not None and fila["voided_by"] == quien
    assert fila["created_by"] == quien and fila["recorded_by"] == quien
    estados = {
        f.tgname: f.estado
        for f in await session.execute(ESTADO_TRIGGERS, {"n": list(BODY_METRICS_TRIGGERS)})
    }
    assert estados == dict.fromkeys(BODY_METRICS_TRIGGERS, "A")


async def test_acepta_fecha_y_campos_vacios(session: AsyncSession) -> None:
    miembro = await socio(session, consentido=True)

    medida = await make_metric(
        session,
        miembro.id,
        measured_on=date(2026, 3, 1),
        weight_g=None,
        body_fat_pct=None,
        notes=None,
    )

    fila = await fila_cruda(session, medida.id)
    assert fila["measured_on"] == date(2026, 3, 1)
    assert fila["height_cm"].startswith("apx1.")
    assert (fila["weight_g"], fila["body_fat_pct"], fila["notes"]) == (None, None, None)


async def test_sin_member_id_crea_un_socio_con_autorizacion_de_datos(
    session: AsyncSession,
) -> None:
    medida = await make_metric(session)

    fila = await fila_cruda(session, medida.id)
    consentimiento = await session.scalar(
        text("SELECT data_consent_at FROM members.members WHERE id = :i"),
        {"i": fila["member_id"]},
    )
    assert consentimiento is not None


async def test_dos_llamadas_dan_ids_distintos_y_el_actor_por_defecto_es_el_del_sistema(
    session: AsyncSession,
) -> None:
    miembro = await socio(session, consentido=True)

    una = await make_metric(session, miembro.id)
    otra = await make_metric(session, miembro.id)

    assert una.id != otra.id
    assert (await fila_cruda(session, una.id))["recorded_by"] == SYSTEM_USER_ID
