"""`members.service.contact_for_notification(..., fields=...)` con PostgreSQL real
(S5-B5, US-123; S5-D32, S5-D34, S4A-D21, S5-D204). # Rojo B5

- `fields` (`None` = `("phone", "email")`): solo se descifra y se audita lo pedido. Con
  `fields={"phone"}` hay una fila `decrypt` de `member.phone` y una `reveal` del campo `phone`, y
  ninguna de `member.email`; el otro campo del `Contact` queda en `None`.
- Un campo desconocido (`document`, `birth_date`, ...) lanza `InvalidField` antes de leer la base
  y sin dejar filas.
- Carga con `load_only(first_name, phone, email, deleted_at, data_consent_at)`: el `SELECT` de
  `members.members` no pide `document`, `birth_date`, `emergency_contact` ni los índices ciegos
  (el rol del worker solo tiene `SELECT` por columna, S5-D204).
- `purpose == "notify"` con `data_consent_at` nulo lanza `MemberNotContactable` sin descifrar ni
  auditar (S5-D34); `auth_link` no exige la autorización (el enlace de acceso no es un aviso).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope, batch_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from app.modules.members.exceptions import InvalidField, MemberNotContactable
from tests.conftest import T0
from tests.factories.members import KNOWN, make_member
from tests.members._apoyo import auditoria_del_socio, contar_crypto_ops, operaciones

TELEFONO = KNOWN["phone"]
CORREO = KNOWN["email"]
DESCONOCIDOS: tuple[str, ...] = ("document", "birth_date", "emergency_contact", "first_name", "x")
COLUMNAS_PROHIBIDAS_EN_EL_SELECT: tuple[str, ...] = (
    "document",
    "document_idx",
    "phone_idx",
    "email_idx",
    "birth_date",
    "emergency_contact",
)


@pytest.fixture
def listo(bus_listo: Keyring, reloj: FrozenClock) -> Keyring:
    return bus_listo


async def socio_consentido(session: AsyncSession, **cambios: Any) -> UUID:
    valores: dict[str, Any] = {"data_consent_at": T0 - timedelta(days=1)}
    valores.update(cambios)
    return (await make_member(session, **valores)).id


async def contactar(
    session: AsyncSession, member_id: UUID, purpose: Any = "notify", **kwargs: Any
) -> service.Contact:
    """Una unidad del worker: sesión limpia, actor y lote fijados, la llamada y commit."""
    session.expunge_all()
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
        contacto = await service.contact_for_notification(session, member_id, purpose, **kwargs)
        await session.commit()
    return contacto


@contextmanager
def sentencias(engine: AsyncEngine) -> Iterator[list[str]]:
    vistas: list[str] = []

    def _antes(_c: object, _cur: object, sql: str, *_args: object) -> None:
        vistas.append(sql)

    event.listen(engine.sync_engine, "before_cursor_execute", _antes)
    try:
        yield vistas
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _antes)


def _clases_descifradas(filas: list[dict[str, Any]]) -> list[str]:
    return sorted(f["data_class"] for f in filas)


# Solo lo pedido ----------------------------------------------------------------------------------


async def test_con_fields_phone_solo_se_descifra_y_se_audita_el_telefono(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session)
    contacto = await contactar(session, socio, fields={"phone"})
    assert (contacto.phone, contacto.email) == (TELEFONO, None)
    descifrados = await operaciones(session, verb="decrypt", record_id=socio)
    assert _clases_descifradas(descifrados) == ["member.phone"]
    revelados = await auditoria_del_socio(session, socio, "reveal")
    assert [f["after"] for f in revelados] == [{"field": "phone", "purpose": "notify"}]


async def test_con_fields_email_solo_se_descifra_y_se_audita_el_correo(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session)
    contacto = await contactar(session, socio, fields={"email"})
    assert (contacto.phone, contacto.email) == (None, CORREO)
    descifrados = await operaciones(session, verb="decrypt", record_id=socio)
    assert _clases_descifradas(descifrados) == ["member.email"]
    revelados = await auditoria_del_socio(session, socio, "reveal")
    assert [f["after"] for f in revelados] == [{"field": "email", "purpose": "notify"}]


@pytest.mark.parametrize(
    "fields",
    [("phone", "email"), ["email", "phone"], frozenset({"phone", "email"}), None],
    ids=["tupla", "lista", "frozenset", "por-defecto"],
)
async def test_pedir_los_dos_campos_o_ninguna_lista_descifra_ambos(
    session: AsyncSession, listo: Keyring, fields: Any
) -> None:
    socio = await socio_consentido(session)
    contacto = await contactar(session, socio, fields=fields)
    assert (contacto.phone, contacto.email) == (TELEFONO, CORREO)
    descifrados = await operaciones(session, verb="decrypt", record_id=socio)
    assert _clases_descifradas(descifrados) == ["member.email", "member.phone"]
    assert await contar_crypto_ops(session, socio, "decrypt", "notify") == 2


async def test_con_fields_vacio_no_se_descifra_ni_se_audita_nada(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session)
    contacto = await contactar(session, socio, fields=frozenset())
    assert (contacto.phone, contacto.email) == (None, None)
    assert await operaciones(session, verb="decrypt", record_id=socio) == []
    assert await auditoria_del_socio(session, socio, "reveal") == []


async def test_un_campo_pedido_pero_vacio_da_none_y_no_deja_filas(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session, phone=None)
    contacto = await contactar(session, socio, fields={"phone"})
    assert (contacto.phone, contacto.email) == (None, None)
    assert await operaciones(session, verb="decrypt", record_id=socio) == []
    assert await auditoria_del_socio(session, socio, "reveal") == []


# Campo desconocido -------------------------------------------------------------------------------


@pytest.mark.parametrize("desconocido", DESCONOCIDOS)
async def test_un_campo_desconocido_lanza_invalid_field_sin_dejar_filas(
    session: AsyncSession, listo: Keyring, desconocido: str
) -> None:
    socio = await socio_consentido(session)
    session.expunge_all()
    with (
        actor_scope(SYSTEM_USER_ID),
        batch_scope(uuid4()),
        pytest.raises(InvalidField) as capturado,
    ):
        await service.contact_for_notification(session, socio, "notify", fields={desconocido})
    await session.rollback()
    assert capturado.value.code == "invalid_field"
    assert desconocido not in capturado.value.message
    assert await operaciones(session, verb="decrypt", record_id=socio) == []
    assert await auditoria_del_socio(session, socio, "reveal") == []


async def test_un_campo_desconocido_junto_a_uno_valido_tambien_se_rechaza_sin_descifrar(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session)
    session.expunge_all()
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()), pytest.raises(InvalidField):
        await service.contact_for_notification(
            session, socio, "notify", fields={"phone", "document"}
        )
    await session.rollback()
    assert await operaciones(session, verb="decrypt", record_id=socio) == []


async def test_un_campo_desconocido_no_lee_la_base(
    session: AsyncSession, listo: Keyring, engine: AsyncEngine
) -> None:
    socio = await socio_consentido(session)
    session.expunge_all()
    with sentencias(engine) as vistas, actor_scope(SYSTEM_USER_ID), pytest.raises(InvalidField):
        await service.contact_for_notification(session, socio, "notify", fields={"document"})
    await session.rollback()
    assert [s for s in vistas if "members.members" in s] == []


# load_only (S5-D204) -----------------------------------------------------------------------------


def _select_de_socios(vistas: list[str]) -> str:
    candidatas = [
        s for s in vistas if s.lstrip().upper().startswith("SELECT") and "FROM members.members" in s
    ]
    assert len(candidatas) == 1, candidatas
    return candidatas[0].split(" FROM ")[0]


@pytest.mark.parametrize("fields", [{"phone"}, {"email"}, None], ids=["phone", "email", "defecto"])
async def test_el_select_de_socios_solo_pide_las_columnas_del_aviso(
    session: AsyncSession, listo: Keyring, engine: AsyncEngine, fields: Any
) -> None:
    socio = await socio_consentido(session)
    session.expunge_all()
    with sentencias(engine) as vistas:
        await contactar(session, socio, fields=fields)
    lista = _select_de_socios(vistas)
    for columna in ("first_name", "phone", "email", "deleted_at", "data_consent_at"):
        assert re.search(rf"\bmembers\.{columna}\b", lista), (columna, lista)
    for columna in COLUMNAS_PROHIBIDAS_EN_EL_SELECT:
        assert not re.search(rf"\bmembers\.{columna}\b", lista), (columna, lista)


# Consentimiento (S5-D34) -------------------------------------------------------------------------


@pytest.mark.parametrize("fields", [None, {"phone"}, {"email"}], ids=["defecto", "phone", "email"])
async def test_notify_sin_autorizacion_lanza_member_not_contactable_sin_descifrar_ni_auditar(
    session: AsyncSession, listo: Keyring, fields: Any
) -> None:
    socio = (await make_member(session)).id  # sin `data_consent_at`
    session.expunge_all()
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()), pytest.raises(MemberNotContactable):
        await service.contact_for_notification(session, socio, "notify", fields=fields)
    await session.rollback()
    assert await operaciones(session, verb="decrypt", record_id=socio) == []
    assert await auditoria_del_socio(session, socio, "reveal") == []


async def test_notify_con_autorizacion_si_devuelve_el_contacto(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session)
    contacto = await contactar(session, socio, "notify")
    assert (contacto.phone, contacto.email) == (TELEFONO, CORREO)


async def test_auth_link_no_exige_la_autorizacion_de_datos(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = (await make_member(session)).id  # sin `data_consent_at`
    contacto = await contactar(session, socio, "auth_link", fields={"email"})
    assert (contacto.phone, contacto.email) == (None, CORREO)
    assert await contar_crypto_ops(session, socio, "decrypt", "auth_link") == 1


async def test_el_aviso_a_un_dado_de_baja_con_autorizacion_sigue_siendo_no_contactable(
    session: AsyncSession, listo: Keyring
) -> None:
    socio = await socio_consentido(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    session.expunge_all()
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()), pytest.raises(MemberNotContactable):
        await service.contact_for_notification(session, socio, "notify", fields={"phone"})
    await session.rollback()
    assert await operaciones(session, verb="decrypt", record_id=socio) == []
