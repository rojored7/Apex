"""Frases de "últimos movimientos" (S4A-B8, US-110; S4A-D28), puras.

Catálogo de S4A-D28, copiado literal del blueprint (`sprint-04a-blueprint.md`):
- socio insert: registró a {Socio}; update con `deleted_at` fijado: dio de baja a {Socio}; con
  `deleted_at` limpiado: reactivó a {Socio}; otro update: actualizó los datos de {Socio};
- membresía insert: vendió {Plan} a {Socio}; update con status cancelled: anuló la membresía
  {Plan} de {Socio}; update de pending_payment a otro estado (activación por cobertura): la
  membresía {Plan} de {Socio} quedó al día; otro update: actualizó la membresía {Plan} de
  {Socio};
- pago insert: registró un pago de {monto} de {Socio} (monto de `after.amount_cop`); update con
  `voided` fijado: anuló un pago de {Socio}, sin monto;
- cualquier otro caso: modificó {entidad} de {Socio}.

Forma fijada por este Rojo (S4A-D28 "arma la frase con el actor como `display_name`"): cada
frase es `"{actor} {fragmento}"`, salvo la activación por cobertura, que no lleva actor y empieza
con mayúscula (`"La membresía {Plan} de {Socio} quedó al día"`, como el desglose de US-110,
pregunta 2). Sin punto final. {Socio} es `short_name` ("Laura G."), {monto} es `format_cop`,
{entidad} sale de `ENTITY_LABELS` y el socio o el plan ausente son `GENERIC_MEMBER` ("un socio")
y `GENERIC_PLAN` ("un plan").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID, uuid4

import pytest

from app.core.audit import AuditEntry
from app.core.context import SYSTEM_USER_ID
from app.modules.audit import diff
from app.modules.audit.schemas import AuditEntryView
from tests.dashboard.conftest import dashboard_service

ANA: Final = uuid4()
SOCIA: Final = uuid4()
MEMBRESIA: Final = uuid4()
PAGO: Final = uuid4()
PLAN: Final = uuid4()
EN: Final = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
SOCIOS: Final = "members.members"
MEMBRESIAS: Final = "memberships.memberships"
PAGOS: Final = "payments.payments"
NOMBRES: Final = dashboard_service.MovementNames(
    actors={ANA: "ana.perez", SYSTEM_USER_ID: "Sistema"},
    members={SOCIA: "Laura G."},
    plans={MEMBRESIA: "Plan Mensual"},
)
BLOB: Final = "apx1.0b5a6d1e-7c1f-4b8a-9d55-2f0e6d3c9a11.A256GCM.bm9uY2U.Y2lmcmFkbw"


def vista(
    tabla: str,
    accion: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    usuario: UUID = ANA,
    socio: UUID | None = SOCIA,
) -> AuditEntryView:
    registro = {SOCIOS: SOCIA, MEMBRESIAS: MEMBRESIA, PAGOS: PAGO}.get(tabla, uuid4())
    return AuditEntryView(
        seq=7,
        at=EN,
        user_id=usuario,
        action=accion,  # type: ignore[arg-type]
        table_name=tabla,
        record_id=registro,
        subject_member_id=socio,
        before=before,
        after=after,
    )


def frase(entrada: AuditEntryView, nombres: Any = NOMBRES) -> str:
    return dashboard_service.movement_phrase(entrada, nombres)


# Socio --------------------------------------------------------------------------------------


def test_alta_de_socio() -> None:
    entrada = vista(SOCIOS, "insert", None, {"deleted_at": None, "status": "active"})
    assert frase(entrada) == "ana.perez registró a Laura G."


def test_baja_de_socio() -> None:
    entrada = vista(
        SOCIOS,
        "update",
        {"deleted_at": None, "status": "active"},
        {"deleted_at": "2026-10-20T15:00:00+00:00", "status": "inactive"},
    )
    assert frase(entrada) == "ana.perez dio de baja a Laura G."


def test_reactivacion_de_socio() -> None:
    entrada = vista(
        SOCIOS,
        "update",
        {"deleted_at": "2026-10-20T15:00:00+00:00", "status": "inactive"},
        {"deleted_at": None, "status": "active"},
    )
    assert frase(entrada) == "ana.perez reactivó a Laura G."


@pytest.mark.parametrize(
    ("before", "after"),
    [({}, {}), (None, None), ({"status": "active"}, {"status": "inactive"})],
    ids=["vacios", "nulos", "otro-campo"],
)
def test_otra_edicion_de_socio(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> None:
    """Un cambio de teléfono o correo llega reducido sin llaves: es "actualizó los datos"."""
    assert (
        frase(vista(SOCIOS, "update", before, after)) == "ana.perez actualizó los datos de Laura G."
    )


# Membresía ----------------------------------------------------------------------------------


def test_venta() -> None:
    after = {"member_id": str(SOCIA), "plan_id": str(PLAN), "status": "pending_payment"}
    assert (
        frase(vista(MEMBRESIAS, "insert", None, after))
        == "ana.perez vendió Plan Mensual a Laura G."
    )


@pytest.mark.parametrize("antes", ["active", "pending_payment", "frozen"])
def test_anulacion_de_membresia(antes: str) -> None:
    """`status` cancelled manda aunque viniera de `pending_payment` (orden del catálogo)."""
    entrada = vista(MEMBRESIAS, "update", {"status": antes}, {"status": "cancelled"})
    assert frase(entrada) == "ana.perez anuló la membresía Plan Mensual de Laura G."


@pytest.mark.parametrize("despues", ["active", "expiring"])
def test_activacion_por_cobertura_no_lleva_actor(despues: str) -> None:
    entrada = vista(MEMBRESIAS, "update", {"status": "pending_payment"}, {"status": despues})
    assert frase(entrada) == "La membresía Plan Mensual de Laura G. quedó al día"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"status": "active"}, {"status": "pending_payment"}),
        ({"status": "active"}, {"status": "frozen"}),
        ({}, {}),
    ],
    ids=["revierte", "congela", "sin-estado"],
)
def test_otra_edicion_de_membresia(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    entrada = vista(MEMBRESIAS, "update", before, after)
    assert frase(entrada) == "ana.perez actualizó la membresía Plan Mensual de Laura G."


# Pago ---------------------------------------------------------------------------------------


def test_registro_de_pago_con_monto() -> None:
    after = {
        "amount_cop": 120_000,
        "member_id": str(SOCIA),
        "membership_id": str(MEMBRESIA),
        "voided": False,
    }
    assert frase(vista(PAGOS, "insert", None, after)) == (
        "ana.perez registró un pago de $ 120.000 de Laura G."
    )


def test_anulacion_de_pago_sin_monto() -> None:
    entrada = vista(PAGOS, "update", {"voided": False}, {"voided": True})
    texto = frase(entrada)
    assert texto == "ana.perez anuló un pago de Laura G."
    assert "$" not in texto


# Frase genérica, actor Sistema y nombres ausentes --------------------------------------------


@pytest.mark.parametrize(
    ("tabla", "accion", "before", "after", "esperada"),
    [
        (SOCIOS, "delete", {"status": "active"}, None, "ana.perez modificó la ficha de Laura G."),
        (
            MEMBRESIAS,
            "delete",
            {"status": "active"},
            None,
            "ana.perez modificó la membresía de Laura G.",
        ),
        (PAGOS, "update", {}, {}, "ana.perez modificó el pago de Laura G."),
        (PAGOS, "delete", {"voided": False}, None, "ana.perez modificó el pago de Laura G."),
    ],
    ids=["socio-delete", "membresia-delete", "pago-update-sin-voided", "pago-delete"],
)
def test_cualquier_otro_caso_usa_la_frase_generica(
    tabla: str,
    accion: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    esperada: str,
) -> None:
    assert frase(vista(tabla, accion, before, after)) == esperada


def test_las_etiquetas_de_entidad_son_las_de_las_tres_tablas() -> None:
    assert dict(dashboard_service.ENTITY_LABELS) == {
        SOCIOS: "la ficha",
        MEMBRESIAS: "la membresía",
        PAGOS: "el pago",
    }
    assert dashboard_service.GENERIC_MEMBER == "un socio"
    assert dashboard_service.GENERIC_PLAN == "un plan"


def test_el_actor_sistema_se_nombra_sistema() -> None:
    entrada = vista(SOCIOS, "insert", None, {}, usuario=SYSTEM_USER_ID)
    assert frase(entrada) == "Sistema registró a Laura G."


def test_socio_ausente_usa_el_generico() -> None:
    sin_socio = dashboard_service.MovementNames(
        actors=NOMBRES.actors, members={}, plans=NOMBRES.plans
    )
    assert frase(vista(SOCIOS, "insert", None, {}), sin_socio) == "ana.perez registró a un socio"
    assert frase(vista(PAGOS, "update", {"voided": False}, {"voided": True}), sin_socio) == (
        "ana.perez anuló un pago de un socio"
    )


def test_entrada_sin_sujeto_usa_el_socio_generico() -> None:
    entrada = vista(MEMBRESIAS, "insert", None, {}, socio=None)
    assert frase(entrada) == "ana.perez vendió Plan Mensual a un socio"


def test_plan_ausente_usa_el_generico() -> None:
    sin_plan = dashboard_service.MovementNames(
        actors=NOMBRES.actors, members=NOMBRES.members, plans={}
    )
    assert frase(vista(MEMBRESIAS, "insert", None, {}), sin_plan) == (
        "ana.perez vendió un plan a Laura G."
    )
    entrada = vista(MEMBRESIAS, "update", {"status": "pending_payment"}, {"status": "active"})
    assert frase(entrada, sin_plan) == "La membresía un plan de Laura G. quedó al día"


def test_movement_names_es_inmutable() -> None:
    with pytest.raises(FrozenInstanceError):
        NOMBRES.actors = {}  # type: ignore[misc]


# Blobs: la vista reducida los descarta antes de la frase ------------------------------------


def _fila_de_socio_con_blobs() -> AuditEntry:
    return AuditEntry(
        id=uuid4(),
        seq=4,
        at=EN,
        user_id=ANA,
        action="insert",
        table_name=SOCIOS,
        record_id=SOCIA,
        subject_member_id=SOCIA,
        before=None,
        after={
            "first_name": "Laura",
            "last_name": "Gómez Restrepo",
            "document": BLOB,
            "document_idx": "***",
            "phone": BLOB,
            "email": BLOB,
            "birth_date": BLOB,
            "emergency_contact": BLOB,
            "status": "active",
            "deleted_at": None,
            "notes": "llamar " + BLOB,
        },
    )


def test_una_entrada_con_blobs_en_document_no_los_incluye() -> None:
    reducida = diff.reduce_entry(_fila_de_socio_con_blobs())
    assert reducida.after == {"status": "active", "deleted_at": None}
    texto = frase(reducida)
    assert texto == "ana.perez registró a Laura G."
    assert "apx1." not in texto
    assert "apx1." not in repr(reducida)


# Dudas del Rojo de B8 fijadas en el Verde --------------------------------------------------


def test_actor_inexistente_se_nombra_alguien() -> None:
    """Un `user_id` sin usuario (no ocurre: la cadena referencia usuarios que nunca se borran
    físicamente) no rompe la frase: el actor es `UNKNOWN_ACTOR`."""
    entrada = vista(SOCIOS, "insert", None, {}, usuario=uuid4())
    assert dashboard_service.UNKNOWN_ACTOR == "Alguien"
    assert frase(entrada) == "Alguien registró a Laura G."


@pytest.mark.parametrize(
    "after",
    [None, {}, {"voided": False}, {"amount_cop": "120000"}, {"amount_cop": True}],
    ids=["nulo", "vacio", "sin-monto", "monto-texto", "monto-booleano"],
)
def test_insert_de_pago_sin_monto_entero_usa_la_frase_generica(
    after: Mapping[str, Any] | None,
) -> None:
    """Un `insert` de pago sin `amount_cop` entero (filas sintéticas de `make_audit_chain`) no
    inventa un monto: cae en "modificó el pago de {Socio}"."""
    assert frase(vista(PAGOS, "insert", None, after)) == "ana.perez modificó el pago de Laura G."


# Sin montos para el coach (S4A-D118) --------------------------------------------------------


def test_registro_de_pago_sin_monto_para_quien_no_ve_finanzas() -> None:
    after = {"amount_cop": 120_000, "member_id": str(SOCIA), "voided": False}
    entrada = vista(PAGOS, "insert", None, after)
    texto = dashboard_service.movement_phrase(entrada, NOMBRES, with_amount=False)
    assert texto == "ana.perez registró un pago de Laura G."
    assert "$" not in texto and "120" not in texto


def test_anulacion_de_pago_igual_con_y_sin_monto() -> None:
    entrada = vista(PAGOS, "update", {"voided": False}, {"voided": True})
    con = dashboard_service.movement_phrase(entrada, NOMBRES, with_amount=True)
    sin = dashboard_service.movement_phrase(entrada, NOMBRES, with_amount=False)
    assert con == sin == "ana.perez anuló un pago de Laura G."


def test_sin_monto_no_cambia_las_frases_de_socios_ni_membresias() -> None:
    entradas = [
        vista(SOCIOS, "insert", None, {}),
        vista(MEMBRESIAS, "insert", None, {}),
        vista(MEMBRESIAS, "update", {"status": "pending_payment"}, {"status": "active"}),
        vista(PAGOS, "insert", None, {}),
    ]
    for entrada in entradas:
        assert dashboard_service.movement_phrase(entrada, NOMBRES, with_amount=False) == frase(
            entrada
        )


def test_solo_el_admin_ve_finanzas() -> None:
    assert dashboard_service.FINANCE_ROLES == frozenset({"admin"})
    assert dashboard_service.can_see_finances("admin") is True
    assert dashboard_service.can_see_finances("coach") is False
    assert dashboard_service.can_see_finances("member") is False
