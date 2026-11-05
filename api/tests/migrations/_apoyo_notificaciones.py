"""Apoyo de `test_0017_*` y `test_0018_*` (S5-B6): SQL crudo sobre `db_test`.

- `consultar(url, sql, *args)`: filas de una consulta (conexión propia).
- `resultados(url, escenarios)`: cada escenario (lista de pasos `(sql, args)`) corre en una
  transacción que siempre se revierte; da `(sqlstate, constraint_name)` del primer error o
  `("", None)`.
- `plantilla(**cambios)` y `regla(template_id, **cambios)`: filas válidas por defecto.
- `aviso(rule_id, **cambios)` (S5-B7): fila válida de `notifications.notifications`.
- `insert(tabla, fila)`: el paso `INSERT` de una fila de `notifications.<tabla>`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import asyncpg

SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
TIMESTAMPTZ = "timestamp with time zone"

Paso = tuple[str, Sequence[Any]]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def consultar(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def correr() -> list[asyncpg.Record]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(correr())


def existe(url: str, tabla: str) -> bool:
    return bool(consultar(url, "SELECT to_regclass($1) IS NOT NULL AS e", tabla)[0]["e"])


def columnas(url: str, tabla: str) -> dict[str, tuple[str, str]]:
    esquema, nombre = tabla.split(".")
    return {
        r["column_name"]: (r["data_type"], r["is_nullable"])
        for r in consultar(
            url,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = $1 AND table_name = $2",
            esquema,
            nombre,
        )
    }


def plantilla(**cambios: object) -> dict[str, object]:
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "name": f"Plantilla {uuid4().hex[:8]}",
        "subject": "Asunto",
        "body": "Hola {nombre}",
    }
    fila.update(cambios)
    return fila


def regla(template_id: object, **cambios: object) -> dict[str, object]:
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "name": "Regla",
        "trigger": "membership_expiring",
        "offset_days": -3,
        "channel": "whatsapp_link",
        "template_id": template_id,
        "is_active": True,
    }
    fila.update(cambios)
    return fila


def insert(tabla: str, fila: dict[str, object]) -> Paso:
    columnas_ = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas_) + 1))
    sql = f"INSERT INTO notifications.{tabla} ({', '.join(columnas_)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in columnas_]


def resultados(url: str, escenarios: Sequence[Sequence[Paso]]) -> list[tuple[str, str | None]]:
    async def correr() -> list[tuple[str, str | None]]:
        conexion = await asyncpg.connect(_dsn(url))
        salida: list[tuple[str, str | None]] = []
        try:
            for pasos in escenarios:
                transaccion = conexion.transaction()
                await transaccion.start()
                try:
                    for sql, args in pasos:
                        await conexion.execute(sql, *args)
                except asyncpg.PostgresError as error:
                    salida.append((str(error.sqlstate), getattr(error, "constraint_name", None)))
                else:
                    salida.append(("", None))
                finally:
                    await transaccion.rollback()
            return salida
        finally:
            await conexion.close()

    return asyncio.run(correr())


def aviso(rule_id: object, **cambios: object) -> dict[str, object]:
    """Fila válida de `notifications.notifications` (S5-B7); ids de socio y membresía sueltos."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "rule_id": rule_id,
        "member_id": uuid4(),
        "membership_id": uuid4(),
        "target_date": date(2026, 11, 5),
        "channel": "whatsapp_link",
        "status": "pending",
        "rendered_subject": "Asunto",
        "rendered_body": "Hola Ana",
    }
    fila.update(cambios)
    return fila
