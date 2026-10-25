"""`0010_payments` (S3-B3, US-095; blueprint B3; D17, D24, S3-D50).

Padre `0009_membership_freezes`. Tabla `payments.payments`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `membership_id uuid NOT NULL`,
  `member_id uuid NOT NULL` (copia inmutable del socio, D1), `amount_cop bigint NOT NULL`,
  `method text NOT NULL`, `reference text NULL`, `paid_at timestamptz NOT NULL`,
  `registered_by uuid NOT NULL`, `voided boolean NOT NULL DEFAULT false`, `void_reason text NULL`,
  `voided_by uuid NULL`, `voided_at timestamptz NULL`;
- CHECKs (23514; la convención les antepone `ck_payments_`): `amount_range` (1 a 1.000.000.000),
  `method` (`cash`, `nequi`, `breb`), `reference_length` (nula o de 1 a 64), `void_reason_length`
  (hasta 500) y `void_coherent` (las cuatro columnas de anulación juntas y el motivo visible;
  necesita `void_reason IS NOT NULL` explícito: con el texto del blueprint, `btrim(NULL) <> ''`
  es NULL, el CHECK no es falso y un anulado sin motivo entraba, caso `anulado-sin-motivo`);
- índices `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id (membership_id)` e
  `ix_payments_member_paid (member_id, paid_at DESC)`, ninguno único;
- sin FK (ni a otros esquemas ni dentro del propio) y sin triggers propios: la inmutabilidad llega
  con `0011_payments_immutability` (B4), cuyos dos triggers son los únicos de la tabla en head;
el `downgrade` borra índices y tabla y deja el esquema `payments` (lo gestiona `0001`).
Todo con SQL crudo en transacciones que se revierten.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0010_payments"
PADRE = "0009_membership_freezes"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
PAGADO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
INDICES = ("ix_payments_paid_at", "ix_payments_membership_id", "ix_payments_member_paid")

TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "membership_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "amount_cop": ("bigint", "NO"),
    "method": ("text", "NO"),
    "reference": ("text", "YES"),
    "paid_at": (TIMESTAMPTZ, "NO"),
    "registered_by": ("uuid", "NO"),
    "voided": ("boolean", "NO"),
    "void_reason": ("text", "YES"),
    "voided_by": ("uuid", "YES"),
    "voided_at": (TIMESTAMPTZ, "YES"),
}


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:  # alembic.util.CommandError o ResolutionError
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _consultar(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def correr() -> list[asyncpg.Record]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _estado(url: str) -> dict[str, Any]:
    existe = _consultar(url, "SELECT to_regclass('payments.payments') IS NOT NULL AS e")
    esquema = _consultar(url, "SELECT count(*) AS n FROM pg_namespace WHERE nspname = 'payments'")
    salida: dict[str, Any] = {"existe": existe[0]["e"], "esquema": esquema[0]["n"] == 1}
    if not salida["existe"]:
        return salida
    salida["columnas"] = {
        r["column_name"]: (r["data_type"], r["is_nullable"])
        for r in _consultar(
            url,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'payments' AND table_name = 'payments'",
        )
    }
    salida["indices"] = {
        r["indexname"]: r["indexdef"]
        for r in _consultar(
            url,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'payments' AND tablename = 'payments'",
        )
    }
    salida["triggers"] = [
        r["tgname"]
        for r in _consultar(
            url,
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid = 'payments.payments'::regclass AND NOT tgisinternal",
        )
    ]
    salida["fks"] = [
        r["conname"]
        for r in _consultar(
            url,
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'payments.payments'::regclass AND contype = 'f'",
        )
    ]
    return salida


def _pago(**cambios: object) -> dict[str, object]:
    """Pago válido de 120.000 en efectivo, sin anular."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "membership_id": uuid4(),
        "member_id": uuid4(),
        "amount_cop": 120_000,
        "method": "cash",
        "reference": None,
        "paid_at": PAGADO,
        "registered_by": SYSTEM_USER_ID,
    }
    fila.update(cambios)
    return fila


def _anulado(**cambios: object) -> dict[str, object]:
    """Pago anulado completo (las cuatro columnas de anulación)."""
    datos: dict[str, object] = {
        "voided": True,
        "void_reason": "Monto equivocado",
        "voided_by": SYSTEM_USER_ID,
        "voided_at": PAGADO,
    }
    datos.update(cambios)
    return _pago(**datos)


def _insertar(url: str, filas: Sequence[dict[str, object]]) -> list[tuple[str, str | None]]:
    """Cada fila se inserta en su propia transacción revertida: `(sqlstate, constraint_name)` del
    error, o `("", None)` si entró."""

    async def correr() -> list[tuple[str, str | None]]:
        conexion = await asyncpg.connect(_dsn(url))
        salida: list[tuple[str, str | None]] = []
        try:
            for fila in filas:
                columnas = list(fila)
                marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
                sql = (
                    f"INSERT INTO payments.payments ({', '.join(columnas)}) "  # noqa: S608
                    f"VALUES ({marcas})"
                )
                transaccion = conexion.transaction()
                await transaccion.start()
                try:
                    await conexion.execute(sql, *[fila[c] for c in columnas])
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


# Revisión y forma ----------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0009_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    """Desde S3-B4 `0011_payments_immutability` cuelga de esta revisión (D40): ya no es head, pero
    sigue en la cadena que llega a head (la cabeza única la exige `test_single_head`)."""
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    cadena = {r.revision for r in scripts.walk_revisions("base", "heads")}
    assert REVISION in cadena


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert estado["columnas"] == COLUMNAS


def test_voided_es_falso_por_defecto(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = 'payments' AND table_name = 'payments' AND column_name = 'voided'",
    )
    assert filas[0]["column_default"] == "false"


def test_los_tres_indices_no_unicos(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    indices = _estado(migrated_database)["indices"]
    assert set(INDICES) <= set(indices), sorted(indices)
    assert "(paid_at DESC)" in indices["ix_payments_paid_at"]
    assert "(membership_id)" in indices["ix_payments_membership_id"]
    assert "(member_id, paid_at DESC)" in indices["ix_payments_member_paid"]
    assert not [n for n in INDICES if "UNIQUE" in indices[n]]
    assert set(indices) == {*INDICES, "pk_payments"}


def test_sin_fk_y_los_unicos_triggers_son_los_de_0011(
    alembic_config: Config, migrated_database: str
) -> None:
    """Regla de módulos 2: sin FK entre esquemas. `0010` no crea triggers: los de inmutabilidad
    son de `0011` (S3-B4) y en head son exactamente esos dos."""
    _revision_existe(alembic_config)
    estado = _estado(migrated_database)
    assert estado["fks"] == []
    assert sorted(estado["triggers"]) == ["payments_forbid_mutation", "payments_forbid_truncate"]


# Filas válidas, CHECKs y NOT NULL ----------------------------------------------------------------


def test_filas_validas_entran(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    validas = [
        _pago(),
        _pago(amount_cop=1),
        _pago(amount_cop=1_000_000_000, method="nequi"),
        _pago(method="breb", reference="A"),
        _pago(reference="Z" * 64),
        _anulado(),
        _anulado(void_reason="m" * 500),
    ]
    assert _insertar(migrated_database, validas) == [("", None)] * len(validas)


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        ({"amount_cop": 0}, "ck_payments_amount_range"),
        ({"amount_cop": -1}, "ck_payments_amount_range"),
        ({"amount_cop": 1_000_000_001}, "ck_payments_amount_range"),
        ({"method": "tarjeta"}, "ck_payments_method"),
        ({"method": "CASH"}, "ck_payments_method"),
        ({"reference": ""}, "ck_payments_reference_length"),
        ({"reference": "Z" * 65}, "ck_payments_reference_length"),
    ],
    ids=[
        "monto-cero",
        "monto-negativo",
        "mil-millones-y-uno",
        "medio-ajeno",
        "medio-en-mayusculas",
        "referencia-vacia",
        "referencia-de-65",
    ],
)
def test_los_checks_del_pago_rechazan(
    alembic_config: Config,
    migrated_database: str,
    cambios: dict[str, object],
    restriccion: str,
) -> None:
    _revision_existe(alembic_config)
    assert _insertar(migrated_database, [_pago(**cambios)]) == [(CHECK_VIOLATION, restriccion)]


def test_un_motivo_de_501_viola_void_reason_length(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    resultado = _insertar(migrated_database, [_anulado(void_reason="m" * 501)])
    assert resultado == [(CHECK_VIOLATION, "ck_payments_void_reason_length")]


@pytest.mark.parametrize(
    "fila",
    [
        _pago(void_reason="No debería estar"),
        _pago(voided_by=SYSTEM_USER_ID),
        _pago(voided_at=PAGADO),
        _anulado(void_reason=None),
        _anulado(void_reason="   "),
        _anulado(voided_by=None),
        _anulado(voided_at=None),
    ],
    ids=[
        "motivo-sin-anular",
        "quien-sin-anular",
        "cuando-sin-anular",
        "anulado-sin-motivo",
        "anulado-con-motivo-de-espacios",
        "anulado-sin-quien",
        "anulado-sin-cuando",
    ],
)
def test_void_coherent_exige_las_cuatro_columnas_juntas(
    alembic_config: Config, migrated_database: str, fila: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _insertar(migrated_database, [fila]) == [(CHECK_VIOLATION, "ck_payments_void_coherent")]


@pytest.mark.parametrize(
    "columna",
    ["membership_id", "member_id", "amount_cop", "method", "paid_at", "registered_by"],
)
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    resultado = _insertar(migrated_database, [_pago(**{columna: None})])
    assert resultado[0][0] == NOT_NULL_VIOLATION


# Ciclo -------------------------------------------------------------------------------------------


def test_ciclo_de_0010(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    assert _estado(migrated_database) == {"existe": False, "esquema": True}
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert estado["columnas"] == COLUMNAS
    assert set(estado["indices"]) == {*INDICES, "pk_payments"}
