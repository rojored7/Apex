"""`members.rules.effective_channels` (S5-B5, US-123; S5-D31, N-33, S4B-D77). # Rojo B5

Función pura: `effective_channels(active, inactive, has_consent) -> frozenset[str]`.
- sin consentimiento (`data_consent_at` nulo) no se avisa por ningún canal, hagan lo que hagan las
  filas;
- con consentimiento, `whatsapp_link` rige por defecto salvo una fila explícita `active=false`;
- `email` exige una fila `email active=true` (opt-in explícito) Y consentimiento.

Tabla de verdad completa: la fila de `whatsapp_link` (ninguna, activa o inactiva) por la fila de
`email` (ninguna, activa o inactiva) por el consentimiento: 18 combinaciones, con el resultado
escrito a mano (no se calcula con la misma regla que se prueba).
"""

from __future__ import annotations

import pytest

from app.modules.members import rules

WA = "whatsapp_link"
CORREO = "email"
NINGUNA, ACTIVA, INACTIVA = "ninguna", "activa", "inactiva"

# (fila de whatsapp_link, fila de email, consentimiento) -> canales efectivos
TABLA_DE_VERDAD: list[tuple[str, str, bool, frozenset[str]]] = [
    (NINGUNA, NINGUNA, True, frozenset({WA})),
    (NINGUNA, ACTIVA, True, frozenset({WA, CORREO})),
    (NINGUNA, INACTIVA, True, frozenset({WA})),
    (ACTIVA, NINGUNA, True, frozenset({WA})),
    (ACTIVA, ACTIVA, True, frozenset({WA, CORREO})),
    (ACTIVA, INACTIVA, True, frozenset({WA})),
    (INACTIVA, NINGUNA, True, frozenset()),
    (INACTIVA, ACTIVA, True, frozenset({CORREO})),
    (INACTIVA, INACTIVA, True, frozenset()),
    (NINGUNA, NINGUNA, False, frozenset()),
    (NINGUNA, ACTIVA, False, frozenset()),
    (NINGUNA, INACTIVA, False, frozenset()),
    (ACTIVA, NINGUNA, False, frozenset()),
    (ACTIVA, ACTIVA, False, frozenset()),
    (ACTIVA, INACTIVA, False, frozenset()),
    (INACTIVA, NINGUNA, False, frozenset()),
    (INACTIVA, ACTIVA, False, frozenset()),
    (INACTIVA, INACTIVA, False, frozenset()),
]


def _conjuntos(fila_wa: str, fila_correo: str) -> tuple[frozenset[str], frozenset[str]]:
    activos = frozenset(
        canal for canal, fila in ((WA, fila_wa), (CORREO, fila_correo)) if fila == ACTIVA
    )
    inactivos = frozenset(
        canal for canal, fila in ((WA, fila_wa), (CORREO, fila_correo)) if fila == INACTIVA
    )
    return activos, inactivos


@pytest.mark.parametrize(
    ("fila_wa", "fila_correo", "consentimiento", "esperado"),
    TABLA_DE_VERDAD,
    ids=[f"wa-{w}__correo-{c}__consent-{k}" for w, c, k, _ in TABLA_DE_VERDAD],
)
def test_tabla_de_verdad_de_los_canales_efectivos(
    fila_wa: str, fila_correo: str, consentimiento: bool, esperado: frozenset[str]
) -> None:
    # Arrange
    activos, inactivos = _conjuntos(fila_wa, fila_correo)
    # Act
    efectivos = rules.effective_channels(activos, inactivos, consentimiento)
    # Assert
    assert efectivos == esperado


def test_la_tabla_cubre_las_dieciocho_combinaciones_sin_repetir() -> None:
    claves = {(w, c, k) for w, c, k, _ in TABLA_DE_VERDAD}
    assert len(TABLA_DE_VERDAD) == len(claves) == 18


def test_sin_consentimiento_el_resultado_es_vacio_aunque_todo_este_activo() -> None:
    efectivos = rules.effective_channels(frozenset({WA, CORREO}), frozenset(), False)
    assert efectivos == frozenset()


def test_el_resultado_es_un_frozenset() -> None:
    efectivos = rules.effective_channels(frozenset(), frozenset(), True)
    assert isinstance(efectivos, frozenset)


def test_la_funcion_no_modifica_sus_entradas() -> None:
    activos = frozenset({CORREO})
    inactivos = frozenset({WA})
    rules.effective_channels(activos, inactivos, True)
    assert (activos, inactivos) == (frozenset({CORREO}), frozenset({WA}))
