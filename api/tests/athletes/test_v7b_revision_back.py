"""Correcciones de backend de la revisión de Fase 4 (S9-V7b): lo que cambia de comportamiento o de
forma verificable.

- M1: `rederive_member` ya no tiene el parámetro `strict` (YAGNI: la rama blanda no tenía llamador).
- M2: las filas del resumen son una `NamedTuple` (`_SummaryRow`), no `Any`.
- M3: las consultas compartidas viven en `athletes/queries.py` y `records.py` no tiene imports
  perezosos (se rompe el ciclo con `derive.py`).
- L1 (bd): `void_metric` toma `voided_at` del reloj de la base: nunca queda antes de `created_at`
  aunque el reloj de la aplicación vaya atrás.
- L3 (bd): `result_ids_with_record` y la lectura de `_invalidate` usan
  `uq_personal_records_result_kind` con el plan genérico.
- L5/L6/L7/L9/L10: duplicados, campo sin uso, tamaño de `sending.py`, constantes y nombres.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, get_type_hints
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.modules.athletes import derive, metrics, reads, rules, service
from app.modules.athletes.models import PersonalRecord
from tests.athletes._apoyo import alta, anular, fila_cruda
from tests.athletes._apoyo_invalidar import escena_serie
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_record
from tests.factories.explain import capturar_sql
from tests.notifications._apoyo_avisos import socio

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
ATHLETES = SRC / "modules" / "athletes"

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"))


# M1 ------------------------------------------------------------------------------------------


def test_rederive_member_no_tiene_el_parametro_strict() -> None:
    assert "strict" not in inspect.signature(service.rederive_member).parameters
    assert "strict" not in inspect.signature(derive.rederive_member).parameters


# M2 ------------------------------------------------------------------------------------------


def test_las_filas_del_resumen_son_una_namedtuple_con_las_columnas_del_resumen() -> None:
    fila = reads._SummaryRow
    assert issubclass(fila, tuple) and hasattr(fila, "_fields")
    assert fila._fields == tuple(c.key for c in reads._SUMMARY_COLUMNS)


# M3 ------------------------------------------------------------------------------------------


def test_las_consultas_compartidas_viven_en_queries_y_no_hay_imports_en_funciones() -> None:
    from app.modules.athletes import queries

    for nombre in ("current_rm", "current_benchmark", "result_ids_with_record", "row_of"):
        assert callable(getattr(queries, nombre)), nombre
    assert "KIND_SQL" in vars(queries)
    for ruta in (ATHLETES / "records.py", ATHLETES / "derive.py", ATHLETES / "reads.py"):
        for nodo in ast.walk(_arbol(ruta)):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                internos = [n for n in ast.walk(nodo) if isinstance(n, ast.Import | ast.ImportFrom)]
                assert internos == [], f"{ruta.name}:{nodo.name} importa dentro de la función"
    assert "athletes.records" not in (ATHLETES / "derive.py").read_text(encoding="utf-8")


# L4 / L5 / L6 --------------------------------------------------------------------------------


def test_un_solo_tipo_de_objetivo_y_kind_es_un_literal() -> None:
    assert hasattr(rules, "Objective") and hasattr(rules, "RecordKind")
    assert get_type_hints(rules.RecordRow)["kind"] == rules.RecordKind
    assert get_type_hints(rules.RecordDraft)["kind"] == rules.RecordKind
    for ruta in (ATHLETES / "records.py", ATHLETES / "derive.py"):
        fuente = ruta.read_text(encoding="utf-8")
        assert "class _Objective" not in fuente and "class _Target" not in fuente, ruta.name


def test_helpers_unicos_de_marca_alerta_y_rol() -> None:
    from app.modules.athletes import alerts

    assert callable(rules._score_of) and callable(alerts.safe_alert)
    assert metrics.ADMIN_ROLE is rules.ADMIN_ROLE
    assert "ADMIN_ROLE: Final" not in (ATHLETES / "metrics.py").read_text(encoding="utf-8")
    for nombre in ("derive.py", "reads.py"):
        fuente = (ATHLETES / nombre).read_text(encoding="utf-8")
        assert "alerta omitida" not in fuente, nombre  # el único sitio es `alerts.safe_alert`


def test_el_resumen_usa_el_conteo_del_digest() -> None:
    fuente = (ATHLETES / "reads.py").read_text(encoding="utf-8")
    assert "digest.current_rms" in fuente and "current_rms=len(rms)" not in fuente


# L7 / L8 / L9 / L10 -------------------------------------------------------------------------


def test_sending_se_partio_y_queda_por_debajo_de_800_lineas() -> None:
    ruta = SRC / "modules" / "notifications" / "sending.py"
    assert len(ruta.read_text(encoding="utf-8").splitlines()) <= 760
    assert (SRC / "modules" / "notifications" / "sending_queries.py").exists()


def test_reveal_alert_window_va_antes_de_su_uso_en_ratelimit() -> None:
    fuente = (SRC / "core" / "ratelimit.py").read_text(encoding="utf-8")
    assert fuente.index("REVEAL_ALERT_WINDOW_S: Final") < fuente.index("REVEAL_HOUR_BUCKET")


def test_busy_wait_es_final_y_se_pasa_como_parametro() -> None:
    from app.cli_ops import derive_records

    fuente = (SRC / "cli_ops" / "derive_records.py").read_text(encoding="utf-8")
    assert "BUSY_WAIT_S: Final" in fuente
    assert "busy_wait_s" in inspect.signature(derive_records._one_member).parameters
    assert "busy_wait_s" in inspect.signature(derive_records._derive).parameters


def test_el_service_de_avisos_no_tapa_el_builtin_list() -> None:
    from app.modules.notifications import service as avisos

    assert callable(avisos.list_) and "list" not in vars(avisos)


# L1 (bd): el reloj de la base ---------------------------------------------------------------


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_anular_con_el_reloj_de_la_app_atrasado_no_deja_voided_at_antes_de_created_at(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, admin.id, miembro.id)
    member_id, metric_id = miembro.id, medicion.id
    reloj.advance(days=-30)  # el reloj de la aplicación va MUY detrás de `created_at`

    await anular(session, admin.id, member_id, metric_id)

    fila = await fila_cruda(session, metric_id)
    assert fila["voided_at"] >= fila["created_at"]
    assert fila["updated_at"] >= fila["created_at"]


# L3 (bd): planes con índice -------------------------------------------------------------------


async def _plan_generico(session: AsyncSession, sql: str, parametros: tuple[Any, ...]) -> str:
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    nombre = f"p_{uuid4().hex[:8]}"
    await conexion.exec_driver_sql(f"PREPARE {nombre} AS {sql}")

    def literal(valor: Any) -> str:
        if isinstance(valor, list | tuple | set):
            return "'{" + ",".join(str(v) for v in valor) + "}'"
        return f"'{valor}'"

    argumentos = ", ".join(literal(p) for p in parametros)
    filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE {nombre}({argumentos})")
    return "\n".join(str(f[0]) for f in filas.all())


async def test_plan_de_result_ids_with_record_usa_un_indice_sin_seq_scan(
    session: AsyncSession,
) -> None:
    """El plan genérico elige `ix_personal_records_member_date` (el filtro por socio) y no el único
    `uq_personal_records_result_kind`: la revisión V7 suponía el segundo; se fija lo medido."""
    from app.modules.athletes import queries

    with capturar_sql(session, "athletes.personal_records") as vistas:
        await queries.result_ids_with_record(session, uuid4(), "rm", [uuid4(), uuid4()])
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, tuple(parametros))

    assert "Index Scan" in plan or "Bitmap Index Scan" in plan, plan
    assert "Seq Scan" not in plan, plan


async def test_plan_de_la_lectura_de_invalidate_usa_uq_result_kind(session: AsyncSession) -> None:
    e = await escena_serie(session, "2026-10-12")
    ajeno: PersonalRecord = await make_record(session, kind="rm", source="derived", value_g=90_000)
    assert ajeno.result_id is not None
    with actor_scope(e.coach), capturar_sql(session, "athletes.personal_records") as vistas:
        await derive._invalidate(
            session,
            member_id=e.socio_id,
            result_id=ajeno.result_id,
            reason="voided",
            by_result=None,
        )
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, tuple(parametros))

    assert "uq_personal_records_result_kind" in plan, plan
    assert "Seq Scan" not in plan, plan
