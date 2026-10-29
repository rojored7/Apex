"""`run_verification` contra la base real (S4A-B3, US-104; S4A-D11, S4A-D12, S4A-D43, S4A-D47).

Todo ocurre en la transacción de la prueba (`audit_chain_factory` vacía `audit.audit_log` y
`audit.verifications` dentro de ella). Valores esperados calculados a mano:
- `through_seq = max(seq)` al empezar; la fila `verify` que se escribe al final es `through_seq + 1`
  y entra en la verificación siguiente;
- `broken_at_seq` es el `seq` de la primera fila que no encaja: una fila con `after` alterado rompe
  en ella misma (1234); una fila borrada rompe en la siguiente (1235). El plan escribe "fila 1234
  alterada → 1235": con la semántica fijada (S4A-D11, la del hash) eso solo vale para la borrada;
  se prueban los dos casos;
- H-1 (S4A-D43): con ancla `A` (la última `ok`), `ok = false` si `max(seq) < A.through_seq` o si la
  fila `A.through_seq` no tiene `A.through_hash`; entonces `broken_at_seq = min(last_seq + 1,
  A.through_seq)`; una verificación rota no mueve el ancla.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit_verify
from app.core.audit import AuditEntry, record
from app.core.audit_verify import (
    AuditVerification,
    VerificationView,
    format_verify_message,
    run_verification,
)
from app.core.context import SYSTEM_USER_ID, actor_scope
from tests.audit._apoyo import CLAVES_AFTER
from tests.audit.conftest import CadenaDePrueba
from tests.conftest import ContadorDeConsultas

POR = SYSTEM_USER_ID
ADMIN = UUID("00000000-0000-0000-0000-00000000a0a0")
LOTE_ASCENDENTE = re.compile(r"ORDER BY audit\.audit_log\.seq(\s+ASC)?\s+LIMIT", re.IGNORECASE)


async def _verificar(session: AsyncSession, by: UUID = POR) -> VerificationView:
    with actor_scope(by):
        return await run_verification(session, source="api", by=by)


async def _verificaciones(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditVerification)) or 0)


async def _entradas_verify(session: AsyncSession) -> list[AuditEntry]:
    filas = await session.scalars(
        select(AuditEntry).where(AuditEntry.action == "verify").order_by(AuditEntry.seq)
    )
    return list(filas)


# Cadena íntegra y rupturas ----------------------------------------------------------------------


async def test_cinco_mil_filas_integras(audit_chain_factory: CadenaDePrueba) -> None:
    ultimo = await audit_chain_factory.make(5000)
    assert ultimo == 5000

    resultado = await _verificar(audit_chain_factory.session)

    assert resultado.ok is True
    assert resultado.rows_checked == 5000
    assert resultado.through_seq == 5000
    assert resultado.broken_at_seq is None
    assert resultado.through_hash == await audit_chain_factory.hash_of(5000)
    assert (resultado.source, resultado.triggered_by) == ("api", POR)
    assert resultado.started_at <= resultado.finished_at


async def test_fila_1234_alterada_rompe_en_1234(audit_chain_factory: CadenaDePrueba) -> None:
    await audit_chain_factory.make(5000)
    await audit_chain_factory.tamper(1234, "after", {"n": "alterado"})

    resultado = await _verificar(audit_chain_factory.session)

    assert resultado.ok is False
    assert resultado.broken_at_seq == 1234
    assert resultado.rows_checked == 1234  # se detiene en la primera ruptura, incluida


async def test_fila_1234_borrada_rompe_en_1235(audit_chain_factory: CadenaDePrueba) -> None:
    await audit_chain_factory.make(5000)
    await audit_chain_factory.drop_rows([1234])

    resultado = await _verificar(audit_chain_factory.session)

    assert resultado.ok is False
    assert resultado.broken_at_seq == 1235
    assert resultado.rows_checked == 1234


async def test_cadena_vacia_es_integra_con_through_seq_0(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    resultado = await _verificar(audit_chain_factory.session)
    assert (resultado.ok, resultado.rows_checked, resultado.through_seq) == (True, 0, 0)
    assert resultado.through_hash == "0" * 64


# H-1: ancla ------------------------------------------------------------------------------------


async def test_h1_cola_borrada_tras_una_verificacion_ok_da_rota(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(50)
    ancla = await _verificar(audit_chain_factory.session)
    assert (ancla.ok, ancla.through_seq) == (True, 50)  # la fila verify queda en el seq 51
    borrados = await audit_chain_factory.drop_tail(3)
    assert borrados == [49, 50, 51]

    resultado = await _verificar(audit_chain_factory.session)

    restante = 48
    assert resultado.ok is False
    assert resultado.broken_at_seq == min(restante + 1, ancla.through_seq) == 49
    assert resultado.anchor_seq == 50
    assert resultado.anchor_broken is True
    texto, codigo = format_verify_message(resultado)
    assert codigo == 1 and "no coincide con la verificación anterior" in texto


async def test_h1_cola_reemplazada_por_una_cadena_valida_pero_distinta_da_rota(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(50)
    ancla = await _verificar(audit_chain_factory.session)
    hash_original = await audit_chain_factory.hash_of(50)
    await audit_chain_factory.tamper(50, "after", {"n": "reescrita"}, rehash=True)
    assert await audit_chain_factory.hash_of(50) != hash_original

    resultado = await _verificar(audit_chain_factory.session)

    # La cadena es internamente válida (51 filas, más la verify nueva al final) pero la fila 50 ya
    # no tiene el hash del ancla: min(51 + 1, 50) = 50.
    assert resultado.ok is False
    assert resultado.broken_at_seq == min(51 + 1, ancla.through_seq) == 50
    assert resultado.anchor_broken is True


async def test_primera_verificacion_sin_ancla_lo_dice_y_la_segunda_no(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(20)

    primera = await _verificar(audit_chain_factory.session)
    segunda = await _verificar(audit_chain_factory.session)

    assert (primera.ok, primera.anchor_seq) == (True, None)
    texto, codigo = format_verify_message(primera)
    assert codigo == 0 and "sin verificación anterior que comparar" in texto
    assert (segunda.ok, segunda.anchor_seq, segunda.rows_checked) == (True, 20, 21)
    assert "sin verificación anterior" not in format_verify_message(segunda)[0]


async def test_una_verificacion_rota_no_mueve_el_ancla(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(50)
    ancla = await _verificar(audit_chain_factory.session)  # through 50; verify en el 51
    await audit_chain_factory.drop_tail(3)  # quedan 1..48
    rota = await _verificar(audit_chain_factory.session)  # through 48; su verify en el 49
    assert (rota.ok, rota.through_seq) == (False, 48)

    siguiente = await _verificar(audit_chain_factory.session)

    # Compara contra el ancla (50), no contra la rota (48): max(seq) = 49 < 50.
    assert siguiente.ok is False
    assert siguiente.anchor_seq == ancla.through_seq == 50
    assert siguiente.broken_at_seq == min(49 + 1, 50) == 50


# Lo que deja cada verificación ------------------------------------------------------------------


async def test_cada_verificacion_deja_su_fila_y_una_entrada_verify_que_entra_a_la_cadena(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    session = audit_chain_factory.session
    await audit_chain_factory.make(50)

    primera = await _verificar(session, ADMIN)

    assert await _verificaciones(session) == 1
    guardada = await session.get(AuditVerification, primera.id)
    assert guardada is not None
    assert (guardada.ok, guardada.through_seq, guardada.rows_checked) == (True, 50, 50)
    assert (guardada.triggered_by, guardada.created_by, guardada.source) == (ADMIN, ADMIN, "api")
    assert guardada.through_hash == primera.through_hash
    [entrada] = await _entradas_verify(session)
    assert (entrada.seq, entrada.table_name, entrada.record_id) == (
        51,
        "audit.verifications",
        primera.id,
    )
    assert (entrada.user_id, entrada.before) == (ADMIN, None)
    assert entrada.after is not None and set(entrada.after) == CLAVES_AFTER
    assert entrada.after["through_hash"] == primera.through_hash
    assert (entrada.after["ok"], entrada.after["through_seq"], entrada.after["source"]) == (
        True,
        50,
        "api",
    )

    segunda = await _verificar(session, ADMIN)

    assert (segunda.ok, segunda.rows_checked, segunda.through_seq) == (True, 51, 51)
    assert await _verificaciones(session) == 2


async def test_una_transaccion_auditada_revertida_no_deja_huecos(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    session = audit_chain_factory.session
    await audit_chain_factory.make(10)
    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await record(
                session,
                action="insert",
                table_name="members.members",
                record_id=None,
                before=None,
                after={"n": "revertida"},
                user_id=POR,
            )
            raise RuntimeError("se revierte")
    await audit_chain_factory.make(5)

    resultado = await _verificar(session)

    assert (resultado.ok, resultado.through_seq, resultado.rows_checked) == (True, 15, 15)


async def test_la_verificacion_no_cambia_ninguna_fila_existente(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(300)
    antes = await audit_chain_factory.digest(hasta=300)

    resultado = await _verificar(audit_chain_factory.session)

    assert resultado.through_seq == 300
    assert await audit_chain_factory.digest(hasta=300) == antes
    assert await audit_chain_factory.last_seq() == 301  # solo se agregó la fila verify


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE audit.verifications SET ok = false",
        "DELETE FROM audit.verifications",
        "TRUNCATE audit.verifications",
    ],
    ids=["update", "delete", "truncate"],
)
async def test_audit_verifications_es_inmutable(
    audit_chain_factory: CadenaDePrueba, sentencia: str
) -> None:
    session = audit_chain_factory.session
    await audit_chain_factory.make(5)
    await _verificar(session)
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(text(sentencia))
    assert await _verificaciones(session) == 1


# Log del ancla y lotes ---------------------------------------------------------------------------


async def test_una_verificacion_ok_escribe_audit_anchor_sin_before_ni_after(
    audit_chain_factory: CadenaDePrueba, caplog: pytest.LogCaptureFixture
) -> None:
    await audit_chain_factory.make(30)
    caplog.set_level(logging.INFO)

    resultado = await _verificar(audit_chain_factory.session)

    anclas = [r for r in caplog.records if r.getMessage() == "audit anchor"]
    assert len(anclas) == 1
    registro = anclas[0]
    assert registro.levelno == logging.INFO
    assert getattr(registro, "through_seq", None) == resultado.through_seq == 30
    assert getattr(registro, "through_hash", None) == resultado.through_hash
    assert not hasattr(registro, "before") and not hasattr(registro, "after")
    assert "marca-de-auditoria" not in caplog.text


async def test_una_verificacion_rota_no_escribe_audit_anchor(
    audit_chain_factory: CadenaDePrueba, caplog: pytest.LogCaptureFixture
) -> None:
    await audit_chain_factory.make(30)
    await audit_chain_factory.tamper(7, "after", {"n": "alterado"})
    caplog.set_level(logging.INFO)

    resultado = await _verificar(audit_chain_factory.session)

    assert resultado.ok is False
    assert not [r for r in caplog.records if r.getMessage() == "audit anchor"]


async def test_con_lote_de_mil_2500_filas_son_tres_lotes(
    audit_chain_factory: CadenaDePrueba, contador_de_consultas: ContadorDeConsultas
) -> None:
    """S4A-D47: `VERIFY_BATCH_SIZE = 1000` y el recorrido se detiene en `through_seq` (2500):
    1.000 + 1.000 + 500. Un lote es una lectura de `audit.audit_log` ordenada por `seq` ascendente
    con `LIMIT` (la de `record`, `seq DESC`, no cuenta)."""
    assert audit_verify.VERIFY_BATCH_SIZE == 1000
    await audit_chain_factory.make(2500)

    with contador_de_consultas.midiendo():
        resultado = await _verificar(audit_chain_factory.session)

    assert (resultado.ok, resultado.rows_checked) == (True, 2500)
    lotes = [s for s in contador_de_consultas.sentencias if LOTE_ASCENDENTE.search(s)]
    assert len(lotes) == 3, lotes


async def test_entre_lotes_cede_el_loop(
    audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4A-D47: `_pause_between_batches` (que hace `asyncio.sleep(0)`) corre entre lotes: con
    2.500 filas, dos veces como mínimo (entre el 1.º y el 2.º y entre el 2.º y el 3.º)."""
    pausas: list[int] = []

    async def contar() -> None:
        pausas.append(1)

    monkeypatch.setattr(audit_verify, "_pause_between_batches", contar)
    await audit_chain_factory.make(2500)

    await _verificar(audit_chain_factory.session)

    assert len(pausas) >= 2


# Revisiones de B3 (database-reviewer y security-reviewer) -------------------------------------


async def test_el_through_hash_ok_sale_del_recorrido_y_no_se_relee(
    audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M (DB, S4A-D99): con la cadena íntegra el `through_hash` es el `last_hash` que verificó el
    recorrido; `_hash_at` solo lo usa `_check_anchor` (con ancla, para la fila del ancla)."""
    leidos: list[int] = []
    original = audit_verify._hash_at

    async def espia(session: AsyncSession, seq: int) -> str | None:
        leidos.append(seq)
        return await original(session, seq)

    monkeypatch.setattr(audit_verify, "_hash_at", espia)
    await audit_chain_factory.make(50)

    primera = await _verificar(audit_chain_factory.session)
    assert leidos == []
    assert primera.through_hash == await audit_chain_factory.hash_of(50)

    segunda = await _verificar(audit_chain_factory.session)
    assert leidos == [50]  # solo la fila del ancla
    assert segunda.through_hash == await audit_chain_factory.hash_of(51)


async def test_una_verificacion_rota_no_guarda_un_hash_sin_verificar(
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(30)
    await audit_chain_factory.tamper(7, "after", {"n": "alterado"})

    resultado = await _verificar(audit_chain_factory.session)

    assert (resultado.ok, resultado.through_seq, resultado.through_hash) == (False, 30, "0" * 64)


async def test_si_la_cadena_se_acaba_antes_de_through_seq_es_rota(
    audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L (DB L2, seguridad L1): filas borradas entre lotes dejan un lote vacío antes de
    `through_seq`; eso es ruptura en `last_seq + 1`, nunca `ok`."""
    borradas: list[int] = []

    async def borrar_la_cola() -> None:
        if not borradas:
            borradas.extend(await audit_chain_factory.drop_tail(1500))

    monkeypatch.setattr(audit_verify, "_pause_between_batches", borrar_la_cola)
    await audit_chain_factory.make(2500)

    resultado = await _verificar(audit_chain_factory.session)

    assert borradas == list(range(1001, 2501))
    assert (resultado.ok, resultado.through_seq) == (False, 2500)
    assert (resultado.broken_at_seq, resultado.rows_checked) == (1001, 1000)


async def test_run_verification_escribe_auditoria_una_sola_vez_y_al_final(
    audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L (DB L4, S4A-D102): `record` toma el candado de la cadena hasta el commit; la verificación
    solo lo llama una vez, en `_persist`, después del último lote."""
    eventos: list[str] = []
    original_record = record
    original_pausa = audit_verify._pause_between_batches

    async def espia_record(*args: object, **kwargs: object) -> object:
        eventos.append(f"record:{kwargs.get('table_name')}")
        return await original_record(*args, **kwargs)  # type: ignore[arg-type]

    async def espia_pausa() -> None:
        eventos.append("pausa")
        await original_pausa()

    monkeypatch.setattr(audit_verify, "record", espia_record)
    monkeypatch.setattr(audit_verify, "_pause_between_batches", espia_pausa)
    await audit_chain_factory.make(2500)

    await _verificar(audit_chain_factory.session)

    assert eventos == ["pausa", "pausa", "record:audit.verifications"]
