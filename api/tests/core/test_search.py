"""`core/search.py` y `core/db.violated_constraint` (revisión Python H3).

Las copias de `escape_like`/`LIKE_ESCAPE` (auth, members, plans), el plegado de tildes (members y
plans, con una tabla incompleta: sin c-cedilla, a-diéresis ni e-circunfleja), la limpieza del
término y el patrón "nombre del índice in str(error.orig)" viven ahora en `core`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Text, literal, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import violated_constraint
from app.core.search import (
    ACCENTED,
    LIKE_ESCAPE,
    clean_query,
    contains_pattern,
    escape_like,
    sql_fold,
    strip_accents,
)

B = chr(92)  # barra invertida, sin escapes en el fuente


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("50%", "50" + B + "%"),
        ("a_b", "a" + B + "_b"),
        ("c:" + B + "x", "c:" + B * 2 + "x"),
        (B + "%_", B * 3 + "%" + B + "_"),
        ("", ""),
    ],
)
def test_escape_like_escapa_la_barra_primero(entrada: str, esperado: str) -> None:
    assert LIKE_ESCAPE == "\\"
    assert escape_like(entrada) == esperado


def test_contains_pattern_envuelve_el_termino_escapado() -> None:
    assert contains_pattern("10%_x") == "%10" + B + "%" + B + "_x%"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Peña", "pena"),
        ("FRANÇOIS", "francois"),
        ("Müller", "muller"),
        ("Hélène Côté", "helene cote"),
        ("Ñandú", "nandu"),
        ("e\u0301", "e"),
        ("Zoë", "zoe"),
    ],
)
def test_strip_accents_pliega_tildes_y_mayusculas(entrada: str, esperado: str) -> None:
    assert strip_accents(entrada) == esperado


def test_la_tabla_de_sql_cubre_la_lista_de_la_revision() -> None:
    for letra in "áéíóúüñàèìòùâêîôûäëïöç":
        assert letra in ACCENTED and letra.upper() in ACCENTED, letra


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [(None, ""), ("  ", ""), (" Jose\u0301 ", "José"), ("a\x00b\x1f", "ab"), ("\x00", "")],
)
def test_clean_query_nfc_sin_controles_y_recortado(entrada: str | None, esperado: str) -> None:
    assert clean_query(entrada) == esperado


async def test_sql_fold_da_lo_mismo_que_strip_accents(session: AsyncSession) -> None:
    """La tabla de `translate` (también en mayúsculas, por si el `LC_CTYPE` de la base no pliega
    `lower('Á')`) coincide con el plegado de Python para cada letra."""
    palabras = ["Peña", "FRANÇOIS", "Müller", "Hélène Côté", "ÁÉÍÓÚÜÑ", "àèìòù", "Zoë Ïñigo"]
    for palabra in palabras:
        plegada = await session.scalar(select(sql_fold(literal(palabra, Text))))
        assert plegada == strip_accents(palabra), palabra


async def test_violated_constraint_lee_el_nombre_de_asyncpg(session: AsyncSession) -> None:
    await session.execute(
        text("CREATE TEMP TABLE t_h3 (x int CONSTRAINT uq_t_h3_x UNIQUE) ON COMMIT DROP")
    )
    await session.execute(text("INSERT INTO t_h3 VALUES (1)"))
    with pytest.raises(IntegrityError) as excinfo:
        async with session.begin_nested():
            await session.execute(text("INSERT INTO t_h3 VALUES (1)"))
    assert violated_constraint(excinfo.value) == "uq_t_h3_x"


def test_violated_constraint_sin_causa_da_none() -> None:
    error = IntegrityError("INSERT", {}, Exception("sin nombre"))
    assert violated_constraint(error) is None
