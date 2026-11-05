"""`members.service.channels_for`, `get_channels` y `set_channels` con PostgreSQL real
(S5-B5, US-123; S5-D31, N-20, N-33). # Rojo B5

- `channels_for(session, member_ids)`: lectura por lote, UNA consulta a
  `members.member_channel_preferences`; un socio sin filas recibe los valores por defecto
  (con consentimiento `{whatsapp_link}`, sin él el conjunto vacío); sin ids no consulta nada.
- `get_channels`: `ChannelsOut(member_id, channels, effective, has_consent)`; también sobre un
  socio dado de baja (N-20); un id inexistente da `MemberNotFound`.
- `set_channels(session, member_id, items, by)`: toma `lock_member` primero; upsert por
  `(member_id, channel)` (una sola fila por par, `created_by` del primer insert); un socio dado de
  baja da `MemberDeleted` (409 `member_deleted`) sin escribir; emite `MemberUpdated` con el id y
  los nombres de los campos cambiados, nunca los valores; audita con `subject_member_id`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy
from app.core.locks import lock_member
from app.modules.members import service
from app.modules.members.exceptions import ConsentRequired, MemberDeleted, MemberNotFound
from app.modules.members.schemas import ChannelItem, ChannelsPatch, MemberChannelState
from tests.conftest import T0, CapturarEventos, ContadorDeConsultas, CrearUsuario, UsuarioPrueba
from tests.factories.members import make_member, unique_document
from tests.members._apoyo import peticion

WA = "whatsapp_link"
CORREO = "email"
TABLA = "members.member_channel_preferences"
OTRO_ACTOR = UUID("0000000a-0000-4000-8000-00000000b501")


@pytest.fixture
async def staff(
    usuario_real: CrearUsuario, bus_listo: Keyring, reloj: FrozenClock
) -> UsuarioPrueba:
    return await usuario_real("coach")


async def socio_con(session: AsyncSession, *, consentimiento: bool = True, **cambios: Any) -> UUID:
    """Un socio con (o sin) autorización de datos; solo devuelve el id."""
    valores: dict[str, Any] = {"document": unique_document(), "phone": None, "email": None}
    if consentimiento:
        valores["data_consent_at"] = T0 - timedelta(days=1)
    valores.update(cambios)
    socio = await make_member(session, **valores)
    return socio.id


async def preferencias_de(session: AsyncSession, member_id: UUID) -> dict[str, dict[str, Any]]:
    filas = (
        await session.execute(
            text(f"SELECT * FROM {TABLA} WHERE member_id = :m"),  # noqa: S608
            {"m": member_id},
        )
    ).mappings()
    return {f["channel"]: dict(f) for f in filas}


async def fijar(session: AsyncSession, member_id: UUID, items: list[ChannelItem], by: UUID) -> Any:
    """Una petición de staff: `set_channels` bajo el actor y commit."""
    with peticion(session, by):
        salida = await service.set_channels(session, member_id, items, by)
        await session.commit()
    return salida


# channels_for: lectura por lote ------------------------------------------------------------------


async def test_channels_for_da_los_valores_por_defecto_a_los_socios_sin_filas(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    con = await socio_con(session)
    sin = await socio_con(session, consentimiento=False)
    efectivos = await service.channels_for(session, [con, sin])
    assert efectivos == {
        con: MemberChannelState(True, frozenset({WA})),
        sin: MemberChannelState(False, frozenset()),
    }


async def test_channels_for_aplica_las_filas_explicitas_de_cada_socio(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    solo_correo = await socio_con(session)
    sin_whatsapp = await socio_con(session)
    mudo = await socio_con(session)
    await fijar(session, solo_correo, [ChannelItem(channel=CORREO, active=True)], staff.id)
    await fijar(session, sin_whatsapp, [ChannelItem(channel=WA, active=False)], staff.id)
    await fijar(
        session,
        mudo,
        [ChannelItem(channel=WA, active=False), ChannelItem(channel=CORREO, active=False)],
        staff.id,
    )
    session.expunge_all()
    efectivos = await service.channels_for(session, [solo_correo, sin_whatsapp, mudo])
    assert efectivos == {
        solo_correo: MemberChannelState(True, frozenset({WA, CORREO})),
        sin_whatsapp: MemberChannelState(True, frozenset()),
        mudo: MemberChannelState(True, frozenset()),
    }


async def test_channels_for_hace_una_sola_consulta_a_las_preferencias_para_varios_socios(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    ids = [await socio_con(session) for _ in range(5)]
    session.expunge_all()
    with contador_de_consultas.midiendo():
        await service.channels_for(session, ids)
    assert contador_de_consultas.de(TABLA) == 1


async def test_channels_for_sin_ids_da_un_dict_vacio_y_no_consulta(
    session: AsyncSession,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    with contador_de_consultas.midiendo():
        efectivos = await service.channels_for(session, [])
    assert efectivos == {}
    assert contador_de_consultas.de(TABLA) == 0


# get_channels --------------------------------------------------------------------------------


async def test_get_channels_sin_filas_da_whatsapp_por_defecto_con_consentimiento(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await socio_con(session)
    salida = await service.get_channels(session, socio)
    assert salida.member_id == socio
    assert salida.channels == []
    assert salida.effective == [WA]
    assert salida.has_consent is True


async def test_get_channels_sin_consentimiento_no_tiene_canales_efectivos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, consentimiento=False)
    salida = await service.get_channels(session, socio)
    assert (salida.effective, salida.has_consent) == ([], False)


async def test_get_channels_responde_tambien_sobre_un_dado_de_baja(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    salida = await service.get_channels(session, socio)
    assert salida.member_id == socio


async def test_get_channels_de_un_id_inexistente_da_member_not_found(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    with pytest.raises(MemberNotFound):
        await service.get_channels(session, uuid4())


# set_channels --------------------------------------------------------------------------------


async def test_set_channels_inserta_la_fila_y_responde_con_los_canales_efectivos(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session)
    salida = await fijar(session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id)
    filas = await preferencias_de(session, socio)
    assert set(filas) == {CORREO}
    assert filas[CORREO]["active"] is True
    assert filas[CORREO]["created_by"] == staff.id
    assert [(i.channel, i.active) for i in salida.channels] == [(CORREO, True)]
    assert sorted(salida.effective) == sorted([WA, CORREO])
    assert salida.has_consent is True


async def test_set_channels_hace_upsert_y_deja_una_sola_fila_por_canal(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session)
    await fijar(session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id)
    primera = (await preferencias_de(session, socio))[CORREO]
    reloj.advance(minutes=5)
    await fijar(session, socio, [ChannelItem(channel=CORREO, active=False)], OTRO_ACTOR)
    filas = await preferencias_de(session, socio)
    assert list(filas) == [CORREO]
    assert filas[CORREO]["active"] is False
    assert filas[CORREO]["id"] == primera["id"]
    assert filas[CORREO]["created_by"] == staff.id


async def test_set_channels_acepta_los_dos_canales_a_la_vez(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session)
    salida = await fijar(
        session,
        socio,
        [ChannelItem(channel=WA, active=False), ChannelItem(channel=CORREO, active=True)],
        staff.id,
    )
    filas = await preferencias_de(session, socio)
    assert {c: f["active"] for c, f in filas.items()} == {WA: False, CORREO: True}
    assert salida.effective == [CORREO]


async def test_set_channels_de_un_socio_dado_de_baja_da_409_member_deleted_sin_escribir(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    with pytest.raises(MemberDeleted) as capturado, peticion(session, staff.id):
        await service.set_channels(
            session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id
        )
    await session.rollback()
    assert (capturado.value.status, capturado.value.code) == (409, "member_deleted")
    assert await preferencias_de(session, socio) == {}


async def test_set_channels_de_un_id_inexistente_da_member_not_found(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    with pytest.raises(MemberNotFound), peticion(session, staff.id):
        await service.set_channels(
            session, uuid4(), [ChannelItem(channel=CORREO, active=True)], staff.id
        )
    await session.rollback()


async def test_set_channels_emite_member_updated_sin_valores(
    session: AsyncSession,
    staff: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    socio = await socio_con(session)
    recibidos = capturar_eventos(service.MemberUpdated)
    await fijar(session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id)
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert evento.member_id == socio
    assert isinstance(evento.changed_fields, tuple) and evento.changed_fields
    assert all(isinstance(c, str) for c in evento.changed_fields)
    volcado = repr(evento).lower()
    for valor in ("true", "false", "@"):
        assert valor not in volcado, valor


async def test_set_channels_audita_la_fila_con_el_socio_como_sujeto(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session)
    await fijar(session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id)
    filas = (
        (
            await session.execute(
                text(
                    "SELECT action, subject_member_id, user_id FROM audit.audit_log "
                    "WHERE table_name = 'members.member_channel_preferences' "
                    "AND subject_member_id = :m "
                    "ORDER BY seq"
                ),
                {"m": socio},
            )
        )
        .mappings()
        .all()
    )
    assert [(f["action"], f["subject_member_id"]) for f in filas] == [("insert", socio)]
    assert filas[0]["user_id"] == staff.id


async def test_set_channels_espera_el_candado_del_socio(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    """Otra transacción tiene `lock_member`: `set_channels` espera y, con `lock_timeout` de 300 ms,
    termina en `DatabaseBusy` sin escribir (el candado del socio es lo primero)."""
    primera, segunda = dos_sesiones
    socio = await make_member(primera, document=unique_document(), phone=None, email=None)
    socio_id = socio.id
    await lock_member(primera, socio_id)
    try:
        with actor_scope(OTRO_ACTOR), pytest.raises(DatabaseBusy):
            await segunda.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await service.set_channels(
                segunda, socio_id, [ChannelItem(channel=CORREO, active=True)], OTRO_ACTOR
            )
        await segunda.rollback()
    finally:
        await primera.rollback()
    assert await preferencias_de(primera, socio_id) == {}


# Consentimiento obligatorio para el opt-in de correo (S5-D211) ------------------------------------


async def test_set_channels_rechaza_el_correo_activo_sin_consentimiento_sin_escribir(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, consentimiento=False)
    with pytest.raises(ConsentRequired) as capturado, peticion(session, staff.id):
        await service.set_channels(
            session, socio, [ChannelItem(channel=CORREO, active=True)], staff.id
        )
    await session.rollback()
    assert (capturado.value.status, capturado.value.code) == (422, "consent_required")
    assert await preferencias_de(session, socio) == {}


async def test_set_channels_rechaza_todo_el_lote_si_un_item_exige_consentimiento(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, consentimiento=False)
    items = [ChannelItem(channel=WA, active=False), ChannelItem(channel=CORREO, active=True)]
    with pytest.raises(ConsentRequired), peticion(session, staff.id):
        await service.set_channels(session, socio, items, staff.id)
    await session.rollback()
    assert await preferencias_de(session, socio) == {}


async def test_set_channels_permite_desactivar_canales_sin_consentimiento(
    session: AsyncSession, staff: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await socio_con(session, consentimiento=False)
    salida = await fijar(
        session,
        socio,
        [ChannelItem(channel=WA, active=False), ChannelItem(channel=CORREO, active=False)],
        staff.id,
    )
    filas = await preferencias_de(session, socio)
    assert {c: f["active"] for c, f in filas.items()} == {WA: False, CORREO: False}
    assert (salida.effective, salida.has_consent) == ([], False)


def test_channels_patch_rechaza_canales_repetidos() -> None:
    with pytest.raises(ValueError, match="repetid"):
        ChannelsPatch(
            items=[
                ChannelItem(channel=CORREO, active=True),
                ChannelItem(channel=CORREO, active=False),
            ]
        )


async def test_channels_for_incluye_a_los_dados_de_baja_y_omite_a_los_inexistentes(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    baja = await socio_con(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    efectivos = await service.channels_for(session, [baja, uuid4()])
    assert efectivos == {baja: MemberChannelState(True, frozenset({WA}))}
