"""`members.service.contact_for_notification` con PostgreSQL real (S4A-B6, US-077; S4A-D21,
S4A-D50, M-6; blueprint B6 y paso 74 del plan).

- Devuelve el teléfono y el correo sembrados en un `Contact` cuyo `repr`/`str` no los muestra.
- Por cada campo no nulo: una fila `reveal` en `audit.audit_log` (`members.members`, el socio como
  `record_id` y `subject_member_id`, el actor de `get_actor()`, `before` nulo y
  `after == {"field": <campo>, "purpose": <propósito>}`, sin `ip` ni el valor) y una fila
  `decrypt` en `crypto_ops` con ese `purpose`, el `record_id` del socio y el `batch_id` del
  `batch_scope` del llamador (sin `bus.batch`, que agregaría y perdería el `record_id`).
- Un propósito inválido lanza `InvalidPurpose` sin ejecutar SQL y sin dejar filas.
- Un socio dado de baja o inexistente lanza `MemberNotContactable` sin descifrar ni auditar.
- Un campo vacío da `None` y no deja filas de ese campo.
- Composición (S4A-D50): no pide `lock_member` ni `FOR UPDATE`/`FOR SHARE`; llamada después de
  `lock_member` del mismo socio en la misma transacción termina sin 55P03; otra transacción que
  retiene el candado del socio no la bloquea; un rollback borra las `reveal` pero no las
  `decrypt` (por eso quien la llama confirma ANTES de enviar el aviso).
"""

from __future__ import annotations

import copy
import inspect
import json
import pickle
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import locks
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope, batch_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from app.modules.members.exceptions import InvalidPurpose, MemberNotContactable
from tests.conftest import T0, CrearUsuario
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, NOMBRE, make_member
from tests.members._apoyo import auditoria_del_socio, contar_crypto_ops, operaciones

TELEFONO = KNOWN["phone"]
CORREO = KNOWN["email"]
INEXISTENTE = UUID("00000000-0000-4000-8000-0000000b6c01")
INVALIDOS: tuple[Any, ...] = ("marketing", "mask", "reveal", "export", "", None)
CANDADOS_DE_FILA = re.compile(r"\bFOR\s+(NO\s+KEY\s+)?(UPDATE|SHARE|KEY\s+SHARE)\b", re.I)


@pytest.fixture
def listo(bus_listo: Keyring, reloj: FrozenClock) -> Keyring:
    return bus_listo


async def contactar(
    session: AsyncSession,
    member_id: UUID,
    purpose: Any = "notify",
    *,
    actor: UUID = SYSTEM_USER_ID,
    lote: UUID | None = None,
) -> service.Contact:
    """Una unidad del worker: sesión limpia, actor y lote fijados, la llamada y commit."""
    session.expunge_all()
    with actor_scope(actor), batch_scope(lote or uuid4()):
        contacto = await service.contact_for_notification(session, member_id, purpose)
        await session.commit()
    return contacto


@contextmanager
def sentencias(engine: AsyncEngine) -> Iterator[list[str]]:
    """Las sentencias SQL que llegan al cursor mientras dura el bloque."""
    vistas: list[str] = []

    def _antes(_c: object, _cur: object, sql: str, *_args: object) -> None:
        vistas.append(sql)

    event.listen(engine.sync_engine, "before_cursor_execute", _antes)
    try:
        yield vistas
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _antes)


def _por_campo(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        filas, key=lambda f: str((f.get("after") or {}).get("field", f.get("data_class")))
    )


# Valor ---------------------------------------------------------------------------------------


async def test_devuelve_el_telefono_y_el_correo_sembrados(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session)
    contacto = await contactar(session, socio.id)
    assert isinstance(contacto, service.Contact)
    assert contacto.first_name == NOMBRE
    assert contacto.phone == TELEFONO
    assert contacto.email == CORREO


async def test_auth_link_tambien_es_un_proposito_valido(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session)
    contacto = await contactar(session, socio.id, "auth_link")
    assert (contacto.phone, contacto.email) == (TELEFONO, CORREO)
    filas = await auditoria_del_socio(session, socio.id, "reveal")
    assert sorted(f["after"]["purpose"] for f in filas) == ["auth_link", "auth_link"]
    assert await contar_crypto_ops(session, socio.id, "decrypt", "auth_link") == 2


# Auditoría (S4A-D21) ---------------------------------------------------------------------------


async def test_deja_dos_filas_reveal_con_el_proposito_y_sin_valores(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session)
    await contactar(session, socio.id)
    filas = _por_campo(await auditoria_del_socio(session, socio.id, "reveal"))
    assert [f["after"] for f in filas] == [
        {"field": "email", "purpose": "notify"},
        {"field": "phone", "purpose": "notify"},
    ]
    for fila in filas:
        assert fila["table_name"] == "members.members"
        assert fila["record_id"] == socio.id
        assert fila["subject_member_id"] == socio.id
        assert fila["user_id"] == SYSTEM_USER_ID
        assert fila["before"] is None
    volcado = json.dumps([[f["before"], f["after"]] for f in filas])
    for valor in KNOWN_NORMALIZED:
        assert valor not in volcado, valor
    assert "apx1." not in volcado
    assert "ip" not in volcado


async def test_con_otro_actor_las_filas_llevan_su_user_id(
    session: AsyncSession, listo: Keyring, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    await contactar(session, socio.id, actor=admin.id)
    reveals = await auditoria_del_socio(session, socio.id, "reveal")
    assert [f["user_id"] for f in reveals] == [admin.id, admin.id]
    decrypts = await operaciones(session, verb="decrypt", record_id=socio.id)
    assert [f["user_id"] for f in decrypts] == [admin.id, admin.id]


# crypto_ops (S4A-D21: sin `bus.batch`) ---------------------------------------------------------


async def test_deja_dos_decrypt_con_el_record_id_del_socio_y_el_mismo_lote(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session)
    lote = uuid4()
    await contactar(session, socio.id, lote=lote)
    filas = _por_campo(await operaciones(session, verb="decrypt", record_id=socio.id))
    assert [f["data_class"] for f in filas] == ["member.email", "member.phone"]
    for fila in filas:
        assert fila["purpose"] == "notify"
        assert fila["batch_id"] == lote
        assert fila["user_id"] == SYSTEM_USER_ID
        assert fila["result"] == "ok"
        assert fila["count"] == 1
    assert await contar_crypto_ops(session, socio.id, "decrypt", "notify") == 2
    assert await contar_crypto_ops(session, socio.id, "decrypt", "mask") == 0
    assert await contar_crypto_ops(session, socio.id, "decrypt", "reveal") == 0


# Propósito inválido: antes de leer ------------------------------------------------------------


@pytest.mark.parametrize("proposito", INVALIDOS)
async def test_un_proposito_invalido_no_lee_la_base_ni_deja_filas(
    session: AsyncSession,
    listo: Keyring,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    proposito: Any,
) -> None:
    socio = await make_member(session)
    session.expunge_all()

    async def _no_leer(*_a: object, **_k: object) -> object:
        raise AssertionError("leyó la base con un propósito inválido")

    for metodo in ("execute", "scalar", "scalars", "get", "stream"):
        monkeypatch.setattr(session, metodo, _no_leer)
    with sentencias(engine) as vistas, actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
        with pytest.raises(InvalidPurpose):
            await service.contact_for_notification(session, socio.id, proposito)
    monkeypatch.undo()
    assert vistas == []
    with actor_scope(SYSTEM_USER_ID):
        await session.commit()
    assert await auditoria_del_socio(session, socio.id, "reveal") == []
    assert await operaciones(session, verb="decrypt", record_id=socio.id) == []


# Socio no contactable --------------------------------------------------------------------------


async def test_un_socio_inexistente_da_member_not_contactable_sin_descifrar(
    session: AsyncSession, listo: Keyring
) -> None:
    with pytest.raises(MemberNotContactable):
        await contactar(session, INEXISTENTE)
    await session.rollback()
    assert await auditoria_del_socio(session, INEXISTENTE) == []
    assert await operaciones(session, verb="decrypt", record_id=INEXISTENTE) == []


async def test_un_socio_dado_de_baja_da_member_not_contactable_sin_descifrar(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=3), status="inactive")
    socio_id = socio.id
    with pytest.raises(MemberNotContactable):
        await contactar(session, socio_id)
    await session.rollback()
    assert await auditoria_del_socio(session, socio_id, "reveal") == []
    assert await operaciones(session, verb="decrypt", record_id=socio_id) == []


# Campos vacíos -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("vacio", "lleno"), [("email", "phone"), ("phone", "email")])
async def test_un_campo_vacio_da_none_y_una_sola_fila_de_cada_tipo(
    session: AsyncSession, listo: Keyring, vacio: str, lleno: str
) -> None:
    socio = await make_member(session, **{vacio: None})
    contacto = await contactar(session, socio.id)
    assert getattr(contacto, vacio) is None
    assert getattr(contacto, lleno) == KNOWN[lleno]
    reveals = await auditoria_del_socio(session, socio.id, "reveal")
    assert [f["after"] for f in reveals] == [{"field": lleno, "purpose": "notify"}]
    decrypts = await operaciones(session, verb="decrypt", record_id=socio.id)
    assert [f["data_class"] for f in decrypts] == [f"member.{lleno}"]


async def test_sin_telefono_ni_correo_no_deja_filas(session: AsyncSession, listo: Keyring) -> None:
    socio = await make_member(session, phone=None, email=None)
    contacto = await contactar(session, socio.id)
    assert (contacto.first_name, contacto.phone, contacto.email) == (NOMBRE, None, None)
    assert await auditoria_del_socio(session, socio.id, "reveal") == []
    assert await operaciones(session, verb="decrypt", record_id=socio.id) == []


# `Contact` no muestra el teléfono ni el correo ---------------------------------------------------


def _sin_contacto_en(texto: str) -> None:
    assert TELEFONO not in texto
    assert CORREO not in texto
    assert TELEFONO[-4:] not in texto
    assert CORREO.split("@")[0] not in texto


def test_repr_y_str_de_contact_no_muestran_telefono_ni_correo() -> None:
    contacto = service.Contact(first_name=NOMBRE, phone=TELEFONO, email=CORREO)
    for texto in (repr(contacto), str(contacto), f"{contacto}", f"{contacto!r}"):
        _sin_contacto_en(texto)
    with pytest.raises(FrozenInstanceError):
        contacto.phone = "3000000000"  # type: ignore[misc]


def test_contact_no_se_serializa() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `json.dumps` sin ayuda, `pickle`, `copy`,
    `deepcopy` y `vars` fallan con `TypeError`; el mensaje no lleva el teléfono ni el correo."""
    contacto = service.Contact(first_name=NOMBRE, phone=TELEFONO, email=CORREO)
    intentos = (
        lambda: json.dumps(contacto),
        lambda: pickle.dumps(contacto),
        lambda: copy.copy(contacto),
        lambda: copy.deepcopy(contacto),
        lambda: vars(contacto),
    )
    for intento in intentos:
        with pytest.raises(TypeError) as error:
            intento()
        _sin_contacto_en(str(error.value))


async def test_el_contact_devuelto_tampoco_los_muestra(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await make_member(session)
    contacto = await contactar(session, socio.id)
    for texto in (repr(contacto), str(contacto), f"{contacto}"):
        _sin_contacto_en(texto)


# Composición (S4A-D50) ----------------------------------------------------------------------------


def test_el_docstring_escribe_la_regla_de_composicion() -> None:
    doc = " ".join((inspect.getdoc(service.contact_for_notification) or "").split()).lower()
    for frase in ("lock_member", "una unidad por socio", "antes de enviar", "rollback"):
        assert frase.lower() in doc, frase


async def test_no_pide_lock_member_ni_candados_de_fila(
    session: AsyncSession,
    listo: Keyring,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socio = await make_member(session)
    llamadas: list[UUID] = []

    async def _espia(_s: AsyncSession, member_id: UUID) -> None:
        llamadas.append(member_id)

    monkeypatch.setattr(locks, "lock_member", _espia)
    session.expunge_all()
    with sentencias(engine) as vistas, actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
        contacto = await service.contact_for_notification(session, socio.id, "notify")
        await session.commit()
    assert contacto.phone == TELEFONO
    assert llamadas == []
    assert not [s for s in vistas if "hashtextextended" in s]
    assert not [s for s in vistas if CANDADOS_DE_FILA.search(s)]


async def test_despues_de_lock_member_del_mismo_socio_termina_sin_55p03(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
        await segunda.execute(text("SET LOCAL lock_timeout = '1s'"))
        await locks.lock_member(segunda, socio.id)
        contacto = await service.contact_for_notification(segunda, socio.id, "notify")
        await segunda.commit()
    assert (contacto.phone, contacto.email) == (TELEFONO, CORREO)
    consulta = text(
        "SELECT count(*) FROM audit.audit_log WHERE record_id = :id AND action = 'reveal'"
    )
    assert await primera.scalar(consulta, {"id": socio.id}) == 2
    await primera.commit()


async def test_otra_transaccion_con_el_candado_del_socio_no_la_bloquea(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, reloj: FrozenClock
) -> None:
    """Sin `lock_member`: con el candado del socio tomado por otra transacción, la llamada
    termina antes de `lock_timeout` (si lo pidiera, saldría `DatabaseBusy`)."""
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    await locks.lock_member(primera, socio.id)
    try:
        with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
            await segunda.execute(text("SET LOCAL lock_timeout = '1s'"))
            contacto = await service.contact_for_notification(segunda, socio.id, "notify")
            await segunda.commit()
    finally:
        await primera.rollback()
    assert contacto.phone == TELEFONO


async def test_el_rollback_borra_las_reveal_pero_no_las_decrypt(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, reloj: FrozenClock
) -> None:
    """Razón de "confirmar antes de enviar" (S4A-D50, M-6 punto 3): `oplog` escribe las
    `decrypt` en otra conexión al revertir (el dato estuvo en claro en memoria), pero las filas
    `reveal` de la auditoría se pierden. Un aviso enviado antes del commit quedaría sin rastro."""
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    lote = uuid4()
    with actor_scope(SYSTEM_USER_ID), batch_scope(lote):
        contacto = await service.contact_for_notification(segunda, socio.id, "notify")
        await segunda.rollback()
    assert contacto.phone == TELEFONO
    consulta = text(
        "SELECT count(*) FROM audit.audit_log WHERE record_id = :id AND action = 'reveal'"
    )
    assert await primera.scalar(consulta, {"id": socio.id}) == 0
    assert await contar_crypto_ops(primera, socio.id, "decrypt", "notify") == 2
    lotes = await primera.scalars(
        text(
            "SELECT DISTINCT batch_id FROM crypto.crypto_ops "
            "WHERE record_id = :id AND verb = 'decrypt'"
        ),
        {"id": socio.id},
    )
    assert list(lotes) == [lote]
    await primera.commit()
