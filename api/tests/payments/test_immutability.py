"""Inmutabilidad de `payments.payments` en la base (S3-B4, US-096; blueprint B4; D13, M-6, L-10).

La función `payments.forbid_mutation()` de `0011_payments_immutability` y sus dos triggers
(`payments_forbid_mutation BEFORE UPDATE OR DELETE FOR EACH ROW` y `payments_forbid_truncate
BEFORE TRUNCATE FOR EACH STATEMENT`, los dos `ENABLE ALWAYS`) dejan pasar una sola transición: la
anulación completa de un pago vigente. Todo lo demás se rechaza con `ERRCODE =
integrity_constraint_violation` y `CONSTRAINT = payments_immutable` (SQLAlchemy lo entrega como
`IntegrityError`; `core.db.violated_constraint` lee el nombre) y el motivo en el mensaje
(`payments_immutable: <motivo>`):
- `delete` (borrar una fila) y `truncate` (vaciar la tabla), antes de leer `OLD`;
- `already_voided`: cualquier `UPDATE` sobre un anulado (segunda anulación, `voided` de `true` a
  `false`, un `UPDATE` sin cambios);
- `column`: cambia alguna de las 10 columnas protegidas (`id`, `membership_id`, `member_id`,
  `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by`),
  aunque la misma sentencia llene las de anulación;
- `incomplete_void`: el `UPDATE` de un vigente que no deja `voided = true` con motivo visible,
  `voided_by` y `voided_at` (también el que solo toca `updated_at`).
`updated_at` es libre: la anulación completa lo puede cambiar. Bajo
`session_replication_role = replica` los rechazos siguen (M-6, `ENABLE ALWAYS`).

Todo con SQL crudo dentro de la sesión de la prueba: cada caso en su `SAVEPOINT`
(`session.begin_nested()`), que el rechazo revierte, y relectura de la fila después.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import violated_constraint
from app.modules.payments import service

SYSTEM_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000001")
ANULADOR: Final = UUID("0000000a-0000-4000-8000-00000000b401")
PAGADO: Final = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
ANULADO_EN: Final = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
CONSTRAINT: Final = "payments_immutable"

PROTEGIDAS: Final = (
    "id",
    "membership_id",
    "member_id",
    "amount_cop",
    "method",
    "reference",
    "paid_at",
    "registered_by",
    "created_at",
    "created_by",
)
DE_ANULACION: Final = ("voided", "void_reason", "voided_by", "voided_at")
NUEVOS: Final[dict[str, object]] = {
    "id": uuid4(),
    "membership_id": uuid4(),
    "member_id": uuid4(),
    "amount_cop": 1,
    "method": "nequi",
    "reference": "OTRA-9",
    "paid_at": PAGADO - timedelta(days=1),
    "registered_by": uuid4(),
    "created_at": PAGADO - timedelta(days=1),
    "created_by": uuid4(),
}

_INSERTAR = text(
    "INSERT INTO payments.payments (id, created_by, membership_id, member_id, amount_cop, "
    "method, reference, paid_at, registered_by, voided, void_reason, voided_by, voided_at) "
    "VALUES (:id, :created_by, :membership_id, :member_id, 120000, 'cash', 'REC-1', :paid_at, "
    ":registered_by, :voided, :void_reason, :voided_by, :voided_at)"
)
_LEER = text("SELECT * FROM payments.payments WHERE id = :id")
_ANULAR = (
    "UPDATE payments.payments SET voided = true, void_reason = :motivo, voided_by = :quien, "
    "voided_at = :cuando WHERE id = :id"
)


async def _insertar(session: AsyncSession, *, anulado: bool = False) -> UUID:
    """Un pago de 120.000 en efectivo (`REC-1`); anulado completo si se pide."""
    pago_id = uuid4()
    await session.execute(
        _INSERTAR,
        {
            "id": pago_id,
            "created_by": SYSTEM_USER_ID,
            "membership_id": uuid4(),
            "member_id": uuid4(),
            "paid_at": PAGADO,
            "registered_by": SYSTEM_USER_ID,
            "voided": anulado,
            "void_reason": "Monto mal digitado" if anulado else None,
            "voided_by": SYSTEM_USER_ID if anulado else None,
            "voided_at": PAGADO if anulado else None,
        },
    )
    return pago_id


async def _leer(session: AsyncSession, pago_id: UUID) -> dict[str, Any] | None:
    fila = (await session.execute(_LEER, {"id": pago_id})).mappings().first()
    return dict(fila) if fila is not None else None


async def _rechazo(session: AsyncSession, sql: str, parametros: dict[str, Any]) -> IntegrityError:
    """Corre `sql` en su SAVEPOINT; debe fallar con `IntegrityError` (el SAVEPOINT se revierte)."""
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(text(sql), parametros)
    return error.value


def _es_rechazo(error: IntegrityError, motivo: str) -> None:
    assert violated_constraint(error) == CONSTRAINT, str(error)
    assert f"{CONSTRAINT}: {motivo}" in str(error), str(error)


def _anulacion(pago_id: UUID, **cambios: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": pago_id,
        "motivo": "Monto mal digitado",
        "quien": ANULADOR,
        "cuando": ANULADO_EN,
    }
    datos.update(cambios)
    return datos


def test_la_constante_del_service_es_la_de_la_base() -> None:
    assert service.IMMUTABLE_CONSTRAINT == CONSTRAINT
    assert "IMMUTABLE_CONSTRAINT" in service.__all__


# Borrar y vaciar -----------------------------------------------------------------------------


async def test_borrar_un_pago_se_rechaza(session: AsyncSession) -> None:
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    error = await _rechazo(session, "DELETE FROM payments.payments WHERE id = :id", {"id": pago_id})
    _es_rechazo(error, "delete")
    assert await _leer(session, pago_id) == antes


async def test_borrar_un_pago_anulado_tambien_se_rechaza(session: AsyncSession) -> None:
    pago_id = await _insertar(session, anulado=True)
    error = await _rechazo(session, "DELETE FROM payments.payments WHERE id = :id", {"id": pago_id})
    _es_rechazo(error, "delete")
    assert await _leer(session, pago_id) is not None


async def test_vaciar_la_tabla_se_rechaza(session: AsyncSession) -> None:
    pago_id = await _insertar(session)
    error = await _rechazo(session, "TRUNCATE payments.payments", {})
    _es_rechazo(error, "truncate")
    assert await _leer(session, pago_id) is not None


# Columnas protegidas -------------------------------------------------------------------------


@pytest.mark.parametrize("columna", PROTEGIDAS)
async def test_cambiar_una_columna_protegida_se_rechaza(
    session: AsyncSession, columna: str
) -> None:
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    sql = f"UPDATE payments.payments SET {columna} = :valor WHERE id = :id"  # noqa: S608
    error = await _rechazo(session, sql, {"valor": NUEVOS[columna], "id": pago_id})
    _es_rechazo(error, "column")
    assert await _leer(session, pago_id) == antes


@pytest.mark.parametrize("columna", PROTEGIDAS)
async def test_cambiar_una_columna_protegida_junto_con_la_anulacion_se_rechaza(
    session: AsyncSession, columna: str
) -> None:
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    sql = (
        f"UPDATE payments.payments SET {columna} = :valor, voided = true, "  # noqa: S608
        "void_reason = :motivo, voided_by = :quien, voided_at = :cuando WHERE id = :id"
    )
    error = await _rechazo(session, sql, _anulacion(pago_id, valor=NUEVOS[columna]))
    _es_rechazo(error, "column")
    assert await _leer(session, pago_id) == antes


# Anulación ---------------------------------------------------------------------------------------


async def test_la_anulacion_completa_se_acepta_con_updated_at_y_el_monto_intacto(
    session: AsyncSession,
) -> None:
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    assert antes is not None
    nuevo_updated_at = antes["updated_at"] + timedelta(minutes=5)
    async with session.begin_nested():
        await session.execute(
            text(_ANULAR.replace("WHERE", ", updated_at = :updated_at WHERE")),
            _anulacion(pago_id, updated_at=nuevo_updated_at),
        )
    despues = await _leer(session, pago_id)
    assert despues is not None
    assert (despues["voided"], despues["void_reason"]) == (True, "Monto mal digitado")
    assert (despues["voided_by"], despues["voided_at"]) == (ANULADOR, ANULADO_EN)
    assert despues["updated_at"] == nuevo_updated_at != antes["updated_at"]
    assert {c: despues[c] for c in PROTEGIDAS} == {c: antes[c] for c in PROTEGIDAS}
    assert despues["amount_cop"] == 120_000


@pytest.mark.parametrize(
    "cambios",
    [
        {"motivo": None},
        {"motivo": "   "},
        {"motivo": ""},
        {"quien": None},
        {"cuando": None},
    ],
    ids=["sin-motivo", "motivo-de-espacios", "motivo-vacio", "sin-voided-by", "sin-voided-at"],
)
async def test_una_anulacion_incompleta_se_rechaza(
    session: AsyncSession, cambios: dict[str, Any]
) -> None:
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    error = await _rechazo(session, _ANULAR, _anulacion(pago_id, **cambios))
    _es_rechazo(error, "incomplete_void")
    assert await _leer(session, pago_id) == antes


async def test_tocar_solo_updated_at_de_un_vigente_es_una_anulacion_incompleta(
    session: AsyncSession,
) -> None:
    """`updated_at` es libre, pero el único `UPDATE` que admite un vigente es su anulación."""
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    error = await _rechazo(
        session,
        "UPDATE payments.payments SET updated_at = clock_timestamp() WHERE id = :id",
        {"id": pago_id},
    )
    _es_rechazo(error, "incomplete_void")
    assert await _leer(session, pago_id) == antes


async def test_poner_voided_false_explicito_sobre_un_vigente_es_incompleta(
    session: AsyncSession,
) -> None:
    pago_id = await _insertar(session)
    error = await _rechazo(
        session, "UPDATE payments.payments SET voided = false WHERE id = :id", {"id": pago_id}
    )
    _es_rechazo(error, "incomplete_void")


async def test_anular_dos_veces_se_rechaza(session: AsyncSession) -> None:
    pago_id = await _insertar(session)
    async with session.begin_nested():
        await session.execute(text(_ANULAR), _anulacion(pago_id))
    antes = await _leer(session, pago_id)
    error = await _rechazo(
        session, _ANULAR, _anulacion(pago_id, motivo="Otra vez", cuando=ANULADO_EN + timedelta(1))
    )
    _es_rechazo(error, "already_voided")
    assert await _leer(session, pago_id) == antes


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE payments.payments SET voided = false, void_reason = NULL, voided_by = NULL, "
        "voided_at = NULL WHERE id = :id",
        "UPDATE payments.payments SET voided = true WHERE id = :id",
        "UPDATE payments.payments SET updated_at = clock_timestamp() WHERE id = :id",
        "UPDATE payments.payments SET void_reason = 'Otro motivo' WHERE id = :id",
    ],
    ids=["de-true-a-false", "sin-cambios", "solo-updated-at", "otro-motivo"],
)
async def test_cualquier_update_sobre_un_anulado_se_rechaza(
    session: AsyncSession, sql: str
) -> None:
    pago_id = await _insertar(session, anulado=True)
    antes = await _leer(session, pago_id)
    error = await _rechazo(session, sql, {"id": pago_id})
    _es_rechazo(error, "already_voided")
    assert await _leer(session, pago_id) == antes


# Réplica (M-6) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "motivo"),
    [
        ("UPDATE payments.payments SET amount_cop = 1 WHERE id = :id", "column"),
        ("DELETE FROM payments.payments WHERE id = :id", "delete"),
    ],
    ids=["update", "delete"],
)
async def test_bajo_replica_los_rechazos_siguen(
    session: AsyncSession, sql: str, motivo: str
) -> None:
    """`ENABLE ALWAYS`: `session_replication_role = replica` no salta los triggers."""
    pago_id = await _insertar(session)
    antes = await _leer(session, pago_id)
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL session_replication_role = replica"))
            await session.execute(text(sql), {"id": pago_id})
    _es_rechazo(error.value, motivo)
    assert await _leer(session, pago_id) == antes
    rol = await session.scalar(text("SHOW session_replication_role"))
    assert rol == "origin"  # el SAVEPOINT revertido deshizo el SET LOCAL


# Forma de la tabla y de la función (US-096 T4, L-10) ------------------------------------------


async def test_las_columnas_son_las_protegidas_las_de_anulacion_y_updated_at(
    session: AsyncSession,
) -> None:
    """Una columna nueva en `payments.payments` obliga a decidir si el trigger la protege."""
    columnas = await session.scalars(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'payments' AND table_name = 'payments'"
        )
    )
    assert set(columnas) == {*PROTEGIDAS, *DE_ANULACION, "updated_at"}


async def test_la_funcion_es_security_invoker_plpgsql_con_search_path_fijo(
    session: AsyncSession,
) -> None:
    """`pg_get_functiondef` nunca imprime `SECURITY INVOKER` (es el valor por defecto): se lee el
    catálogo (`prosecdef`, `lanname`, `proconfig`), como en `0008` y `0009`."""
    fila = (
        (
            await session.execute(
                text(
                    "SELECT p.prosecdef, p.proconfig, l.lanname, pg_get_functiondef(p.oid) AS def "
                    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "JOIN pg_language l ON l.oid = p.prolang "
                    "WHERE n.nspname = 'payments' AND p.proname = 'forbid_mutation'"
                )
            )
        )
        .mappings()
        .first()
    )
    assert fila is not None, "no existe payments.forbid_mutation()"
    assert fila["prosecdef"] is False
    assert fila["lanname"] == "plpgsql"
    assert list(fila["proconfig"] or []) == ["search_path=pg_catalog"]
    definicion = " ".join(str(fila["def"]).split())
    assert "EXCEPTION WHEN OTHERS" not in definicion.upper()
    assert "IS DISTINCT FROM" in definicion.upper()
    for columna in PROTEGIDAS:
        assert f"NEW.{columna}" in definicion, columna
    assert "integrity_constraint_violation" in definicion
    assert CONSTRAINT in definicion
