"""`core.pagination.uuid_array` y `any_uuids` (PM4 de la revisión de Fase 4 del Sprint 3).

Antes había tres copias (`memberships/queries._ids_param`, `members/service._uuids` y un literal
en `payments/rules`). Un solo parámetro ligado de tipo `uuid[]` (S3-D60), con los ids ordenados
(la sentencia no depende del orden de un `set`), y `= ANY(...)` sobre él.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Uuid, column, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.pagination import any_uuids, uuid_array

UNO = UUID("00000000-0000-4000-8000-000000000001")
DOS = UUID("00000000-0000-4000-8000-000000000002")


def _compilar(consulta: object) -> object:
    return consulta.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]


def test_uuid_array_es_un_solo_parametro_uuid_array_ordenado() -> None:
    arreglo = uuid_array({DOS, UNO})
    assert isinstance(arreglo.type, ARRAY)
    assert isinstance(arreglo.type.item_type, Uuid)
    compilado = _compilar(select(arreglo))
    assert list(compilado.params.values()) == [[UNO, DOS]]  # type: ignore[attr-defined]


def test_any_uuids_compila_a_igual_a_any_con_un_parametro() -> None:
    consulta = select(column("id")).where(column("id") == any_uuids([DOS, UNO]))
    compilado = _compilar(consulta)
    assert "= ANY (%(param_1)s" in str(compilado)
    assert list(compilado.params.values()) == [[UNO, DOS]]  # type: ignore[attr-defined]
