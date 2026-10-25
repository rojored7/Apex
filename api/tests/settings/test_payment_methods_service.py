"""Medios de pago en settings con PostgreSQL real (S3-B3, US-056; D24, S3-D55, L-3).

- `get_section("payment_methods")` sin fila da los defaults en versión 0 (leer no siembra);
  `update_section` guarda en versión 1 y la segunda vez exige la versión leída (409
  `version_conflict`); un valor inválido no crea fila.
- `payment_methods(session)` (contrato para `payments`, D24): los tres medios en orden fijo con
  las etiquetas guardadas o las por defecto. Con un JSON guardado a mano que ya no valida (clave
  `tarjeta`, sin `breb`) responde los defaults, nunca un código ajeno, y deja un aviso con solo la
  clave de la sección (nunca las etiquetas).
- Guardar etiquetas no cambia ninguna fila de `payments.payments` (los códigos son fijos).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.settings.exceptions import SettingsValidationError, VersionConflict
from app.modules.settings.schemas import PaymentMethodInfo, SectionKey
from app.modules.settings.service import get_section, payment_methods, update_section
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.settings._apoyo import (
    ADMIN_ID,
    PAYMENT_METHODS_DEFAULTS,
    PAYMENT_METHODS_OK,
    fila,
    filas_de_auditoria,
)

POR_DEFECTO = (
    PaymentMethodInfo(code="cash", label="Efectivo", hint=""),
    PaymentMethodInfo(code="nequi", label="Nequi", hint=""),
    PaymentMethodInfo(code="breb", label="Bre-B", hint=""),
)
GUARDADOS = (
    PaymentMethodInfo(code="cash", label="Caja", hint="Billetes y monedas"),
    PaymentMethodInfo(code="nequi", label="Nequi", hint="Número de comprobante"),
    PaymentMethodInfo(code="breb", label="Bre-B (Bancolombia)", hint=""),
)
CLAVE = SectionKey.payment_methods


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


async def _guardar_crudo(session: AsyncSession, valor: dict[str, Any]) -> None:
    await session.execute(
        text(
            "INSERT INTO settings.settings_sections (id, key, value, version, updated_by,"
            " created_by) VALUES (gen_random_uuid(), 'payment_methods', CAST(:v AS jsonb), 1,"
            " :u, :u)"
        ),
        {"v": json.dumps(valor), "u": SYSTEM_USER_ID},
    )


async def test_sin_fila_get_section_da_los_defaults_en_version_0(db: AsyncSession) -> None:
    salida = await get_section(db, "payment_methods")
    assert (salida.key, salida.value, salida.version) == (CLAVE, PAYMENT_METHODS_DEFAULTS, 0)
    assert await fila(db, "payment_methods") is None


async def test_sin_fila_payment_methods_da_los_tres_por_defecto(db: AsyncSession) -> None:
    assert await payment_methods(db) == POR_DEFECTO
    assert await fila(db, "payment_methods") is None


async def test_guardar_y_leer_las_etiquetas_en_orden_fijo(db: AsyncSession) -> None:
    salida = await update_section(db, CLAVE, PAYMENT_METHODS_OK, 0, ADMIN_ID)
    assert (salida.version, salida.value) == (1, PAYMENT_METHODS_OK)
    assert await payment_methods(db) == GUARDADOS
    auditoria = await filas_de_auditoria(db)
    assert [(f["action"], f["user_id"]) for f in auditoria] == [("insert", ADMIN_ID)]


async def test_la_segunda_vez_exige_la_version_leida(db: AsyncSession) -> None:
    await update_section(db, CLAVE, PAYMENT_METHODS_OK, 0, ADMIN_ID)
    with pytest.raises(VersionConflict) as error:
        await update_section(db, CLAVE, PAYMENT_METHODS_DEFAULTS, 0, ADMIN_ID)
    assert (error.value.status, error.value.code) == (409, "version_conflict")
    guardada = await fila(db, "payment_methods")
    assert guardada is not None and guardada["value"] == PAYMENT_METHODS_OK
    segunda = await update_section(db, CLAVE, PAYMENT_METHODS_DEFAULTS, 1, ADMIN_ID)
    assert segunda.version == 2
    assert await payment_methods(db) == POR_DEFECTO


async def test_un_valor_invalido_no_crea_fila(db: AsyncSession) -> None:
    repetidas = {**PAYMENT_METHODS_OK, "breb": {"label": "caja"}}
    with pytest.raises(SettingsValidationError) as error:
        await update_section(db, CLAVE, repetidas, 0, ADMIN_ID)
    assert error.value.field == "value.breb.label"
    assert await fila(db, "payment_methods") is None
    assert await filas_de_auditoria(db) == []


async def test_el_json_guardado_en_otro_orden_sale_en_orden_fijo(db: AsyncSession) -> None:
    await _guardar_crudo(
        db, {codigo: PAYMENT_METHODS_OK[codigo] for codigo in ("breb", "nequi", "cash")}
    )
    assert await payment_methods(db) == GUARDADOS


@pytest.mark.parametrize(
    "valor",
    [
        {**PAYMENT_METHODS_OK, "tarjeta": {"label": "Tarjeta-Secreta-7731", "hint": ""}},
        {"cash": {"label": "Tarjeta-Secreta-7731"}, "nequi": {"label": "Nequi"}},
        {"cash": {"label": 5}, "nequi": {"label": "Nequi"}, "breb": {"label": "Bre-B"}},
    ],
    ids=["clave-tarjeta", "sin-breb", "etiqueta-no-texto"],
)
async def test_un_json_que_ya_no_valida_da_los_defaults_y_un_aviso_sin_valores(
    db: AsyncSession, caplog: pytest.LogCaptureFixture, valor: dict[str, Any]
) -> None:
    await _guardar_crudo(db, valor)
    with caplog.at_level(logging.WARNING, logger="app.settings"):
        metodos = await payment_methods(db)
    assert metodos == POR_DEFECTO
    assert [m.code for m in metodos] == ["cash", "nequi", "breb"]
    avisos = [r for r in caplog.records if r.name == "app.settings"]
    assert avisos
    assert all("Tarjeta-Secreta-7731" not in r.getMessage() for r in avisos)
    assert "Tarjeta-Secreta-7731" not in caplog.text


async def test_guardar_etiquetas_no_cambia_los_pagos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan)
    pago = await make_payment(session, membresia, amount=60_000, method="breb")
    consulta = text("SELECT method, amount_cop, updated_at FROM payments.payments WHERE id = :id")
    antes = (await session.execute(consulta, {"id": pago.id})).one()
    with actor_scope(ADMIN_ID):
        await update_section(session, CLAVE, PAYMENT_METHODS_OK, 0, ADMIN_ID)
    despues = (await session.execute(consulta, {"id": pago.id})).one()
    assert tuple(despues) == tuple(antes) and despues.method == "breb"
    total = await session.scalar(text("SELECT count(*) FROM payments.payments"))
    assert total == 1
