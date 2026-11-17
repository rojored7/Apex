"""`invalidate_manual_record`: la salida ante un error de digitación (S9-B5, US-181; S9-D13, L-3).

Solo récords MANUALES vivos: pone `invalidated_reason = manual_error`, `invalidated_at` e
`invalidated_by` (por ORM: deja su `update` en la auditoría con el actor) y repone el mejor
resultado que había quedado tapado (S9-D11). Un derivado da 409 `record_is_derived` ("se corrige
corrigiendo o anulando el resultado"), uno ya invalidado 409 `record_already_invalidated`; un
récord que no es del socio, 404 `record_not_found`; un socio dado de baja, 404 `member_not_found`
(S9-D14). Dos invalidaciones a la vez: la segunda espera el candado del socio y recibe 409 (L-3),
nunca un 500. El motivo y el actor jamás son texto libre.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.errors import DomainError, ForbiddenError
from app.modules.athletes import service
from app.modules.athletes.schemas import RecordOut
from tests.athletes._apoyo import alta_record, auditoria_de_records, cuerpo_rm
from tests.athletes._apoyo_derivar import records_de, vigente_g
from tests.athletes._apoyo_invalidar import ContadorMarcas, cargar, escena_serie, vivos, wod_en
from tests.athletes.test_void_concurrency import _esperando_candado
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_record
from tests.results._apoyo import Escena

BLANDO = pytest.mark.usefixtures("reloj", "bus_listo")
REAL = pytest.mark.usefixtures("reloj", "bus_confirmado")
MEDIDAS = ("weight_g", "height_cm", "body_fat_pct", "notes")


async def _invalidar(
    session: AsyncSession, actor: UUID, member_id: UUID, record_id: UUID, *, role: str = "admin"
) -> RecordOut:
    """`service.invalidate_manual_record` como una petición: sesión vacía, `actor_scope`, commit si
    sale bien y rollback si no."""
    session.expunge_all()
    with actor_scope(actor):
        try:
            salida = await service.invalidate_manual_record(
                session, member_id, record_id, by=actor, role=role
            )
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return salida


async def _error(
    session: AsyncSession, actor: UUID, member_id: UUID, record_id: UUID, *, role: str = "admin"
) -> Any:
    with pytest.raises(DomainError) as info:
        await _invalidar(session, actor, member_id, record_id, role=role)
    return info.value


@pytest.fixture
async def e(session: AsyncSession) -> Escena:
    return await escena_serie(session, "2026-10-12")


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _manual(
    session: AsyncSession, actor: UUID, e: Escena, valor_g: int, dia: str = "2026-10-10"
) -> UUID:
    """Un RM manual del movimiento principal de la escena, dado de alta por el service."""
    salida = await alta_record(
        session, actor, e.socio_id, cuerpo_rm(e.movimientos[0], value_g=valor_g, achieved_on=dia)
    )
    return salida.id  # type: ignore[no-any-return]


@BLANDO
async def test_invalida_un_manual_vivo_sin_borrarlo(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    record_id = await _manual(session, e.coach, e, 1_000_000)

    salida = await _invalidar(session, admin.id, e.socio_id, record_id)

    assert salida.id == record_id
    assert salida.invalidated_reason == "manual_error"
    assert salida.invalidated_at is not None
    assert salida.is_current is False
    filas = await records_de(session, e.socio_id)
    assert len(filas) == 1, "no se borra"
    assert filas[0]["invalidated_reason"] == "manual_error"
    assert filas[0]["invalidated_by"] == admin.id
    assert filas[0]["invalidated_by_result_id"] is None
    assert filas[0]["value_g"] == 1_000_000
    assert vigente_g(filas) is None


@BLANDO
async def test_repone_el_mejor_resultado_que_habia_quedado_tapado(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    """Un manual de 100 kg tapa un resultado de 60 kg (no derivó). Invalidar el manual repone el
    de 60 como récord derivado y deja el vigente en 60.000 g."""
    manual = await _manual(session, e.coach, e, 100_000)
    sesenta = await cargar(session, e, e.wod_id, 60_000)
    assert [f["id"] for f in vivos(await records_de(session, e.socio_id))] == [manual]

    await _invalidar(session, admin.id, e.socio_id, manual)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 2
    repuesto = vivos(filas)[0]
    assert repuesto["value_g"] == 60_000
    assert repuesto["result_id"] == sesenta.id and repuesto["source"] == "derived"
    assert repuesto["created_by"] == admin.id, "el actor del contexto: quien invalidó"
    assert vigente_g(filas) == 60_000


@BLANDO
async def test_la_reposicion_pide_member_marks_una_vez_filtrado_por_el_principal(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    manual = await _manual(session, e.coach, e, 100_000)
    contador = ContadorMarcas(monkeypatch)

    await _invalidar(session, admin.id, e.socio_id, manual)

    assert len(contador.llamadas) == 1
    assert contador.llamadas[0]["member_id"] == e.socio_id
    assert contador.llamadas[0]["only_load"] is True
    assert set(contador.llamadas[0]["wod_ids"]) == {e.wod_id}


@BLANDO
async def test_benchmark_manual_invalidado_repone_el_mejor_tiempo_tapado(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    """Un manual de 250 s en Fran tapa un resultado de 300 s; al invalidarlo vuelve el de 300."""
    from tests.athletes._apoyo import cuerpo_benchmark
    from tests.athletes._apoyo_invalidar import poner_en
    from tests.factories.wods import make_benchmark

    bm = await make_benchmark(session, e.coach, name="Fran", score_type="time")
    w = await wod_en(
        session, e, "2026-10-14", "F1", score_type="time", time_cap_s=600, benchmark_id=bm.id
    )
    manual = (
        await alta_record(
            session,
            e.coach,
            e.socio_id,
            cuerpo_benchmark(bm.id, seconds=250, achieved_on="2026-10-10"),
        )
    ).id
    resultado = await poner_en(session, e, w, seconds=300)
    assert [f["id"] for f in vivos(await records_de(session, e.socio_id), "benchmark")] == [manual]

    await _invalidar(session, admin.id, e.socio_id, manual)

    vivas = vivos(await records_de(session, e.socio_id), "benchmark")
    assert [(f["seconds"], f["result_id"]) for f in vivas] == [(300, resultado.id)]


@BLANDO
async def test_un_derivado_da_409_record_is_derived_y_no_se_toca(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    await cargar(session, e, e.wod_id, 100_000)
    derivado = vivos(await records_de(session, e.socio_id))[0]["id"]
    await session.commit()  # `_error` hace rollback: sin esto se llevaría también la escena

    error = await _error(session, admin.id, e.socio_id, derivado)

    assert (error.status, error.code) == (409, "record_is_derived")
    assert vivos(await records_de(session, e.socio_id))[0]["id"] == derivado


@BLANDO
async def test_repetir_da_409_record_already_invalidated_sin_nueva_auditoria(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    manual = await _manual(session, e.coach, e, 100_000)
    await _invalidar(session, admin.id, e.socio_id, manual)
    antes = len(await auditoria_de_records(session, manual))

    error = await _error(session, admin.id, e.socio_id, manual)

    assert (error.status, error.code) == (409, "record_already_invalidated")
    assert len(await auditoria_de_records(session, manual)) == antes


@BLANDO
async def test_un_derivado_ya_invalidado_tambien_da_409_de_derivado(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    """El tipo manda sobre el estado: se corrige el resultado, no el récord."""
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id)
    viejo = next(f for f in await records_de(session, e.socio_id) if f["result_id"] == malo.id)

    error = await _error(session, admin.id, e.socio_id, viejo["id"])

    assert (error.status, error.code) == (409, "record_is_derived")


@BLANDO
async def test_un_record_de_otro_socio_o_inexistente_da_404_record_not_found(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    ajeno = await make_record(session, kind="rm", value_g=90_000)  # de OTRO socio
    manual = await _manual(session, e.coach, e, 100_000)

    de_otro = await _error(session, admin.id, e.socio_id, ajeno.id)
    no_existe = await _error(session, admin.id, e.socio_id, uuid4())

    assert (de_otro.status, de_otro.code) == (404, "record_not_found")
    assert (no_existe.status, no_existe.code) == (404, "record_not_found")
    assert de_otro.message == no_existe.message, "no delata que el récord existe"
    assert vivos(await records_de(session, e.socio_id))[0]["id"] == manual


@BLANDO
async def test_un_socio_dado_de_baja_da_404_member_not_found(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    manual = await _manual(session, e.coach, e, 100_000)
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"), {"i": e.socio_id}
    )

    error = await _error(session, admin.id, e.socio_id, manual)

    assert (error.status, error.code) == (404, "member_not_found")
    assert vivos(await records_de(session, e.socio_id))[0]["id"] == manual


@BLANDO
async def test_deja_una_fila_update_con_el_actor_y_sin_medidas(
    session: AsyncSession, e: Escena, admin: UsuarioPrueba
) -> None:
    manual = await _manual(session, e.coach, e, 100_000)

    await _invalidar(session, admin.id, e.socio_id, manual)

    filas = await auditoria_de_records(session, manual)
    assert [f["action"] for f in filas] == ["insert", "update"]
    cambio = filas[1]
    assert cambio["user_id"] == admin.id
    assert cambio["subject_member_id"] == e.socio_id
    assert cambio["after"]["invalidated_reason"] == "manual_error"
    claves = set((cambio["after"] or {}).keys()) | set((cambio["before"] or {}).keys())
    assert not set(MEDIDAS) & claves


@BLANDO
async def test_un_coach_ajeno_recibe_403_y_el_dueno_lo_invalida(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    """M-3 (S9-D33): el coach solo invalida lo que registró él."""
    dueno = await usuario_real("coach")
    ajeno = await usuario_real("coach")
    manual = await _manual(session, dueno.id, e, 100_000)

    with pytest.raises(ForbiddenError):
        await _invalidar(session, ajeno.id, e.socio_id, manual, role="coach")
    assert vivos(await records_de(session, e.socio_id))[0]["id"] == manual

    salida = await _invalidar(session, dueno.id, e.socio_id, manual, role="coach")
    assert salida.invalidated_reason == "manual_error"


# Dos a la vez (L-3) ---------------------------------------------------------------------------


@REAL
async def test_dos_invalidaciones_a_la_vez_una_200_y_la_otra_409_nunca_500(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    """La primera toma el candado del socio y no confirma; la segunda queda esperando en
    `lock_member` (visible en `pg_locks`) y, al confirmar la primera, lee el récord ya invalidado
    y recibe 409 `record_already_invalidated` (nunca el 500 de la guarda de la base)."""
    from tests.notifications._apoyo_avisos import socio

    una, otra = dos_sesiones
    miembro = await socio(una, consentido=True)
    record = await make_record(una, miembro.id, kind="rm", value_g=100_000)
    member_id, record_id = miembro.id, record.id
    una.expunge_all()
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)

    async def invalidar(sesion: AsyncSession) -> Any:
        with actor_scope(SYSTEM_USER_ID):
            return await service.invalidate_manual_record(
                sesion, member_id, record_id, by=SYSTEM_USER_ID, role="admin"
            )

    primera = await invalidar(una)  # candado tomado, sin confirmar
    assert primera.invalidated_reason == "manual_error"
    contraria = asyncio.create_task(invalidar(otra))
    try:
        try:
            await _esperando_candado(engine, pid)
            assert not contraria.done(), "la segunda invalidación debe esperar a la primera"
        finally:
            await una.commit()  # nunca dejar el candado tomado
        resultado = (await asyncio.wait_for(asyncio.gather(contraria, return_exceptions=True), 30))[
            0
        ]
    finally:
        if not contraria.done():
            contraria.cancel()
        await asyncio.gather(contraria, return_exceptions=True)
        await otra.rollback()

    assert isinstance(resultado, DomainError), resultado
    assert (resultado.status, resultado.code) == (409, "record_already_invalidated")
    vivas = await una.scalar(
        text(
            "SELECT count(*) FROM athletes.personal_records "
            "WHERE member_id = :m AND invalidated_at IS NULL"
        ),
        {"m": member_id},
    )
    assert vivas == 0
