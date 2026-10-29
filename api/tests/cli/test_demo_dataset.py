"""`app.seed.dataset.demo_dataset` (S4B-B1, US-111; S4B-D32): el catálogo puro de la demostración.

Contrato (todo ficticio, sin base ni reloj):
- con `today = 2026-10-21` y `expiring_days = 7` hay un `expiring` con `expected_end_date`
  2026-10-25 (hoy + 4) y un `expired` con 2026-10-10 (hoy - 11);
- 3 planes (mensual 120.000, trimestral 320.000, tiquetera de 12 clases en 60 días 150.000);
- 30 socios con documento `999` + 7 dígitos únicos, teléfono `300 000 00xx`, correo
  `demo+NN@ejemplo.invalid` y `data_consent` verdadero; cada uno con su venta;
- al menos 2 `active`, 2 `expiring`, 2 `expired`, 1 `frozen`, 2 `pending_payment`, 1 `cancelled`,
  una renovación, un pago anulado y los tres medios de pago; montos enteros positivos;
- la ventana de congelación cumple `max_freeze_days_per_membership` y `max_retroactive_days` por
  defecto (Q9) y contiene a `today`;
- las fechas cuelgan de `today` (invariantes por desplazamiento) y del `expiring_days` recibido.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

import pytest

from app.modules.settings.schemas import MembershipsSettings
from app.seed.dataset import DEMO_DOCUMENT_PREFIX, DemoPayment, DemoSpec, demo_dataset

HOY = date(2026, 10, 21)
CAMPOS = ("active", "expiring", "expired", "frozen", "pending_payment", "cancelled")


@pytest.fixture
def spec() -> DemoSpec:
    return demo_dataset(HOY, 7)


def _pagos(spec: DemoSpec) -> list[DemoPayment]:
    return [
        pago
        for socio in spec.members
        for pago in (
            ([socio.sale.first_payment] if socio.sale.first_payment is not None else [])
            + list(socio.sale.extra_payments)
        )
    ]


def test_por_vencer_y_vencidas_caen_donde_dice_el_plan(spec: DemoSpec) -> None:
    fines = {
        estado: {s.sale.expected_end_date for s in spec.members if s.sale.expected_status == estado}
        for estado in ("expiring", "expired")
    }
    assert fines["expiring"] == {date(2026, 10, 25)}
    assert fines["expired"] == {date(2026, 10, 10)}


def test_tres_planes_con_los_precios_del_plan(spec: DemoSpec) -> None:
    assert len(spec.plans) == 3
    assert {p.price_cop for p in spec.plans} == {120_000, 320_000, 150_000}
    assert len({p.name for p in spec.plans}) == 3
    [tiquetera] = [p for p in spec.plans if p.kind == "classes"]
    assert (tiquetera.class_count, tiquetera.duration_days, tiquetera.price_cop) == (
        12,
        60,
        150_000,
    )
    assert all(p.class_count is None for p in spec.plans if p.kind == "days")


def test_treinta_socios_con_documentos_telefonos_y_correos_ficticios(spec: DemoSpec) -> None:
    assert len(spec.members) == 30
    documentos = [s.document for s in spec.members]
    assert len(set(documentos)) == 30
    assert all(re.fullmatch(rf"{DEMO_DOCUMENT_PREFIX}\d{{7}}", d) for d in documentos)
    assert DEMO_DOCUMENT_PREFIX == "999"
    assert all(re.fullmatch(r"300 000 00\d\d", s.phone) for s in spec.members)
    correos = [s.email for s in spec.members]
    assert all(re.fullmatch(r"demo\+\d{2}@ejemplo\.invalid", c) for c in correos)
    assert len(set(correos)) == 30
    assert all(s.first_name.strip() and s.last_name.strip() for s in spec.members)
    assert all(s.birth_date < HOY for s in spec.members)
    assert {"f", "m"} <= {s.sex for s in spec.members}


def test_todos_los_socios_autorizaron_el_tratamiento_de_datos(spec: DemoSpec) -> None:
    assert all(s.data_consent is True for s in spec.members)


def test_montos_enteros_positivos_y_pagos_a_nombre_de_un_medio_conocido(spec: DemoSpec) -> None:
    assert all(isinstance(p.price_cop, int) and p.price_cop > 0 for p in spec.plans)
    pagos = _pagos(spec)
    assert pagos
    assert all(type(p.amount_cop) is int and p.amount_cop > 0 for p in pagos)
    assert {p.method for p in pagos} == {"cash", "nequi", "breb"}
    assert all(p.paid_on <= HOY for p in pagos)


def test_hay_al_menos_un_caso_por_estado(spec: DemoSpec) -> None:
    cuenta = Counter(s.sale.expected_status for s in spec.members)
    minimos = {
        "active": 2,
        "expiring": 2,
        "expired": 2,
        "frozen": 1,
        "pending_payment": 2,
        "cancelled": 1,
    }
    for estado, minimo in minimos.items():
        assert cuenta[estado] >= minimo, (estado, cuenta)
    assert set(cuenta) <= set(CAMPOS)


def test_hay_una_renovacion_un_anulado_y_una_cancelacion(spec: DemoSpec) -> None:
    assert sum(1 for s in spec.members if s.sale.renewal) == 1
    assert sum(1 for p in _pagos(spec) if p.void) >= 1
    assert all(s.sale.cancel for s in spec.members if s.sale.expected_status == "cancelled")
    assert sum(1 for s in spec.members if s.sale.cancel) >= 1


def test_todo_socio_tiene_venta_con_un_plan_del_catalogo(spec: DemoSpec) -> None:
    nombres = {p.name for p in spec.plans}
    assert all(s.sale.plan_name in nombres for s in spec.members)


def test_la_congelacion_cumple_los_limites_por_defecto_y_contiene_hoy(spec: DemoSpec) -> None:
    limites = MembershipsSettings()
    congeladas = [s.sale for s in spec.members if s.sale.freeze is not None]
    assert congeladas
    for venta in congeladas:
        assert venta.freeze is not None
        ventana = venta.freeze
        assert ventana.frozen_from <= ventana.frozen_to
        assert (ventana.frozen_to - ventana.frozen_from).days + 1 <= (
            limites.max_freeze_days_per_membership
        )
        assert 0 <= (HOY - ventana.frozen_from).days <= limites.max_retroactive_days
    assert all(
        s.sale.freeze is not None and s.sale.freeze.frozen_from <= HOY <= s.sale.freeze.frozen_to
        for s in spec.members
        if s.sale.expected_status == "frozen"
    )


def test_lo_pagado_cubre_las_activadas_y_no_pasa_del_precio(spec: DemoSpec) -> None:
    precios = {p.name: p.price_cop for p in spec.plans}
    for socio in spec.members:
        venta = socio.sale
        pagos = ([venta.first_payment] if venta.first_payment else []) + list(venta.extra_payments)
        pagado = sum(p.amount_cop for p in pagos if not p.void)
        precio = precios[venta.plan_name]
        assert pagado <= precio, socio.document
        if venta.expected_status in ("active", "expiring", "expired", "frozen"):
            assert pagado >= precio, (socio.document, venta.expected_status)
        if venta.expected_status == "pending_payment":
            assert pagado < precio, socio.document


def test_es_determinista(spec: DemoSpec) -> None:
    assert demo_dataset(HOY, 7) == spec


def test_las_fechas_cuelgan_de_today() -> None:
    base = demo_dataset(HOY, 7)
    despues = demo_dataset(date(2026, 11, 1), 7)

    def desfases(s: DemoSpec, hoy: date) -> list[tuple[int, int]]:
        return [
            ((m.sale.start_date - hoy).days, (m.sale.expected_end_date - hoy).days)
            for m in s.members
        ]

    assert desfases(base, HOY) == desfases(despues, date(2026, 11, 1))
    assert [m.document for m in base.members] == [m.document for m in despues.members]


@pytest.mark.parametrize("expiring_days", [3, 7, 30])
def test_los_estados_por_vencer_y_vigente_respetan_expiring_days(expiring_days: int) -> None:
    spec = demo_dataset(HOY, expiring_days)
    for socio in spec.members:
        dias = (socio.sale.expected_end_date - HOY).days
        if socio.sale.expected_status == "expiring":
            assert 0 <= dias <= expiring_days, dias
        if socio.sale.expected_status == "active":
            assert dias > expiring_days, dias
        if socio.sale.expected_status == "expired":
            assert dias < 0, dias
