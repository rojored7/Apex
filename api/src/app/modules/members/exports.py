"""Exportación de socios a CSV (S5-B12, US-138; S5-D41, S5-D60, S5-D82, S5-D246 a S5-D248; M-10).
Privado de `members`: solo lo importa `members/service.py` (`export_members`).

Flujo (S5-D41), todo ANTES de enviar cabeceras: `prepare` cuenta las filas que cumplen los filtros
(más que el tope: `ExportTooLarge`, 422), comprueba que el bus de cifrado esté listo (si no,
`CryptoUnavailable`, 503) y escribe la fila de apertura de la auditoría (acción `export`, tabla
`members.members`, `record_id` = id de la exportación, `after` con filtros estructurados, `has_q`,
filas, columnas e IP; nunca el texto de `q`). Después responde con el generador `_cuerpo`.

El generador abre su PROPIA sesión por lote con `db.get_sessionmaker()` al correr (la de la
petición ya cerró, S5-D246), lee 500 socios por la llave `(created_at, id)` sin OFFSET, los
descifra con `_decrypt_batch` (segunda y última puerta de `types.reveal` fuera de `detail.py`,
`test_reveal_single_door`: una fila `decrypt` con propósito `export` y `count = N` por clase y
lote en `crypto_ops`, M-10) y entrega cada lote. Al terminar, abortar o cortarse el cliente escribe
la fila de cierre `{completed, rows_sent}` en un `finally` blindado contra la cancelación (S5-D248).

Solo salen las nueve columnas de N-29: `birth_date` y `emergency_contact` no se descifran. Los
textos libres pasan por `escape_formula` (L-6); las fechas salen en hora de Bogotá.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, Final
from uuid import UUID, uuid4

import anyio
from sqlalchemy import Select, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit, db
from app.core.alerts import alert
from app.core.clock import BOGOTA, current_clock
from app.core.context import actor_scope
from app.core.crypto import bus, types
from app.core.crypto.keyring import current_keyring
from app.core.export import ExportStream, ExportTooLarge, csv_header, csv_rows, escape_formula
from app.modules.members.models import Member
from app.modules.members.schemas import MemberExportQuery
from app.modules.memberships.schemas import MemberMembership

logger = logging.getLogger("app.members.export")

BATCH_SIZE: Final = 500
HEADER: Final[tuple[str, ...]] = (
    "nombres",
    "apellidos",
    "documento",
    "telefono",
    "correo",
    "estado_membresia",
    "plan",
    "vence",
    "creado",
)
TABLE: Final = "members.members"
PURPOSE: Final = "export"
CAMPOS_CIFRADOS: Final[tuple[str, ...]] = ("document", "phone", "email")
SIN_MEMBRESIA: Final = "none"
FECHA_HORA: Final = "%Y-%m-%d %H:%M"

Fila = list[str | int]
EstadoDe = Callable[[AsyncSession, list[UUID]], Awaitable[dict[UUID, MemberMembership]]]
Llave = tuple[datetime, UUID]


def _decrypt_batch(socios: Sequence[Member]) -> dict[UUID, dict[str, Any]]:
    """Documento, teléfono y correo en claro de cada socio del lote (los nulos no se descifran).
    Todo el lote va dentro de `bus.batch`: una fila `decrypt` por clase con `purpose="export"`."""
    claros: dict[UUID, dict[str, Any]] = {}
    with bus.batch("decrypt", None):
        for socio in socios:
            claros[socio.id] = {
                campo: types.reveal(socio, campo, PURPOSE)
                for campo in CAMPOS_CIFRADOS
                if getattr(socio, campo) is not None
            }
    return claros


async def _contar(session: AsyncSession, consulta: Select[Member] | None) -> int:
    if consulta is None:
        return 0
    return int(await session.scalar(select(func.count()).select_from(consulta.subquery())) or 0)


def _texto(valor: object) -> str:
    return "" if valor is None else escape_formula(str(valor))


def _fila(socio: Member, claros: dict[str, Any], membresia: MemberMembership | None) -> Fila:
    """Las nueve columnas de N-29 de un socio; `membresia` es `MemberMembership | None`."""
    return [
        _texto(socio.first_name),
        _texto(socio.last_name),
        _texto(claros.get("document")),
        _texto(claros.get("phone")),
        _texto(claros.get("email")),
        SIN_MEMBRESIA if membresia is None else membresia.status,
        "" if membresia is None else _texto(membresia.plan_name),
        "" if membresia is None or membresia.end_date is None else membresia.end_date.isoformat(),
        socio.created_at.astimezone(BOGOTA).strftime(FECHA_HORA),
    ]


def _siguiente(consulta: Select[Member], despues_de: Llave | None) -> Select[Member]:
    """El lote que sigue a `despues_de` por la llave `(created_at, id)`; sin OFFSET."""
    if despues_de is not None:
        actual = tuple_(Member.created_at, Member.id)
        pasado = tuple_(
            literal(despues_de[0], Member.created_at.type), literal(despues_de[1], Member.id.type)
        )
        consulta = consulta.where(actual > pasado)
    return consulta.order_by(Member.created_at, Member.id).limit(BATCH_SIZE)


async def _leer_lote(
    consulta: Select[Member] | None, despues_de: Llave | None, by: UUID, estado_de: EstadoDe
) -> tuple[list[Fila], Llave | None]:
    """Un lote con sesión propia: socios, descifrado en bloque y estado de membresía; el commit
    vuelca las filas de `crypto_ops`. Sin lote devuelve `([], None)`."""
    if consulta is None:
        return [], None
    with actor_scope(by):
        async with db.get_sessionmaker()() as sesion:
            socios = list(await sesion.scalars(_siguiente(consulta, despues_de)))
            if not socios:
                return [], None
            claros = _decrypt_batch(socios)
            estados = await estado_de(sesion, [s.id for s in socios])
            await sesion.commit()
    filas = [_fila(s, claros[s.id], estados.get(s.id)) for s in socios]
    return filas, (socios[-1].created_at, socios[-1].id)


async def _cerrar(export_id: UUID, by: UUID, *, completed: bool, rows_sent: int) -> None:
    """La fila de cierre en sesión propia; blindada contra la cancelación del cliente (S5-D248).
    Un fallo no tapa el motivo del corte: se registra y se avisa."""
    with anyio.CancelScope(shield=True):
        try:
            async with db.get_sessionmaker()() as sesion:
                await audit.record(
                    sesion,
                    action="export",
                    table_name=TABLE,
                    record_id=export_id,
                    before=None,
                    after={"completed": completed, "rows_sent": rows_sent},
                    user_id=by,
                )
                await sesion.commit()
        except Exception as error:
            tipo = type(error).__name__
            logger.error("members export: cierre sin registrar", extra={"error_type": tipo})
            alert("export_close_lost", table=TABLE, error_type=tipo)


async def _cuerpo(
    consulta: Select[Member] | None,
    export_id: UUID,
    by: UUID,
    estado_de: EstadoDe,
    max_rows: int,
) -> AsyncIterator[bytes]:
    """El CSV en streaming: cabecera y un fragmento por lote (S5-D247); el cierre en `finally`."""
    enviadas = 0
    completo = False
    try:
        yield csv_header(HEADER)
        despues_de: Llave | None = None
        while True:
            filas, despues_de = await _leer_lote(consulta, despues_de, by, estado_de)
            if not filas:
                completo = True
                break
            sobran = len(filas) > max_rows - enviadas
            if sobran:  # altas concurrentes tras el conteo: el tope también rige aquí (S5-D253)
                filas = filas[: max_rows - enviadas]
            enviadas += len(filas)  # ya en manos del consumidor al suspender en `yield`
            if filas:
                yield csv_rows(filas)
            if sobran:
                break
            if len(filas) < BATCH_SIZE:
                completo = True
                break
    finally:
        await _cerrar(export_id, by, completed=completo, rows_sent=enviadas)


async def prepare(
    session: AsyncSession,
    filters: MemberExportQuery,
    consulta: Select[Member] | None,
    *,
    by: UUID,
    ip: str,
    max_rows: int,
    estado_de: EstadoDe,
) -> ExportStream:
    """Valida el tope, comprueba el bus y audita la apertura; ver el docstring del módulo.
    `estado_de` es `memberships.service.status_for`, que entrega `service.py` (G-03)."""
    total = await _contar(session, consulta)
    if total > max_rows:
        raise ExportTooLarge()
    current_keyring()  # sellado o sin cargar: CryptoUnavailable (503) antes de las cabeceras
    export_id = uuid4()
    await audit.record(
        session,
        action="export",
        table_name=TABLE,
        record_id=export_id,
        before=None,
        after={
            "filters": filters.model_dump(mode="json", exclude={"q"}),
            "has_q": bool(filters.q and filters.q.strip()),
            "rows": total,
            "fields": list(HEADER),
            "ip": ip,
        },
        user_id=by,
    )
    nombre = f"socios-{current_clock().today_bogota():%Y%m%d}.csv"
    return ExportStream(
        export_id=export_id,
        rows=total,
        filename=nombre,
        body=lambda: _cuerpo(consulta, export_id, by, estado_de, max_rows),
    )
