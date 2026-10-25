"""`members.service.create` y los contratos para otros módulos, con PostgreSQL real (S2-B7;
US-069 criterios 1, 3 a 6, 8 a 10; M-4, L-3; blueprint B7).

Alta:
- `"1.020.304"` y `"1020304"` dan el mismo `document_idx` (`bus.blind_index`); un documento de
  otro socio no borrado da `MemberDocumentDuplicated` (409, `field="document"`, `existing_id`) y
  no crea nada; uno que solo tiene un socio dado de baja no bloquea; en la carrera (dos altas a
  la vez, `dos_sesiones`) una gana y la otra recibe el 409.
- una fila `insert` de auditoría en `members.members` con los cinco campos como blob,
  `subject_member_id = id` y el actor como `user_id`; `created_by` es el actor;
- `MemberCreated(member_id)` en la misma transacción: si un handler falla, no queda el socio;
- `data_consent=True` fija `data_consent_at` con el reloj del servidor (M-4) y
  `data_consent_version` queda nula; sin autorización, `warnings == ["data_consent_missing"]`;
- la respuesta sale enmascarada de la entrada: en `crypto_ops` solo hay `encrypt` e `index` del
  socio y ningún `decrypt`.
Contratos: `get_ref`, `ensure_exists`, `id_by_document` y `count`.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from app.core.events import DomainEvent
from app.modules.members import service
from app.modules.members.exceptions import (
    MemberDocumentDuplicated,
    MemberNotFound,
    MemberValidationError,
)
from app.modules.members.schemas import MemberDetailOut, MemberRef
from app.modules.members.service import MemberCreated
from tests.auth._cuentas import filas_auditoria
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED, make_member, unique_document
from tests.members._apoyo import (
    CAMPOS_DETALLE,
    MASCARAS_KNOWN,
    crear,
    cuantos_socios,
    entrada,
    fila_socio,
    operaciones,
)

CIFRADOS = ("document", "phone", "email", "birth_date", "emergency_contact")


class HandlerRoto(Exception):
    """Falla de un suscriptor de `MemberCreated`. No hereda de `RuntimeError`: `NotImplementedError`
    sí, y la prueba pasaría sobre los stubs."""


@pytest.fixture
async def admin(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    """Admin real con el bus listo en el savepoint de la prueba.

    La carrera no lo usa: `bus_listo` borra `crypto_keys` dentro de la transacción de `session`
    y dejaría esperando a las conexiones de `dos_sesiones` y `bus_confirmado`."""
    return await usuario_real("admin")


def _indice(documento: str) -> str:
    return bus.blind_index("member.document", documento)


# Alta ------------------------------------------------------------------------------------


async def test_crea_el_socio_activo_y_responde_enmascarado(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada())
    assert isinstance(salida, MemberDetailOut)
    assert set(salida.model_dump()) == CAMPOS_DETALLE
    assert salida.first_name == "Lucía" and salida.last_name == "Gómez"
    assert salida.status == "active"
    assert salida.sex == "f"
    assert salida.document_type == "CC"
    for campo, mascara in MASCARAS_KNOWN.items():
        assert getattr(salida, campo) == mascara, campo
    assert salida.deleted_at is None
    # PL4 de la revisión de Fase 4 del Sprint 3: el alta responde `"none"`, como la ficha.
    assert salida.membership_status == "none"
    assert salida.warnings == []
    assert salida.created_at is not None and salida.updated_at is not None
    fila = await fila_socio(session, salida.id)
    assert fila["status"] == "active" and fila["document_type"] == "CC"
    assert fila["created_by"] == admin.id


async def test_el_documento_con_puntos_y_sin_puntos_da_el_mismo_indice(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada(document="1.020.304", phone=None, email=None))
    fila = await fila_socio(session, salida.id)
    assert fila["document_idx"] == _indice("1020304") == _indice("1.020.304")
    assert salida.document == "CC •••• 0304"
    assert await service.id_by_document(session, "1020304") == salida.id
    assert await service.id_by_document(session, "1.020.304") == salida.id


async def test_telefono_y_correo_llenan_sus_indices_y_sin_ellos_quedan_nulos(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    completo = await crear(session, admin.id, entrada())
    fila = await fila_socio(session, completo.id)
    assert fila["phone_idx"] == bus.blind_index("member.phone", "3007654321")
    assert fila["email_idx"] == bus.blind_index("member.email", "lucia.gomez@correo.co")
    minimo = await crear(
        session,
        admin.id,
        entrada(
            document=unique_document(),
            phone=None,
            email=None,
            birth_date=None,
            emergency_contact=None,
            sex=None,
        ),
    )
    fila = await fila_socio(session, minimo.id)
    for columna in (*CIFRADOS[1:], "phone_idx", "email_idx", "sex"):
        assert fila[columna] is None, columna
    assert minimo.phone is None and minimo.email is None
    assert minimo.birth_date is None and minimo.emergency_contact is None


async def test_documento_duplicado_entre_vivos_da_409_con_existing_id_y_no_crea_nada(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    primero = await crear(session, admin.id, entrada(document="1.020.304"))
    with actor_scope(admin.id), pytest.raises(MemberDocumentDuplicated) as error:
        await service.create(session, entrada(document="1020304", phone=None, email=None))
    await session.rollback()
    assert error.value.status == 409
    assert error.value.code == "member_document_duplicated"
    assert error.value.field == "document"
    assert error.value.existing_id == primero.id
    assert error.value.message == "Ya existe un socio con este documento"
    assert "1020304" not in error.value.message
    assert await cuantos_socios(session, document_idx=_indice("1020304")) == 1


async def test_un_documento_de_un_socio_dado_de_baja_no_bloquea(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    baja = await make_member(session, document="1020304", phone=None, email=None, deleted_at=T0)
    nuevo = await crear(session, admin.id, entrada(document="1.020.304"))
    assert nuevo.id != baja.id
    assert await cuantos_socios(session, document_idx=_indice("1020304")) == 2
    assert await service.id_by_document(session, "1020304") == nuevo.id


async def test_carrera_de_dos_altas_con_el_mismo_documento_una_gana_y_la_otra_da_409(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    """Ambas pasan el pre-chequeo; `uq_members_document_idx_alive` decide dentro de un
    `begin_nested()` y el `IntegrityError` se traduce a `MemberDocumentDuplicated`."""
    primera, segunda = dos_sesiones
    documento = unique_document()

    async def alta(sesion: AsyncSession) -> Any:
        try:
            with actor_scope(SYSTEM_USER_ID):
                salida = await service.create(
                    sesion, entrada(document=documento, phone=None, email=None)
                )
                await sesion.commit()
            return salida
        except MemberDocumentDuplicated as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(alta(primera), alta(segunda), return_exceptions=True)
    creados = [r for r in resultados if isinstance(r, MemberDetailOut)]
    duplicados = [r for r in resultados if isinstance(r, MemberDocumentDuplicated)]
    assert len(creados) == 1 and len(duplicados) == 1, resultados
    assert duplicados[0].existing_id in (None, creados[0].id)
    assert duplicados[0].field == "document"


async def test_deja_una_fila_insert_de_auditoria_con_blobs_y_el_socio_como_sujeto(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada())
    filas = await filas_auditoria(session, "members.members", salida.id)
    assert [(f["action"], f["user_id"]) for f in filas] == [("insert", admin.id)]
    (fila,) = filas
    assert fila["subject_member_id"] == salida.id
    despues = fila["after"]
    for campo in CIFRADOS:
        assert str(despues[campo]).startswith("apx1."), campo
    assert despues["created_by"] == str(admin.id)
    assert "notes" not in despues
    volcado = json.dumps(filas, default=str)
    for valor in KNOWN_NORMALIZED:
        assert valor not in volcado, valor
    assert "Secret(" not in volcado


async def test_emite_member_created_con_el_id_del_socio(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(MemberCreated)
    salida = await crear(session, admin.id, entrada())
    assert recibidos == [MemberCreated(member_id=salida.id, occurred_at=T0)]


async def test_si_un_handler_de_member_created_falla_el_socio_no_queda(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    vistos: list[UUID] = []

    async def roto(evento: DomainEvent, sesion: AsyncSession) -> None:
        assert isinstance(evento, MemberCreated)
        vistos.append(evento.member_id)
        raise HandlerRoto("falla a propósito")

    events.subscribe(MemberCreated, roto)  # `restaurar_bus` lo quita al salir
    documento = unique_document()
    with actor_scope(admin.id), pytest.raises(HandlerRoto):
        await service.create(session, entrada(document=documento))
    await session.rollback()
    assert len(vistos) == 1
    assert await cuantos_socios(session, document_idx=_indice(documento)) == 0
    assert await filas_auditoria(session, "members.members", vistos[0]) == []


async def test_con_autorizacion_la_fecha_es_la_del_reloj_del_servidor(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    reloj.advance(hours=3)
    salida = await crear(session, admin.id, entrada(data_consent=True))
    assert salida.data_consent_at == T0 + timedelta(hours=3)
    assert salida.data_consent_version is None
    assert salida.warnings == []
    fila = await fila_socio(session, salida.id)
    assert fila["data_consent_at"] == T0 + timedelta(hours=3)
    assert fila["data_consent_version"] is None


async def test_sin_autorizacion_avisa_y_no_guarda_fecha(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada(data_consent=False))
    assert salida.warnings == ["data_consent_missing"]
    assert salida.data_consent_at is None
    fila = await fila_socio(session, salida.id)
    assert fila["data_consent_at"] is None and fila["data_consent_version"] is None


async def test_la_respuesta_no_descifra_nada_solo_cifra_e_indexa(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    descifrados_antes = len(await operaciones(session, verb="decrypt"))
    salida = await crear(session, admin.id, entrada())
    assert len(await operaciones(session, verb="decrypt")) == descifrados_antes
    del_socio = await operaciones(session, record_id=salida.id)
    verbos = Counter(f["verb"] for f in del_socio)
    assert set(verbos) == {"encrypt", "index"}, verbos
    assert verbos["encrypt"] == len(CIFRADOS)
    assert verbos["index"] >= 3  # document, phone y email
    assert {f["user_id"] for f in del_socio} == {admin.id}


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"birth_date": date(2026, 10, 22)}, "birth_date"),
        ({"document": "..."}, "document"),
        ({"phone": "+57"}, "phone"),
    ],
)
async def test_una_entrada_invalida_da_422_con_field_y_no_crea_nada(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    cambios: dict[str, Any],
    campo: str,
) -> None:
    """`birth_date` de mañana en Bogotá (`T0` es 2026-10-21); L-3 sin 500."""
    antes = await cuantos_socios(session)
    with actor_scope(admin.id), pytest.raises(MemberValidationError) as error:
        await service.create(session, entrada(**cambios))
    await session.rollback()
    assert error.value.field == campo and error.value.status == 422
    assert await cuantos_socios(session) == antes


# Contratos para otros módulos ------------------------------------------------------------


async def test_get_ref_devuelve_la_dataclass_y_no_el_orm(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    vivo = await make_member(session, document=unique_document(), phone=None, email=None)
    baja = await make_member(
        session, document=unique_document(), phone=None, email=None, deleted_at=T0
    )
    ref = await service.get_ref(session, vivo.id)
    assert ref == MemberRef(
        id=vivo.id, first_name="Lucía", last_name="Gómez", status="active", is_deleted=False
    )
    assert (await service.get_ref(session, baja.id)).is_deleted is True
    with pytest.raises(MemberNotFound) as error:
        await service.get_ref(session, uuid4())
    assert error.value.status == 404 and error.value.code == "member_not_found"


async def test_ensure_exists_con_y_sin_borrados(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    vivo = await make_member(session, document=unique_document(), phone=None, email=None)
    baja = await make_member(
        session, document=unique_document(), phone=None, email=None, deleted_at=T0
    )
    await service.ensure_exists(session, vivo.id)  # no lanza
    with pytest.raises(MemberNotFound):
        await service.ensure_exists(session, baja.id)
    await service.ensure_exists(session, baja.id, include_deleted=True)  # no lanza
    with pytest.raises(MemberNotFound):
        await service.ensure_exists(session, uuid4(), include_deleted=True)


async def test_id_by_document_solo_entre_no_borrados(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    vivo = await make_member(session, document="1.020.304", phone=None, email=None)
    await make_member(session, document="5550001", phone=None, email=None, deleted_at=T0)
    assert await service.id_by_document(session, "1020304") == vivo.id
    assert await service.id_by_document(session, "5550001") is None
    assert await service.id_by_document(session, unique_document()) is None


async def test_count_con_y_sin_borrados(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    antes_vivos = await service.count(session)
    antes_todos = await service.count(session, include_deleted=True)
    for _ in range(3):
        await make_member(session, document=unique_document(), phone=None, email=None)
    await make_member(session, document=unique_document(), phone=None, email=None, deleted_at=T0)
    assert await service.count(session) == antes_vivos + 3
    assert await service.count(session, include_deleted=True) == antes_todos + 4
