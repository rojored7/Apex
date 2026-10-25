"""Reglas puras de membresías (S3-B1, US-083; blueprint B1 "Rojo", sección 2 "Tipos puros"; D5,
D8, D15, D16, N-23, N-24, M-4).

Sin base ni reloj: "hoy" llega como argumento. Fechas calculadas a mano (N-23, fin inclusivo:
`start + duration_days`; 30 días dan acceso 31 días):
- 2026-10-01 + 30 = 2026-10-31; + 60 = 2026-11-30; 2028-02-01 + 30 = 2028-03-02 (2028 es
  bisiesto: febrero tiene 29); 2026-10-21 + 30 = 2026-11-20; 2026-12-15 + 30 = 2027-01-14.
- Con `expiring_days = 7` y fin 2026-10-31: el 23 faltan 8 días (al día), el 24 faltan 7 (por
  vencer), el 31 faltan 0 (por vencer), el 1 de noviembre ya pasó (vencida).
- Hoy de las pruebas es 2026-10-21 (D33): hoy + 366 = 2027-10-22 (2027 no es bisiesto), hoy + 367
  = 2027-10-23, hoy - 7 = 2026-10-14 y hoy - 8 = 2026-10-13.
- Renovación (Q1): vigente hasta el 2026-10-28 empieza el 29; adyacentes no se solapan con
  `daterange(start, end, '[]')`: fin el 28 e inicio el 29 caben, inicio el 28 choca.
- S3-B4 (E5, S3-D75): `prefix_field("first_payment", "amount_cop")` es
  `"first_payment.amount_cop"` y `None` queda `None`; `sell.reraise_with_prefix` re-lanza una copia
  de la misma clase con `code`, `message`, `existing_id`, `status` y `headers` intactos y solo el
  `field` prefijado (el original no cambia).
- S3-B7 (US-091, US-092; D18, L-9, N-26): `parse_status_filter` (comas, partes recortadas,
  repetidos fundidos, `None`/vacío/espacios sin filtro; desconocido, mayúsculas o parte vacía son
  `StatusFilterInvalid` 422 `validation_error` en `status` sin eco del valor) y
  `resolve_member_status`/`resolve_member_membership` con los nueve casos de US-092 sobre
  snapshots con estado EFECTIVO y hoy 2026-10-21: vigente (`active`, `expiring` o `frozen` con
  inicio <= hoy) > `pending_payment` > `expired` > futura (inicio > hoy) > `none`; las canceladas
  no cuentan; dentro de una categoría decide el fin más tardío.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.db import DatabaseBusy
from app.core.errors import DomainError, TooManyRequestsError
from app.modules.memberships.exceptions import (
    MembershipConflict,
    StartDateTooFar,
    StartDateTooRetroactive,
    StatusFilterInvalid,
)
from app.modules.memberships.models import STATUSES
from app.modules.memberships.rules import (
    MAX_START_AHEAD_DAYS,
    MEMBER_STATUS_PRIORITY,
    FreezeWindow,
    MembershipSnapshot,
    MembershipStatus,
    OpenMemberships,
    PaymentLine,
    PlanTerms,
    classify_open,
    compute_end_date,
    compute_status,
    covers,
    effective,
    find_overlap,
    is_covered,
    next_start_for_renewal,
    paid_total,
    parse_status_filter,
    prefix_field,
    resolve_member_membership,
    resolve_member_status,
    snapshot,
    validate_start_date,
)
from app.modules.memberships.sell import reraise_with_prefix
from app.modules.payments.exceptions import (
    PaidAtInFuture,
    PaidAtTooRetroactive,
    PaymentError,
    PaymentExceedsBalance,
    PaymentLimitReached,
)

HOY = date(2026, 10, 21)
S = MembershipStatus
DIAS_30 = PlanTerms(kind="days", duration_days=30, class_count=None)


def snap(
    status: MembershipStatus = S.active,
    start: date = date(2026, 10, 1),
    end: date = date(2026, 10, 31),
    classes_remaining: int | None = None,
    id: UUID | None = None,
) -> MembershipSnapshot:
    return MembershipSnapshot(
        id=id or uuid4(),
        status=status,
        start_date=start,
        end_date=end,
        classes_remaining=classes_remaining,
    )


def ventana(desde: date, hasta: date) -> FreezeWindow:
    return FreezeWindow(frozen_from=desde, frozen_to=hasta)


# Catálogo ------------------------------------------------------------------------------------


def test_los_estados_de_la_regla_son_los_del_modelo() -> None:
    assert {s.value for s in MembershipStatus} == set(STATUSES)
    assert len(STATUSES) == 6
    assert MAX_START_AHEAD_DAYS == 366


# compute_end_date ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inicio", "plan", "fin"),
    [
        (date(2026, 10, 1), DIAS_30, date(2026, 10, 31)),
        (
            date(2026, 10, 1),
            PlanTerms(kind="classes", duration_days=60, class_count=12),
            date(2026, 11, 30),
        ),
        (date(2028, 2, 1), DIAS_30, date(2028, 3, 2)),
        (date(2026, 10, 21), DIAS_30, date(2026, 11, 20)),
        (date(2026, 12, 15), DIAS_30, date(2027, 1, 14)),
        (
            date(2026, 10, 21),
            PlanTerms(kind="days", duration_days=1, class_count=None),
            date(2026, 10, 22),
        ),
    ],
    ids=["30-dias", "clases-60-dias", "febrero-bisiesto", "venta-de-hoy", "cruce-de-ano", "un-dia"],
)
def test_compute_end_date_es_inicio_mas_duracion_con_fin_inclusivo(
    inicio: date, plan: PlanTerms, fin: date
) -> None:
    assert compute_end_date(inicio, plan) == fin


# compute_status -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hoy", "esperado"),
    [
        (date(2026, 10, 1), S.active),
        (date(2026, 10, 23), S.active),
        (date(2026, 10, 24), S.expiring),
        (date(2026, 10, 30), S.expiring),
        (date(2026, 10, 31), S.expiring),
        (date(2026, 11, 1), S.expired),
        (date(2027, 1, 1), S.expired),
    ],
    ids=[
        "primer-dia",
        "faltan-8",
        "faltan-7",
        "faltan-1",
        "ultimo-dia",
        "dia-siguiente",
        "mucho-despues",
    ],
)
def test_compute_status_por_fecha_con_expiring_days_7(
    hoy: date, esperado: MembershipStatus
) -> None:
    assert compute_status(snap(), hoy, 7, []) == esperado


def test_compute_status_con_expiring_days_0_solo_el_ultimo_dia_es_por_vencer() -> None:
    assert compute_status(snap(), date(2026, 10, 30), 0, []) == S.active
    assert compute_status(snap(), date(2026, 10, 31), 0, []) == S.expiring


def test_pending_payment_se_conserva_aunque_las_fechas_ya_pasaron() -> None:
    pendiente = snap(S.pending_payment, date(2026, 8, 1), date(2026, 8, 31))
    assert compute_status(pendiente, HOY, 7, []) == S.pending_payment


def test_pending_payment_gana_a_una_ventana_de_congelacion_que_contiene_hoy() -> None:
    pendiente = snap(S.pending_payment)
    assert compute_status(pendiente, HOY, 7, [ventana(HOY, HOY)]) == S.pending_payment


@pytest.mark.parametrize(
    ("hoy", "ventanas"),
    [
        (HOY, []),
        (date(2026, 11, 15), []),
        (HOY, [ventana(date(2026, 10, 15), date(2026, 10, 25))]),
        (date(2026, 10, 30), []),
    ],
    ids=["vigente", "vencida-por-fecha", "con-ventana-hoy", "por-vencer"],
)
def test_cancelled_siempre_es_cancelled(hoy: date, ventanas: list[FreezeWindow]) -> None:
    assert compute_status(snap(S.cancelled), hoy, 7, ventanas) == S.cancelled


def test_classes_remaining_cero_es_vencida_aunque_las_fechas_esten_vigentes() -> None:
    assert compute_status(snap(classes_remaining=0), HOY, 7, []) == S.expired
    assert compute_status(snap(classes_remaining=3), HOY, 7, []) == S.active


@pytest.mark.parametrize(
    "ventanas",
    [
        [ventana(date(2026, 10, 15), date(2026, 10, 25))],
        [ventana(HOY, date(2026, 10, 25))],
        [ventana(date(2026, 10, 15), HOY)],
        [ventana(HOY, HOY)],
        [
            ventana(date(2026, 10, 1), date(2026, 10, 5)),
            ventana(date(2026, 10, 20), date(2026, 10, 22)),
        ],
    ],
    ids=["contiene-hoy", "empieza-hoy", "termina-hoy", "solo-hoy", "segunda-de-dos"],
)
def test_una_ventana_que_contiene_hoy_da_frozen(ventanas: list[FreezeWindow]) -> None:
    assert compute_status(snap(), HOY, 7, ventanas) == S.frozen


@pytest.mark.parametrize(
    "ventanas",
    [
        [ventana(date(2026, 10, 1), date(2026, 10, 5))],
        [ventana(date(2026, 10, 25), date(2026, 10, 28))],
        [
            ventana(date(2026, 10, 1), date(2026, 10, 20)),
            ventana(date(2026, 10, 22), date(2026, 10, 24)),
        ],
    ],
    ids=["pasada", "futura", "rodean-hoy-sin-contenerlo"],
)
def test_una_ventana_que_no_contiene_hoy_no_congela(ventanas: list[FreezeWindow]) -> None:
    assert compute_status(snap(), HOY, 7, ventanas) == S.active


def test_el_estado_guardado_no_manda_salvo_cancelled_y_pending_payment() -> None:
    """D5: una `frozen` sin ventanas que contengan hoy, o una `expired` vigente por fecha, se
    leen por la fecha (el job de US-094 llega en el Sprint 4A)."""
    assert compute_status(snap(S.frozen), HOY, 7, []) == S.active
    assert compute_status(snap(S.expired), HOY, 7, []) == S.active
    assert compute_status(snap(S.active), date(2026, 11, 1), 7, []) == S.expired


def test_una_futura_activa_se_lee_al_dia() -> None:
    futura = snap(S.active, date(2026, 11, 1), date(2026, 11, 30))
    assert compute_status(futura, HOY, 7, []) == S.active


def test_expiring_days_negativo_es_value_error() -> None:
    with pytest.raises(ValueError, match="expiring_days"):
        compute_status(snap(), HOY, -1, [])


def test_effective_devuelve_otro_snapshot_con_el_estado_calculado() -> None:
    original = snap(S.active)
    calculado = effective(original, date(2026, 10, 24), 7, [])
    assert calculado == replace(original, status=S.expiring)
    assert calculado is not original
    assert original.status == S.active


# Cobertura (RN-03, Q5) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pagado", "cubre"),
    [(120_000, True), (119_999, False), (150_000, True), (0, False)],
    ids=["igual", "menor", "mayor-q5", "nada"],
)
def test_covers(pagado: int, cubre: bool) -> None:
    assert covers(120_000, pagado) is cubre


def test_paid_total_suma_solo_los_no_anulados() -> None:
    lineas = [PaymentLine(60_000, False), PaymentLine(60_000, True), PaymentLine(30_000, False)]
    assert paid_total(lineas) == 90_000
    assert paid_total([]) == 0


@pytest.mark.parametrize(
    ("lineas", "cubre"),
    [
        ([PaymentLine(120_000, False)], True),
        ([PaymentLine(60_000, False), PaymentLine(60_000, False)], True),
        ([PaymentLine(60_000, False)], False),
        ([PaymentLine(200_000, False)], True),
        ([PaymentLine(120_000, True), PaymentLine(120_000, True)], False),
        ([], False),
    ],
    ids=["igual", "dos-abonos", "abono", "mayor-q5", "todos-anulados", "sin-pagos"],
)
def test_is_covered(lineas: list[PaymentLine], cubre: bool) -> None:
    assert is_covered(120_000, lineas) is cubre


# next_start_for_renewal (Q1) -----------------------------------------------------------------


def test_renovar_una_vigente_empieza_el_dia_siguiente_al_fin() -> None:
    vigente = snap(S.active, date(2026, 9, 29), date(2026, 10, 28))
    assert next_start_for_renewal(vigente, HOY) == date(2026, 10, 29)


def test_renovar_el_ultimo_dia_empieza_manana() -> None:
    vigente = snap(S.expiring, date(2026, 9, 21), HOY)
    assert next_start_for_renewal(vigente, HOY) == date(2026, 10, 22)


def test_renovar_una_vencida_o_sin_membresia_empieza_hoy() -> None:
    vencida = snap(S.expired, date(2026, 9, 1), date(2026, 10, 10))
    assert next_start_for_renewal(vencida, HOY) == HOY
    assert next_start_for_renewal(None, HOY) == HOY


# classify_open y find_overlap (D8) --------------------------------------------------------------


@pytest.mark.parametrize(
    "estado", [S.active, S.expiring, S.frozen], ids=["activa", "por-vencer", "congelada"]
)
def test_una_vigente_es_current(estado: MembershipStatus) -> None:
    vigente = snap(estado)
    assert classify_open([vigente], HOY) == OpenMemberships(current=vigente, future=None)


def test_una_activa_que_empieza_hoy_es_vigente() -> None:
    hoy = snap(S.active, HOY, date(2026, 11, 20))
    assert classify_open([hoy], HOY) == OpenMemberships(current=hoy, future=None)


@pytest.mark.parametrize(
    "futura",
    [
        snap(S.pending_payment, date(2026, 11, 1), date(2026, 11, 30)),
        snap(S.pending_payment, date(2026, 10, 1), date(2026, 10, 31)),
        snap(S.pending_payment, date(2026, 8, 1), date(2026, 8, 31)),
        snap(S.active, date(2026, 10, 29), date(2026, 11, 28)),
        snap(S.expiring, date(2026, 10, 22), date(2026, 10, 25)),
    ],
    ids=[
        "pendiente-futura",
        "pendiente-en-curso",
        "pendiente-vieja",
        "activa-futura",
        "por-vencer-futura",
    ],
)
def test_una_futura_es_future(futura: MembershipSnapshot) -> None:
    assert classify_open([futura], HOY) == OpenMemberships(current=None, future=futura)


def test_vigente_y_futura_a_la_vez() -> None:
    vigente = snap(S.active, date(2026, 9, 29), date(2026, 10, 28))
    futura = snap(S.pending_payment, date(2026, 10, 29), date(2026, 11, 28))
    assert classify_open([futura, vigente], HOY) == OpenMemberships(current=vigente, future=futura)


def test_solo_vencidas_o_canceladas_no_abren_nada() -> None:
    items = [
        snap(S.expired, date(2026, 9, 1), date(2026, 10, 10)),
        snap(S.cancelled, date(2026, 10, 1), date(2026, 10, 31)),
    ]
    assert classify_open(items, HOY) == OpenMemberships(current=None, future=None)
    assert classify_open([], HOY) == OpenMemberships(current=None, future=None)


OTRA = UUID("11111111-1111-1111-1111-111111111111")
SEGUNDA = UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.parametrize(
    ("inicio", "fin", "esperado"),
    [
        (date(2026, 10, 29), date(2026, 11, 28), None),
        (date(2026, 10, 28), date(2026, 11, 27), OTRA),
        (date(2026, 9, 1), date(2026, 9, 30), None),
        (date(2026, 9, 1), date(2026, 10, 1), OTRA),
        (date(2026, 9, 1), date(2026, 12, 1), OTRA),
        (date(2026, 10, 10), date(2026, 10, 12), OTRA),
    ],
    ids=[
        "adyacente-despues",
        "mismo-dia-final",
        "adyacente-antes",
        "mismo-dia-inicial",
        "la-contiene",
        "contenida",
    ],
)
def test_find_overlap_con_rangos_cerrados(inicio: date, fin: date, esperado: UUID | None) -> None:
    otra = snap(S.active, date(2026, 10, 1), date(2026, 10, 28), id=OTRA)
    assert find_overlap(inicio, fin, [otra]) == esperado


def test_find_overlap_devuelve_la_que_choca_y_none_sin_otras() -> None:
    primera = snap(S.expired, date(2026, 8, 1), date(2026, 8, 31), id=OTRA)
    segunda = snap(S.active, date(2026, 10, 1), date(2026, 10, 28), id=SEGUNDA)
    assert find_overlap(date(2026, 10, 20), date(2026, 11, 19), [primera, segunda]) == SEGUNDA
    assert find_overlap(date(2026, 10, 20), date(2026, 11, 19), []) is None


# validate_start_date (N-24, M-4) -----------------------------------------------------------------


@pytest.mark.parametrize(
    "inicio",
    [HOY, HOY - timedelta(days=7), HOY + timedelta(days=366), date(2027, 10, 22)],
    ids=["hoy", "hoy-menos-7", "hoy-mas-366", "2027-10-22"],
)
def test_validate_start_date_acepta_la_ventana_permitida(inicio: date) -> None:
    validate_start_date(inicio, HOY, max_retroactive_days=7)


@pytest.mark.parametrize(
    "inicio",
    [date(2026, 10, 13), date(2026, 1, 1), date(1, 1, 1)],
    ids=["hoy-menos-8", "enero", "anio-1"],
)
def test_validate_start_date_rechaza_lo_demasiado_antiguo(inicio: date) -> None:
    with pytest.raises(StartDateTooRetroactive) as error:
        validate_start_date(inicio, HOY, max_retroactive_days=7)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "start_date_too_retroactive",
        "start_date",
    )


@pytest.mark.parametrize(
    "inicio",
    [date(2027, 10, 23), HOY + timedelta(days=367), date(2099, 1, 1), date(9999, 12, 31)],
    ids=["2027-10-23", "hoy-mas-367", "2099", "9999-12-31"],
)
def test_validate_start_date_rechaza_lo_demasiado_lejano_sin_overflow(inicio: date) -> None:
    with pytest.raises(StartDateTooFar) as error:
        validate_start_date(inicio, HOY, max_retroactive_days=7)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "start_date_too_far",
        "start_date",
    )


def test_sin_tope_retroactivo_acepta_cualquier_pasado_pero_no_el_futuro_lejano() -> None:
    """`enforce_retroactive_limit=False` (importación, N-24) llega como `None`; M-4 sigue."""
    validate_start_date(date(2020, 1, 1), HOY, max_retroactive_days=None)
    with pytest.raises(StartDateTooFar):
        validate_start_date(date(2027, 10, 23), HOY, max_retroactive_days=None)


def test_max_ahead_days_se_puede_ajustar() -> None:
    validate_start_date(HOY + timedelta(days=10), HOY, max_retroactive_days=7, max_ahead_days=10)
    with pytest.raises(StartDateTooFar):
        validate_start_date(
            HOY + timedelta(days=11), HOY, max_retroactive_days=7, max_ahead_days=10
        )


# Valores inmutables y validados ----------------------------------------------------------------


def test_los_valores_son_inmutables() -> None:
    with pytest.raises(FrozenInstanceError):
        snap().status = S.expired  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ventana(HOY, HOY).frozen_to = date(2026, 10, 30)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        DIAS_30.duration_days = 60  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        PaymentLine(1, False).voided = True  # type: ignore[misc]


def test_fechas_invertidas_son_value_error() -> None:
    with pytest.raises(ValueError, match="start_date"):
        snap(start=date(2026, 10, 31), end=date(2026, 10, 1))
    with pytest.raises(ValueError, match="frozen_from"):
        ventana(date(2026, 10, 25), date(2026, 10, 15))


def test_un_solo_dia_es_un_rango_valido() -> None:
    assert snap(start=HOY, end=HOY).end_date == HOY
    assert ventana(HOY, HOY).frozen_to == HOY


def test_freeze_window_cuenta_los_dos_extremos_y_sabe_si_contiene_un_dia() -> None:
    diez = ventana(date(2026, 10, 15), date(2026, 10, 25))
    assert diez.days == 11
    assert ventana(HOY, HOY).days == 1
    assert diez.contains(date(2026, 10, 15)) and diez.contains(date(2026, 10, 25))
    assert not diez.contains(date(2026, 10, 14)) and not diez.contains(date(2026, 10, 26))


# prefix_field y reraise_with_prefix (S3-B4, E5, S3-D75) -------------------------------------------


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        ("amount_cop", "first_payment.amount_cop"),
        ("paid_at", "first_payment.paid_at"),
        ("method", "first_payment.method"),
        (None, None),
    ],
)
def test_prefix_field_antepone_el_prefijo_y_respeta_none(
    campo: str | None, esperado: str | None
) -> None:
    assert prefix_field("first_payment", campo) == esperado


def test_prefix_field_usa_el_prefijo_dado() -> None:
    assert prefix_field("renewal", "start_date") == "renewal.start_date"


_ID_EXISTENTE = UUID("0000000a-0000-4000-8000-00000000c401")


def _errores() -> list[DomainError]:
    sobrepago = PaymentExceedsBalance()
    sobrepago.headers["X-Prueba"] = "1"
    return [
        sobrepago,
        PaidAtInFuture(),
        PaidAtTooRetroactive(),
        PaymentLimitReached(),
        MembershipConflict(existing_id=_ID_EXISTENTE),
        # PM3 de la revisión de Fase 4 del Sprint 3: errores con `__init__` propio (sin `code`
        # ni `message` en la firma) y con cabeceras; reconstruirlos daba `TypeError` (500).
        DatabaseBusy(),
        TooManyRequestsError(7),
    ]


@pytest.mark.parametrize("error", _errores(), ids=lambda e: type(e).__name__)
def test_reraise_with_prefix_conserva_todo_menos_el_campo(error: DomainError) -> None:
    with pytest.raises(DomainError) as capturado:
        reraise_with_prefix(error, "first_payment")
    copia = capturado.value
    assert type(copia) is type(error)
    assert copia is not error
    assert (copia.code, copia.message, copia.existing_id, copia.status) == (
        error.code,
        error.message,
        error.existing_id,
        error.status,
    )
    assert copia.headers == error.headers
    assert copia.field == prefix_field("first_payment", error.field)


def test_reraise_with_prefix_da_first_payment_amount_cop_y_paid_at() -> None:
    with pytest.raises(PaymentExceedsBalance) as sobrepago:
        reraise_with_prefix(PaymentExceedsBalance(), "first_payment")
    assert sobrepago.value.field == "first_payment.amount_cop"
    with pytest.raises(PaidAtInFuture) as futuro:
        reraise_with_prefix(PaidAtInFuture(), "first_payment")
    assert (futuro.value.code, futuro.value.field) == ("validation_error", "first_payment.paid_at")


def test_reraise_with_prefix_sin_campo_deja_el_campo_en_none_y_no_cambia_el_original() -> None:
    original = PaymentLimitReached()
    with pytest.raises(PaymentLimitReached) as capturado:
        reraise_with_prefix(original, "first_payment")
    assert capturado.value.field is None
    assert original.field is None
    sobrepago = PaymentExceedsBalance()
    with pytest.raises(PaymentExceedsBalance):
        reraise_with_prefix(sobrepago, "first_payment")
    assert sobrepago.field == "amount_cop"  # el original no se toca


def _subclases(base: type[DomainError]) -> list[type[DomainError]]:
    hijas = base.__subclasses__()
    return [clase for hija in hijas for clase in (hija, *_subclases(hija))]


@pytest.mark.parametrize(
    "clase",
    sorted(set(_subclases(PaymentError)), key=lambda c: c.__name__),
    ids=lambda c: c.__name__,
)
def test_reraise_with_prefix_sirve_para_toda_excepcion_de_pagos(
    clase: type[DomainError],
) -> None:
    """Revisión de seguridad de B4 (LOW-1): toda subclase de `PaymentError` acepta la firma de
    `DomainError` que usa `reraise_with_prefix`; una firma distinta daría `TypeError` (500)."""
    original = clase()
    with pytest.raises(clase) as capturado:
        reraise_with_prefix(original, "first_payment")
    assert type(capturado.value) is clase
    assert capturado.value.field == prefix_field("first_payment", original.field)


# parse_status_filter (S3-B7, D18, L-9) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("active", {S.active}),
        ("active,expiring", {S.active, S.expiring}),
        ("expiring,active,expiring", {S.active, S.expiring}),
        (" active , pending_payment ", {S.active, S.pending_payment}),
        ("cancelled", {S.cancelled}),
        ("pending_payment,active,expiring,expired,frozen,cancelled", set(MembershipStatus)),
    ],
    ids=["uno", "dos", "repetidos", "con-espacios", "canceladas", "los-seis"],
)
def test_parse_status_filter_separa_por_comas_y_funde_repetidos(
    crudo: str, esperado: set[MembershipStatus]
) -> None:
    resultado = parse_status_filter(crudo)
    assert resultado == frozenset(esperado)
    assert isinstance(resultado, frozenset)


@pytest.mark.parametrize("crudo", [None, "", "   "], ids=["none", "vacio", "espacios"])
def test_parse_status_filter_sin_valor_es_sin_filtro(crudo: str | None) -> None:
    assert parse_status_filter(crudo) is None


@pytest.mark.parametrize(
    "crudo",
    ["vigente", "active,vigente", "ACTIVE", "none", "active,", ",active", "active,,expiring"],
    ids=["desconocido", "uno-de-dos", "mayusculas", "none", "coma-final", "coma-inicial", "vacia"],
)
def test_parse_status_filter_rechaza_un_estado_desconocido_sin_repetirlo(crudo: str) -> None:
    with pytest.raises(StatusFilterInvalid) as error:
        parse_status_filter(crudo)
    assert error.value.status == 422
    assert error.value.code == "validation_error"
    assert error.value.field == "status"
    assert "vigente" not in error.value.message
    assert "ACTIVE" not in error.value.message


# resolve_member_status (S3-B7, US-092 criterios 2 a 4) --------------------------------------------
#
# Hoy 2026-10-21. Los snapshots ya traen el estado EFECTIVO (lo que da `compute_status`).

VIGENTE = snap(S.active, date(2026, 10, 1), date(2026, 10, 31))
POR_VENCER = snap(S.expiring, date(2026, 9, 26), date(2026, 10, 26))
RENOVACION_PENDIENTE = snap(S.pending_payment, date(2026, 10, 27), date(2026, 11, 26))
FUTURA_ACTIVA = snap(S.active, date(2026, 10, 28), date(2026, 11, 27))
VENCIDA = snap(S.expired, date(2026, 8, 1), date(2026, 8, 31))
VENCIDA_ANTES = snap(S.expired, date(2026, 6, 1), date(2026, 6, 30))
ANULADA = snap(S.cancelled, date(2026, 10, 1), date(2026, 10, 31))
CONGELADA = snap(S.frozen, date(2026, 10, 1), date(2026, 11, 15))
PENDIENTE = snap(S.pending_payment, date(2026, 10, 21), date(2026, 11, 20))

NUEVE_CASOS: list[tuple[str, list[MembershipSnapshot], str, MembershipSnapshot | None]] = [
    ("solo-vigente", [VIGENTE], "active", VIGENTE),
    (
        "por-vencer-y-renovacion-pendiente",
        [POR_VENCER, RENOVACION_PENDIENTE],
        "expiring",
        POR_VENCER,
    ),
    ("solo-futura-activa", [FUTURA_ACTIVA], "active", FUTURA_ACTIVA),
    ("solo-vencida", [VENCIDA], "expired", VENCIDA),
    ("solo-anulada", [ANULADA], "none", None),
    ("congelada", [CONGELADA], "frozen", CONGELADA),
    ("pendiente-y-vencida", [VENCIDA, PENDIENTE], "pending_payment", PENDIENTE),
    ("vencida-y-futura-activa", [FUTURA_ACTIVA, VENCIDA], "expired", VENCIDA),
    ("vacio", [], "none", None),
]


@pytest.mark.parametrize(
    ("membresias", "esperado"),
    [(m, e) for _, m, e, _ in NUEVE_CASOS],
    ids=[caso for caso, *_ in NUEVE_CASOS],
)
def test_resolve_member_status_aplica_la_prioridad_de_us_092(
    membresias: list[MembershipSnapshot], esperado: str
) -> None:
    assert resolve_member_status(membresias, HOY) == esperado
    assert resolve_member_status(list(reversed(membresias)), HOY) == esperado


@pytest.mark.parametrize(
    ("membresias", "esperado", "decide"),
    [(m, e, d) for _, m, e, d in NUEVE_CASOS],
    ids=[caso for caso, *_ in NUEVE_CASOS],
)
def test_resolve_member_membership_devuelve_la_membresia_que_decide(
    membresias: list[MembershipSnapshot], esperado: str, decide: MembershipSnapshot | None
) -> None:
    assert resolve_member_membership(membresias, HOY) == (esperado, decide)
    assert resolve_member_membership(tuple(reversed(membresias)), HOY) == (esperado, decide)


def test_la_vigente_gana_a_pendiente_vencida_futura_y_anulada() -> None:
    todas = [ANULADA, VENCIDA, RENOVACION_PENDIENTE, FUTURA_ACTIVA, POR_VENCER]
    assert resolve_member_membership(todas, HOY) == ("expiring", POR_VENCER)


def test_la_pendiente_gana_a_la_futura_activa() -> None:
    otra_futura = snap(S.active, date(2026, 11, 21), date(2026, 12, 21))
    assert resolve_member_membership([otra_futura, PENDIENTE], HOY) == (
        "pending_payment",
        PENDIENTE,
    )


def test_entre_vencidas_decide_la_de_fin_mas_tardio() -> None:
    assert resolve_member_membership([VENCIDA_ANTES, VENCIDA], HOY) == ("expired", VENCIDA)
    assert resolve_member_membership([VENCIDA, VENCIDA_ANTES], HOY) == ("expired", VENCIDA)


def test_una_futura_por_vencer_cuenta_con_su_estado_efectivo() -> None:
    """Una futura de un plan corto cuyo fin cae dentro de `expiring_days` llega con su estado
    efectivo `expiring`: el socio cuenta con ese estado (US-092 criterio 4 sobre el efectivo)."""
    corta = snap(S.expiring, date(2026, 10, 23), date(2026, 10, 25))
    assert resolve_member_membership([corta], HOY) == ("expiring", corta)


def test_una_que_empieza_hoy_es_vigente_y_no_futura() -> None:
    de_hoy = snap(S.active, HOY, date(2026, 11, 20))
    pendiente_futura = snap(S.pending_payment, date(2026, 11, 21), date(2026, 12, 21))
    assert resolve_member_membership([pendiente_futura, de_hoy], HOY) == ("active", de_hoy)


def test_la_prioridad_tiene_las_cuatro_categorias_en_orden() -> None:
    assert MEMBER_STATUS_PRIORITY == ("current", "pending_payment", "expired", "future")


# rules.snapshot (PM4 de la revisión de Fase 4 del Sprint 3) -------------------------------------


@dataclass(frozen=True)
class _FilaDeColumnas:
    """Lo que devuelve un `select` de columnas: atributos con el estado guardado como texto."""

    id: UUID
    status: str
    start_date: date
    end_date: date
    classes_remaining: int | None


def test_snapshot_de_una_fila_de_columnas_convierte_el_estado() -> None:
    fila = _FilaDeColumnas(uuid4(), "frozen", HOY, HOY + timedelta(days=30), 4)
    assert snapshot(fila) == MembershipSnapshot(
        id=fila.id,
        status=S.frozen,
        start_date=HOY,
        end_date=HOY + timedelta(days=30),
        classes_remaining=4,
    )


def test_snapshot_con_un_estado_desconocido_es_value_error() -> None:
    with pytest.raises(ValueError, match="no_existe"):
        snapshot(_FilaDeColumnas(uuid4(), "no_existe", HOY, HOY, None))
