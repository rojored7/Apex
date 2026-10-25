"""`members.service.update` con PostgreSQL real (S3-B10; US-075; D21, M-3, L-1, S3-D46, S3-D54;
blueprint B10 y demo 6).

- Cambiar el teléfono cambia el blob (nonce nuevo), descifra al valor nuevo, recalcula
  `phone_idx` y la búsqueda por el número viejo ya no encuentra al socio; `null` lo borra.
- El admin cambia el documento: reindexa (`document_idx`, `id_by_document`) y la máscara cambia.
  Un documento de otro socio vivo da `MemberDocumentDuplicated` con `existing_id` y ningún cambio
  parcial; en la carrera (dos ediciones a la vez, `dos_sesiones`) decide
  `uq_members_document_idx_alive` y la perdedora recibe el 409.
- Un coach con `document` o `document_type` en el cuerpo recibe `MemberFieldForbidden` (por
  presencia, M-3) y nada cambia.
- Un socio dado de baja da `MemberIsDeactivated` (409); un id inexistente `MemberNotFound`.
- Auditoría `update` solo con las columnas cambiadas (`phone` y `phone_idx`, nunca `first_name`),
  los `*_idx` como `"***"` y sin ningún valor en claro. Un PATCH sin cambios efectivos (mismos
  valores o solo de formato) no hace `UPDATE`, no audita y no emite.
- `MemberUpdated(member_id, changed_fields)` con los nombres de las columnas cambiadas en orden
  alfabético (sin `*_idx` ni valores).
- `data_consent=true` sobre una autorización nula fija `data_consent_at` con el reloj; sobre una
  existente no la reescribe (y no audita); `false` da `ConsentCannotBeWithdrawn` (422,
  `field="data_consent"`).
- Las reglas del alta valen también aquí: fecha de nacimiento futura, teléfono sin dígitos y
  documento que se normaliza a vacío dan `MemberValidationError` con `field`.
- La respuesta es la ficha enmascarada (`CAMPOS_DETALLE`, con la membresía que decide) y
  `warnings == ["data_consent_missing"]` mientras no haya autorización.
- `update` toma `lock_member` (S3-D54): con el candado del socio tomado por otra transacción,
  espera y con `lock_timeout` corto termina en `DatabaseBusy`.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy
from app.core.locks import lock_member
from app.modules.members import service
from app.modules.members.exceptions import (
    ConsentCannotBeWithdrawn,
    MemberDocumentDuplicated,
    MemberFieldForbidden,
    MemberIsDeactivated,
    MemberNotFound,
    MemberValidationError,
)
from app.modules.members.schemas import MemberDetailOut, MemberPatch
from tests.conftest import T0, CapturarEventos, ContadorDeConsultas, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import (
    CAMPOS_DETALLE,
    MASCARAS_KNOWN,
    auditoria_del_socio,
    descifrar,
    fila_socio,
    peticion,
)

TELEFONO_NUEVO = "+57 310 555 0000"
TELEFONO_NUEVO_NORMALIZADO = "3105550000"


@pytest.fixture
async def coach(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("coach")


@pytest.fixture
async def admin(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("admin")


async def editar(
    session: AsyncSession, quien: UsuarioPrueba, member_id: UUID, **campos: Any
) -> MemberDetailOut:
    """Una petición: `service.update` con el rol del usuario, bajo su actor, y commit."""
    patch = MemberPatch.model_validate(campos)
    with peticion(session, quien.id):
        salida = await service.update(session, member_id, patch, role=quien.role)
        await session.commit()
    return salida


async def editar_y_fallar(
    session: AsyncSession,
    quien: UsuarioPrueba,
    member_id: UUID,
    error: type[Exception],
    **campos: Any,
) -> Any:
    patch = MemberPatch.model_validate(campos)
    with pytest.raises(error) as capturado, peticion(session, quien.id):
        await service.update(session, member_id, patch, role=quien.role)
    await session.rollback()
    return capturado.value


def _nonce(blob: str) -> str:
    return blob.split(".")[3]


def _updates_de_members(contador: ContadorDeConsultas) -> list[str]:
    return [s for s in contador.sentencias if s.lstrip().upper().startswith("UPDATE MEMBERS.")]


# Teléfono: recifrar y reindexar ---------------------------------------------------------------


async def test_cambiar_el_telefono_recifra_y_reindexa(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    antes = await fila_socio(session, socio.id)
    salida = await editar(session, coach, socio.id, phone=TELEFONO_NUEVO)
    despues = await fila_socio(session, socio.id)
    assert despues["phone"] != antes["phone"]
    assert despues["phone"].startswith("apx1.")
    assert _nonce(despues["phone"]) != _nonce(antes["phone"])
    assert despues["phone_idx"] == bus.blind_index("member.phone", TELEFONO_NUEVO_NORMALIZADO)
    assert despues["phone_idx"] != antes["phone_idx"]
    for columna in ("document", "document_idx", "email", "email_idx", "birth_date"):
        assert despues[columna] == antes[columna], columna
    assert salida.phone == "••• ••• 0000"
    assert descifrar(despues["phone"], socio.id) == TELEFONO_NUEVO


async def test_la_busqueda_por_el_telefono_viejo_ya_no_lo_encuentra(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    assert await service.search_ids(session, "3007654321") == {socio.id}
    await editar(session, coach, socio.id, phone=TELEFONO_NUEVO)
    assert await service.search_ids(session, "3007654321") == set()
    assert await service.search_ids(session, TELEFONO_NUEVO_NORMALIZADO) == {socio.id}


async def test_null_borra_el_telefono_y_su_indice(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    salida = await editar(session, coach, socio.id, phone=None)
    fila = await fila_socio(session, socio.id)
    assert fila["phone"] is None and fila["phone_idx"] is None
    assert salida.phone is None


async def test_cambiar_nombres_y_correo_por_el_coach(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    salida = await editar(
        session, coach, socio.id, first_name="Lucy", email="Lucy.G@Correo.co", sex="x"
    )
    fila = await fila_socio(session, socio.id)
    assert (fila["first_name"], fila["last_name"], fila["sex"]) == ("Lucy", "Gómez", "x")
    assert fila["email_idx"] == bus.blind_index("member.email", "lucy.g@correo.co")
    assert salida.first_name == "Lucy" and salida.email == "l•••@•••.co"


# Documento: solo admin, reindexa y decide el índice único -------------------------------------


async def test_el_admin_cambia_el_documento_y_reindexa(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    salida = await editar(session, admin, socio.id, document="1.020.304.417", document_type="CE")
    fila = await fila_socio(session, socio.id)
    assert fila["document_idx"] == bus.blind_index("member.document", "1020304417")
    assert fila["document_type"] == "CE"
    assert await service.id_by_document(session, "1020304417") == socio.id
    assert await service.id_by_document(session, KNOWN["document"]) is None
    assert salida.document == "CE •••• 4417"


async def test_un_documento_de_otro_socio_vivo_da_409_sin_cambios_parciales(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    otro_documento = unique_document()
    otro = await make_member(session, document=otro_documento, phone=None, email=None)
    antes = await fila_socio(session, socio.id)
    error = await editar_y_fallar(
        session,
        admin,
        socio.id,
        MemberDocumentDuplicated,
        first_name="Otra",
        phone=TELEFONO_NUEVO,
        document=otro_documento,
    )
    assert (error.status, error.code, error.field) == (
        409,
        "member_document_duplicated",
        "document",
    )
    assert error.existing_id == otro.id
    assert otro_documento not in error.message
    assert await fila_socio(session, socio.id) == antes
    assert [f["action"] for f in await auditoria_del_socio(session, socio.id)] == ["insert"]


async def test_el_documento_de_un_dado_de_baja_no_bloquea(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    libre = unique_document()
    await make_member(
        session, document=libre, phone=None, email=None, deleted_at=T0 - timedelta(days=2)
    )
    await editar(session, admin, socio.id, document=libre)
    assert await service.id_by_document(session, libre) == socio.id


async def test_carrera_de_dos_ediciones_al_mismo_documento_decide_el_indice_unico(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    """Dos socios distintos (dos candados distintos) piden a la vez el mismo documento libre:
    ambas pasan el pre-chequeo y `uq_members_document_idx_alive` decide; la perdedora recibe
    `MemberDocumentDuplicated` con el `existing_id` de la ganadora."""
    primera, segunda = dos_sesiones
    uno = await make_member(primera, document=unique_document(), phone=None, email=None)
    dos = await make_member(primera, document=unique_document(), phone=None, email=None)
    documento = unique_document()
    actor = UUID("0000000a-0000-4000-8000-00000000b10c")

    async def cambiar(sesion: AsyncSession, member_id: UUID) -> Any:
        try:
            with actor_scope(actor):
                salida = await service.update(
                    sesion, member_id, MemberPatch(document=documento), role="admin"
                )
                await sesion.commit()
            return member_id, salida
        except MemberDocumentDuplicated as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(
        cambiar(primera, uno.id), cambiar(segunda, dos.id), return_exceptions=True
    )
    ganadores = [r for r in resultados if isinstance(r, tuple)]
    perdedores = [r for r in resultados if isinstance(r, MemberDocumentDuplicated)]
    assert len(ganadores) == 1 and len(perdedores) == 1, resultados
    assert perdedores[0].existing_id == ganadores[0][0]
    assert perdedores[0].field == "document"


@pytest.mark.parametrize(
    "campos",
    [
        {"document": KNOWN["document"]},
        {"document": "7.319.582.046"},
        {"document": "55667788"},
        {"document_type": "CC"},
        {"document_type": "PA"},
        {"phone": TELEFONO_NUEVO, "document": KNOWN["document"]},
    ],
    ids=["mismo", "mismo-con-puntos", "distinto", "mismo-tipo", "otro-tipo", "con-telefono"],
)
async def test_el_coach_con_documento_o_tipo_recibe_403_y_nada_cambia(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock, campos: dict[str, Any]
) -> None:
    socio = await make_member(session)
    antes = await fila_socio(session, socio.id)
    error = await editar_y_fallar(session, coach, socio.id, MemberFieldForbidden, **campos)
    esperado = "document" if "document" in campos else "document_type"
    assert (error.status, error.code, error.field) == (403, "forbidden_field", esperado)
    assert await fila_socio(session, socio.id) == antes


# Baja e inexistente --------------------------------------------------------------------------


async def test_un_dado_de_baja_da_409_member_deactivated(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    antes = await fila_socio(session, socio.id)
    error = await editar_y_fallar(session, admin, socio.id, MemberIsDeactivated, first_name="Otra")
    assert (error.status, error.code) == (409, "member_deactivated")
    assert await fila_socio(session, socio.id) == antes


async def test_un_id_inexistente_da_member_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    inexistente = UUID("00000000-0000-4000-8000-00000000b10d")
    error = await editar_y_fallar(session, admin, inexistente, MemberNotFound, first_name="Otra")
    assert error.status == 404


# Auditoría y evento --------------------------------------------------------------------------


async def test_la_auditoria_update_solo_lleva_las_columnas_cambiadas(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await editar(session, coach, socio.id, phone=TELEFONO_NUEVO, first_name="Lucía")
    updates = await auditoria_del_socio(session, socio.id, "update")
    assert len(updates) == 1
    (fila,) = updates
    assert fila["user_id"] == coach.id
    assert fila["subject_member_id"] == socio.id
    assert set(fila["before"]) == {"phone", "phone_idx"}
    assert set(fila["after"]) == {"phone", "phone_idx"}
    assert fila["before"]["phone_idx"] == "***" and fila["after"]["phone_idx"] == "***"
    assert str(fila["after"]["phone"]).startswith("apx1.")
    volcado = json.dumps([fila["before"], fila["after"]])
    for valor in (*KNOWN_NORMALIZED, TELEFONO_NUEVO, TELEFONO_NUEVO_NORMALIZADO):
        assert valor not in volcado, valor


async def test_los_indices_del_documento_y_el_correo_salen_como_asteriscos(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    await editar(session, admin, socio.id, document=unique_document(), email="otra@correo.co")
    (fila,) = await auditoria_del_socio(session, socio.id, "update")
    assert set(fila["before"]) == {"document", "document_idx", "email", "email_idx"}
    for indice in ("document_idx", "email_idx"):
        assert fila["before"][indice] == "***" and fila["after"][indice] == "***"


async def test_un_patch_sin_cambios_efectivos_no_actualiza_ni_audita_ni_emite(
    session: AsyncSession,
    coach: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    socio = await make_member(session, sex="f")  # la fábrica no fija `sex` por defecto
    antes = await fila_socio(session, socio.id)
    recibidos = capturar_eventos(service.MemberUpdated)
    with contador_de_consultas.midiendo():
        salida = await editar(
            session,
            coach,
            socio.id,
            first_name="Lucía",
            last_name="Gómez",
            phone="300 765 4321",  # el mismo número con otro formato
            email="LUCIA.GOMEZ@correo.co",
            sex="f",
            birth_date="1991-07-23",
        )
        updates = _updates_de_members(contador_de_consultas)
    assert updates == []
    assert recibidos == []
    assert await auditoria_del_socio(session, socio.id, "update") == []
    assert await fila_socio(session, socio.id) == antes
    assert salida.phone == MASCARAS_KNOWN["phone"]


async def test_member_updated_lleva_los_nombres_cambiados_sin_valores(
    session: AsyncSession,
    coach: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    socio = await make_member(session)
    recibidos = capturar_eventos(service.MemberUpdated)
    await editar(session, coach, socio.id, phone=TELEFONO_NUEVO, first_name="Lucy")
    assert recibidos == [
        service.MemberUpdated(
            member_id=socio.id, changed_fields=("first_name", "phone"), occurred_at=T0
        )
    ]
    texto = repr(recibidos[0])
    for valor in ("Lucy", TELEFONO_NUEVO, TELEFONO_NUEVO_NORMALIZADO):
        assert valor not in texto, valor


# Autorización de datos (M-3, S3-D46) ---------------------------------------------------------


async def test_data_consent_true_sobre_una_nula_fija_la_fecha_del_reloj(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session, data_consent_at=None)
    salida = await editar(session, coach, socio.id, data_consent=True)
    fila = await fila_socio(session, socio.id)
    assert fila["data_consent_at"] == reloj.now_utc()
    assert salida.data_consent_at == reloj.now_utc()
    assert salida.warnings == []
    (update,) = await auditoria_del_socio(session, socio.id, "update")
    assert set(update["after"]) == {"data_consent_at"}


async def test_data_consent_true_sobre_una_existente_no_la_reescribe(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    original = T0 - timedelta(days=90)
    socio = await make_member(session, data_consent_at=original)
    await editar(session, coach, socio.id, data_consent=True)
    assert (await fila_socio(session, socio.id))["data_consent_at"] == original
    assert await auditoria_del_socio(session, socio.id, "update") == []


async def test_data_consent_false_da_422_y_no_cambia_nada(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session, data_consent_at=T0 - timedelta(days=5))
    antes = await fila_socio(session, socio.id)
    error = await editar_y_fallar(
        session, coach, socio.id, ConsentCannotBeWithdrawn, data_consent=False, first_name="Otra"
    )
    assert (error.status, error.code, error.field) == (
        422,
        "consent_cannot_be_withdrawn",
        "data_consent",
    )
    assert await fila_socio(session, socio.id) == antes


async def test_warnings_avisa_mientras_no_haya_autorizacion(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    sin = await make_member(session, data_consent_at=None)
    con = await make_member(
        session, document=unique_document(), phone=None, email=None, data_consent_at=T0
    )
    assert (await editar(session, coach, sin.id, first_name="Ana")).warnings == [
        "data_consent_missing"
    ]
    assert (await editar(session, coach, con.id, first_name="Ana")).warnings == []


# Reglas del alta y respuesta -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "campo"),
    [
        ({"birth_date": "2026-10-22"}, "birth_date"),
        ({"birth_date": "1899-12-31"}, "birth_date"),
        ({"phone": "+57"}, "phone"),
        ({"phone": "..."}, "phone"),
        ({"document": "..."}, "document"),
    ],
    ids=["fecha-futura", "fecha-antigua", "telefono-solo-prefijo", "telefono-puntos", "documento"],
)
async def test_las_reglas_del_alta_valen_en_la_edicion(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    campos: dict[str, Any],
    campo: str,
) -> None:
    socio = await make_member(session)
    antes = await fila_socio(session, socio.id)
    error = await editar_y_fallar(session, admin, socio.id, MemberValidationError, **campos)
    assert (error.status, error.code, error.field) == (422, "validation_error", campo)
    assert await fila_socio(session, socio.id) == antes


async def test_la_respuesta_es_la_ficha_enmascarada_con_su_membresia(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    mensual = await make_plan(session, name="Mensual")
    socio = await make_member(session, data_consent_at=T0)
    await make_membership(
        session, socio, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    salida = await editar(session, coach, socio.id, last_name="Gómez Ruiz")
    assert isinstance(salida, MemberDetailOut)
    assert set(salida.model_dump()) == CAMPOS_DETALLE
    assert salida.last_name == "Gómez Ruiz"
    for campo, mascara in MASCARAS_KNOWN.items():
        assert getattr(salida, campo) == mascara, campo
    assert (salida.membership_status, salida.plan_name) == ("active", "Mensual")
    volcado = salida.model_dump_json()
    for valor in (*KNOWN_NORMALIZED, "apx1."):
        assert valor not in volcado, valor


# Candado del socio (S3-D54, L-1) -------------------------------------------------------------


async def test_update_espera_el_candado_del_socio(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    """Otra transacción tiene `lock_member`: `update` espera y, con `lock_timeout` de 300 ms,
    termina en `DatabaseBusy` sin escribir."""
    primera, segunda = dos_sesiones
    socio = await make_member(primera, document=unique_document(), phone=None, email=None)
    socio_id = socio.id  # el rollback de `primera` expira el objeto
    await lock_member(primera, socio_id)
    actor = UUID("0000000a-0000-4000-8000-00000000b10e")
    try:
        with actor_scope(actor), pytest.raises(DatabaseBusy):
            await segunda.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await service.update(segunda, socio_id, MemberPatch(first_name="Otra"), role="admin")
        await segunda.rollback()
    finally:
        await primera.rollback()
    nombre = await primera.scalar(
        text("SELECT first_name FROM members.members WHERE id = :id"), {"id": socio_id}
    )
    assert nombre == "Lucía"
    await primera.commit()
