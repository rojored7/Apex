"""`members.rules.consent_required(today, consent_required_from)` (S6-C3, US-149; S6-D46, Q16).

Pura: sin fecha de corte nada se exige (Q16: los socios anteriores quedan sin autorización y no se
bloquea nada); con corte futuro todavía no; el día del corte y después, sí. Y la condición SQL
compartida «sin autorización» (`CONSENT_MISSING_CONDITION`) es `data_consent_at IS NULL`.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.members.rules import CONSENT_MISSING_CONDITION, consent_required

HOY = date(2026, 10, 21)


def test_sin_fecha_de_corte_no_se_exige() -> None:
    assert consent_required(HOY, None) is False


@pytest.mark.parametrize(
    "corte", [date(2026, 10, 22), date(2027, 1, 1), date(9999, 12, 31)], ids=str
)
def test_un_corte_futuro_no_exige_todavia(corte: date) -> None:
    assert consent_required(HOY, corte) is False


def test_el_dia_del_corte_ya_se_exige() -> None:
    assert consent_required(HOY, HOY) is True


@pytest.mark.parametrize("corte", [date(2026, 10, 20), date(2026, 1, 1), date(1900, 1, 1)], ids=str)
def test_un_corte_pasado_se_exige(corte: date) -> None:
    assert consent_required(HOY, corte) is True


def test_la_condicion_compartida_es_data_consent_at_is_null() -> None:
    sql = str(CONSENT_MISSING_CONDITION.compile(dialect=postgresql.dialect()))
    assert sql == "members.members.data_consent_at IS NULL"
