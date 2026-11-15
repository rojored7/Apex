"""`consume_class`, `return_class` y `consumes_class` (S7-C2, US-160; S7-D14, S7-D29). Puras.

Sin base ni reloj: "hoy" llega como argumento. Una tiquetera de 12 clases del 1 al 30 de
noviembre de 2026 es el caso base.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.memberships.rules import (
    ClassBalance,
    ClassUsage,
    PlanTerms,
    consume_class,
    consumes_class,
    plan_renewal,
    return_class,
)

INICIO = date(2026, 11, 1)
FIN = date(2026, 11, 30)


def _saldo(restantes: int, **cambios: object) -> ClassBalance:
    valores: dict[str, object] = {
        "start_date": INICIO,
        "end_date": FIN,
        "classes_total": 12,
        "classes_remaining": restantes,
        "original_end_date": None,
    }
    valores.update(cambios)
    return ClassBalance(**valores)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("estado", "total", "esperado"),
    [
        ("active", 12, True),
        ("expiring", 12, True),
        ("active", None, False),
        ("expiring", None, False),
        ("expired", 12, False),
        ("frozen", 12, False),
        ("pending_payment", 12, False),
        ("cancelled", 12, False),
        ("none", None, False),
    ],
)
def test_consumes_class_solo_activas_por_clases(
    estado: str, total: int | None, esperado: bool
) -> None:
    assert consumes_class(estado, total) is esperado


def test_consume_resta_una_y_no_toca_las_fechas() -> None:
    uso = consume_class(_saldo(12), date(2026, 11, 10))
    assert uso == ClassUsage(classes_remaining=11, end_date=FIN, original_end_date=None)


def test_nunca_negativo() -> None:
    uso = consume_class(_saldo(0), date(2026, 11, 10))
    assert uso.classes_remaining == 0


def test_la_ultima_clase_recorta_el_fin_a_hoy_y_guarda_el_original() -> None:
    uso = consume_class(_saldo(1), date(2026, 11, 10))
    assert uso == ClassUsage(
        classes_remaining=0, end_date=date(2026, 11, 10), original_end_date=FIN
    )


@pytest.mark.parametrize(
    ("hoy", "fin_esperado", "original"),
    [
        (date(2026, 11, 10), date(2026, 11, 10), FIN),  # hoy dentro del rango: recorta a hoy
        (date(2026, 10, 25), INICIO, FIN),  # aún no empieza: max(start, hoy) = start
        (date(2026, 11, 30), FIN, None),  # hoy = fin: el fin no cambia, no hay original
        (date(2026, 12, 15), FIN, None),  # ya vencida: min no la alarga
    ],
)
def test_recorte_a_min_end_max_start_hoy(
    hoy: date, fin_esperado: date, original: date | None
) -> None:
    uso = consume_class(_saldo(1), hoy)
    assert (uso.end_date, uso.original_end_date) == (fin_esperado, original)
    assert uso.end_date >= INICIO  # respeta start_date <= end_date


def test_agotar_con_recorte_previo_no_pisa_el_original() -> None:
    previo = _saldo(1, end_date=date(2026, 11, 5), original_end_date=FIN)
    uso = consume_class(previo, date(2026, 11, 3))
    assert uso.original_end_date == FIN and uso.end_date == date(2026, 11, 3)


def test_tope_en_el_total() -> None:
    assert return_class(_saldo(12), overlaps=False).classes_remaining == 12
    assert return_class(_saldo(11), overlaps=False).classes_remaining == 12


def test_restaura_sin_solape() -> None:
    recortada = _saldo(0, end_date=date(2026, 11, 10), original_end_date=FIN)
    uso = return_class(recortada, overlaps=False)
    assert uso == ClassUsage(classes_remaining=1, end_date=FIN, original_end_date=None)


def test_no_restaura_con_solape() -> None:
    recortada = _saldo(0, end_date=date(2026, 11, 10), original_end_date=FIN)
    uso = return_class(recortada, overlaps=True)
    assert uso == ClassUsage(
        classes_remaining=1, end_date=date(2026, 11, 10), original_end_date=FIN
    )


def test_devolver_sin_recorte_solo_suma() -> None:
    uso = return_class(_saldo(5), overlaps=True)
    assert uso == ClassUsage(classes_remaining=6, end_date=FIN, original_end_date=None)


def test_renovacion_tras_agotar_empieza_al_dia_siguiente() -> None:
    """Sin vigente, una tiquetera agotada (recortada a hoy) empuja el inicio al día siguiente."""
    plan = PlanTerms(kind="classes", duration_days=60, class_count=12)
    hoy = date(2026, 10, 21)
    sin_cola = plan_renewal(None, plan, 100_000, hoy)
    con_cola = plan_renewal(None, plan, 100_000, hoy, after=hoy)
    assert sin_cola.start_date == hoy
    assert con_cola.start_date == date(2026, 10, 22)
    assert con_cola.end_date == date(2026, 12, 21)
