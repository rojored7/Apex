"""Los códigos de los medios de pago coinciden en los cinco sitios (S3-B3, US-056; D24).

Los códigos son fijos (`cash`, `nequi`, `breb`); `settings` solo cambia cómo se ven. Si un sitio
los cambiara y otro no, un pago válido para el API lo rechazaría la base (o al revés), o el front
pintaría un medio que no se puede registrar. Fuentes:
1. `settings.schemas.PAYMENT_METHOD_CODES` (y las claves de `PaymentMethodsSettings`);
2. el `Literal` `payments.schemas.PaymentMethod`;
3. `payments.models.PAYMENT_METHODS`;
4. el CHECK `method` del modelo `Payment`;
5. el texto de la migración `0010_payments.py` (su CHECK `method`).
La lista de un CHECK se lee con una expresión regular sobre `method IN (...)`; un control con un
texto falso comprueba que el lector no devuelve una lista vacía.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import CheckConstraint

from app.modules.payments.models import PAYMENT_METHODS, Payment
from app.modules.payments.schemas import PaymentMethod
from app.modules.settings.schemas import PAYMENT_METHOD_CODES, PaymentMethodsSettings

ESPERADOS = ("cash", "nequi", "breb")
MIGRACION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0010_payments.py"
_LISTA_DEL_CHECK = re.compile(r"method\s+IN\s*\(([^)]*)\)", re.IGNORECASE)


def codigos_del_check(texto: str) -> tuple[str, ...]:
    """Los literales de `method IN ('a', 'b', ...)` en el orden en que aparecen."""
    coincidencia = _LISTA_DEL_CHECK.search(texto)
    if coincidencia is None:
        return ()
    return tuple(re.findall(r"'([^']*)'", coincidencia.group(1)))


def _check_del_modelo() -> str:
    tabla = Payment.__table__
    checks = [
        str(c.sqltext)
        for c in tabla.constraints
        if isinstance(c, CheckConstraint) and str(c.name).endswith("method")
    ]
    assert len(checks) == 1, checks
    return checks[0]


def test_settings_define_los_tres_codigos_fijos() -> None:
    assert PAYMENT_METHOD_CODES == ESPERADOS
    assert tuple(PaymentMethodsSettings.model_fields) == ESPERADOS


def test_el_literal_de_payments_coincide() -> None:
    assert get_args(PaymentMethod) == PAYMENT_METHOD_CODES


def test_las_constantes_del_modelo_coinciden() -> None:
    assert PAYMENT_METHODS == PAYMENT_METHOD_CODES


def test_el_check_del_modelo_coincide() -> None:
    assert codigos_del_check(_check_del_modelo()) == PAYMENT_METHOD_CODES


def test_el_check_de_la_migracion_0010_coincide() -> None:
    if not MIGRACION.is_file():
        pytest.fail(f"no existe {MIGRACION.name}: la escribe el Verde de S3-B3")
    assert codigos_del_check(MIGRACION.read_text(encoding="utf-8")) == PAYMENT_METHOD_CODES


def test_el_lector_del_check_ve_la_lista_y_el_orden() -> None:
    """Control: si el lector devolviera siempre `()`, las comparaciones fallarían por otra razón;
    si ignorara el orden, un cambio de orden pasaría."""
    assert codigos_del_check("CHECK (method IN ('cash', 'nequi', 'breb'))") == ESPERADOS
    assert codigos_del_check("\"method IN ('breb','cash')\"") == ("breb", "cash")
    assert codigos_del_check("amount_cop BETWEEN 1 AND 10") == ()
