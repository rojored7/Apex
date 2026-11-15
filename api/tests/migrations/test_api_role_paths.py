"""Los caminos de escritura del api corren como `apex_api` sobre `apex_roles` (S5-W0-3; S5-D202).

Con el `INSERT` de `payments.payments` por columna (sin `void_reason`, `voided_by` ni
`voided_at`), el ORM no puede nombrar esas columnas al registrar un pago. Estas pruebas ejecutan
`payments.service.register` y `payments.service.void` (las funciones reales de `POST /payments`
y de la anulación) con una sesión conectada como `apex_api`.
Las filas se siembran como propietario; `apex_roles` se descarta al terminar la sesión.
"""

# ruff: noqa: S608
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import TypeVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus, inventory, rotate_job
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.provider import configure_provider
from app.modules.memberships import service as _memberships_service  # registra el gate  # noqa: F401
from app.modules.payments import service as payments_service
from tests.conftest import LIMPIAR_LLAVES
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.migrations._apoyo_notificaciones import consultar
from tests.migrations.conftest import RolesDb, url_por_rol
from tests.migrations.test_db_grants import propietario

T = TypeVar("T")
SYSTEM = str(SYSTEM_USER_ID)
USUARIO_ROTADOR = UUID("00000000-0000-0000-0000-0000000000f1")
LIMPIAR_JOBS_Y_LLAVES = (
    disable_user_sql("crypto.crypto_jobs"),
    "DELETE FROM crypto.crypto_jobs",
    rearm_always_sql("crypto.crypto_jobs"),
    *LIMPIAR_LLAVES,
)


def _blob(socio: UUID) -> str:
    return bus.encrypt("member.document", b"123456", bus.aad_for(socio), record_id=socio)


def _como_api[T](apex: RolesDb, trabajo: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def correr() -> T:
        motor: AsyncEngine = create_async_engine(url_por_rol(apex, "apex_api"))
        try:
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            with actor_scope(SYSTEM_USER_ID):
                async with fabrica() as sesion:
                    resultado = await trabajo(sesion)
                    await sesion.commit()
                    return resultado
        finally:
            await motor.dispose()

    return asyncio.run(correr())


@pytest.fixture
def membresia_activa(apex_roles: RolesDb) -> UUID:
    """Un socio, un plan y una membresía `active` de 100000 COP sembrados como propietario."""
    socio, plan, membresia = str(uuid4()), str(uuid4()), str(uuid4())
    hoy = date.today()
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "
        "document_idx, phone, phone_idx, email, email_idx) "
        f"VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Api', "
        f"'apx1.doc', 'idx-{socio}', 'apx1.fono', 'pidx-{socio}', 'apx1.correo', 'eidx-{socio}')",
        "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days) "
        f"VALUES ('{plan}', '{SYSTEM}', 'Plan {plan}', 100000, 'days', 30)",
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "
        "agreed_price_cop, start_date, end_date, status) "
        f"VALUES ('{membresia}', '{SYSTEM}', '{socio}', '{plan}', 100000, "
        f"'{hoy}', '{hoy + timedelta(days=30)}', 'active')",
    )
    return UUID(membresia)


def test_registrar_un_pago_como_apex_api_usa_el_insert_por_columna(
    apex_roles: RolesDb, membresia_activa: UUID
) -> None:
    async def trabajo(sesion: AsyncSession) -> UUID:
        pago = await payments_service.register(
            sesion,
            membership_id=membresia_activa,
            amount_cop=40000,
            method="cash",
            role="admin",
        )
        return pago.id

    pago_id = _como_api(apex_roles, trabajo)

    async def leer(sesion: AsyncSession) -> tuple[bool, object, object, object]:
        fila = (
            await sesion.execute(
                text(
                    "SELECT voided, void_reason, voided_by, voided_at "
                    "FROM payments.payments WHERE id = :i"
                ),
                {"i": pago_id},
            )
        ).one()
        return fila.voided, fila.void_reason, fila.voided_by, fila.voided_at

    assert _como_api(apex_roles, leer) == (False, None, None, None)


def test_anular_un_pago_como_apex_api_usa_el_update_por_columna(
    apex_roles: RolesDb, membresia_activa: UUID
) -> None:
    async def registrar(sesion: AsyncSession) -> UUID:
        pago = await payments_service.register(
            sesion,
            membership_id=membresia_activa,
            amount_cop=30000,
            method="cash",
            role="admin",
        )
        return pago.id

    pago_id = _como_api(apex_roles, registrar)

    async def anular(sesion: AsyncSession) -> bool:
        anulado = await payments_service.void(
            sesion, payment_id=pago_id, reason="error de digitación"
        )
        return anulado.voided

    assert _como_api(apex_roles, anular) is True


# S6-R1 (S6-D43, S6-D61, H-2, E6): la rotacion desde la pantalla corre como `apex_api` ---


def test_start_from_screen_y_run_rotation_como_apex_api_pasan_las_guardas_de_0024(
    apex_roles: RolesDb, proveedor_local: LocalFileProvider
) -> None:
    """`start_from_screen` (job `running`, anterior a `decrypt_only`, nueva `active`) y
    `run_rotation` (progreso del job, recifrado de `members.members.document`) con las sesiones de
    `apex_api`: sin los grants por columna y las guardas de `0024` esto falla en la base real."""
    miembro = uuid4()

    async def con_api(trabajo: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
        motor = create_async_engine(url_por_rol(apex_roles, "apex_api"))
        try:
            with actor_scope(SYSTEM_USER_ID):
                return await trabajo(async_sessionmaker(motor, expire_on_commit=False))
        finally:
            await motor.dispose()

    async def crear_llaves(fabrica: async_sessionmaker[AsyncSession]) -> None:
        async with fabrica() as sesion, sesion.begin():
            await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)

    async def rotar(fabrica: async_sessionmaker[AsyncSession]) -> tuple[str, int, list[str]]:
        async with fabrica() as sesion, sesion.begin():
            activa = await sesion.scalar(
                select(CryptoKey.id).where(
                    CryptoKey.data_class == "member.document",
                    CryptoKey.purpose == "encrypt",
                    CryptoKey.state == "active",
                )
            )
            assert activa is not None
            inicio = await inventory.start_from_screen(
                sesion, activa, reason="prueba de roles", by=USUARIO_ROTADOR
            )
        await rotate_job.run_rotation(fabrica, inicio.job_id)
        async with fabrica() as sesion:
            job = await sesion.get(CryptoJob, inicio.job_id)
            assert job is not None
            estados = (
                await sesion.scalars(
                    select(CryptoKey.state)
                    .where(CryptoKey.data_class == "member.document")
                    .where(CryptoKey.purpose == "encrypt")
                    .order_by(CryptoKey.version)
                )
            ).all()
            return job.status, job.done, list(estados)

    configure_provider(proveedor_local)
    try:
        asyncio.run(con_api(crear_llaves))
        # Los socios de las otras pruebas del módulo traen un `document` de relleno (`apx1.doc`):
        # no descifra y la rotación recifra TODA la clase. Se les pone un blob válido (S6-R1).
        otros = consultar(apex_roles.dsn(), "SELECT id FROM members.members")
        propietario(
            apex_roles,
            *(
                f"UPDATE members.members SET document = '{_blob(fila['id'])}' "
                f"WHERE id = '{fila['id']}'"
                for fila in otros
            ),
        )
        blob = _blob(miembro)
        propietario(
            apex_roles,
            "INSERT INTO members.members (id, created_by, first_name, last_name, "
            f"document, document_idx) VALUES ('{miembro}', '{SYSTEM}', 'Ana', 'Rol', "
            f"'{blob}', 'idx-{miembro}')",
            "INSERT INTO auth.users (id, created_by, email, role) VALUES "
            f"('{USUARIO_ROTADOR}', '{SYSTEM}', 'rol-{miembro}@test.apex', 'admin')",
        )
        estado, hechas, llaves = asyncio.run(con_api(rotar))
    finally:
        configure_provider(None)
        configure_keyring(None)
        propietario(
            apex_roles,
            f"DELETE FROM members.members WHERE id = '{miembro}'",
            f"DELETE FROM auth.users WHERE id = '{USUARIO_ROTADOR}'",
            *LIMPIAR_JOBS_Y_LLAVES,
        )
    assert (estado, hechas) == ("done", 1 + len(otros))
    assert llaves == ["decrypt_only", "active"]


def test_crear_y_editar_una_franja_como_apex_api_usa_el_update_por_columna(
    apex_roles: RolesDb,
) -> None:
    """S7-A2 (S7-D18): `classes.service.create_slot` y `update_slot` con los privilegios reales de
    `apex_api` (INSERT y UPDATE por columna sobre `classes.class_slots`, sin DELETE). Desde B1 el
    alta de una franja activa también inserta sus sesiones (INSERT en `class_sessions`)."""
    from app.modules.classes import service as classes_service
    from app.modules.classes.schemas import SlotCreate, SlotPatch
    from tests.conftest import LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS

    async def crear(sesion: AsyncSession) -> UUID:
        data = SlotCreate.model_validate(
            {"weekdays": [1, 3], "start_time": "18:30", "duration_min": 60, "capacity": 12}
        )
        franja = await classes_service.create_slot(sesion, data, SYSTEM_USER_ID)
        return franja.id

    slot_id = _como_api(apex_roles, crear)

    async def editar(sesion: AsyncSession) -> tuple[int, bool]:
        parche = SlotPatch.model_validate({"capacity": 9, "is_active": False})
        franja = await classes_service.update_slot(sesion, slot_id, parche, SYSTEM_USER_ID)
        return franja.capacity, franja.is_active

    try:
        assert _como_api(apex_roles, editar) == (9, False)
    finally:
        propietario(apex_roles, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS)


def test_check_in_como_apex_api_inserta_asistencia_y_lee_lo_que_necesita(
    apex_roles: RolesDb,
) -> None:
    """S7-C1 (S7-D13, P-ROL): `classes.service.check_in` con los privilegios reales de `apex_api`:
    `SELECT` de socios y ajustes, `SELECT ... FOR UPDATE` de la sesión (exige `UPDATE` de columna),
    `INSERT` en `classes.attendance` y en `audit.audit_log`. El puerto de membresías es un doble."""
    from app.modules.classes import service as classes_service
    from app.modules.classes.schemas import AttendanceCreate
    from tests.conftest import LIMPIAR_ATTENDANCE, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS
    from tests.factories.classes import FakeMembershipPort

    socio, sesion_id = uuid4(), uuid4()
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "
        f"document_idx) VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Check', 'apx1.doc', 'idx-{socio}')",
        "INSERT INTO classes.class_sessions (id, created_by, session_date, starts_at, "
        f"duration_min, capacity) VALUES ('{sesion_id}', '{SYSTEM}', "
        "(now() AT TIME ZONE 'America/Bogota')::date, now(), 60, 15)",
    )
    anterior = classes_service.membership_port()
    classes_service.set_membership_port(FakeMembershipPort("expired"))

    async def registrar(sesion: AsyncSession) -> tuple[list[str], int]:
        datos = AttendanceCreate.model_validate({"session_id": sesion_id, "member_id": socio})
        with actor_scope(SYSTEM_USER_ID):
            salida = await classes_service.check_in(sesion, datos, by=SYSTEM_USER_ID)
        return salida.flags, salida.attendance_count

    try:
        assert _como_api(apex_roles, registrar) == (["expired"], 1)
        filas = consultar(
            apex_roles.dsn(),
            "SELECT count(*) AS n FROM classes.attendance WHERE session_id = $1",
            sesion_id,
        )
        assert filas[0]["n"] == 1
    finally:
        classes_service.set_membership_port(anterior)
        propietario(apex_roles, LIMPIAR_ATTENDANCE, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS)


def test_apex_api_escribe_original_end_date(apex_roles: RolesDb) -> None:
    """S7-C2 (`0029`): la última clase de una tiquetera recorta el fin y guarda `original_end_date`
    con el `UPDATE` por columna de `apex_api`; el puerto REAL de memberships lee la membresía."""
    from app.modules.classes import service as classes_service
    from app.modules.classes.schemas import AttendanceCreate
    from tests.conftest import LIMPIAR_ATTENDANCE, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS

    # Ids únicos por corrida: la base `apex_roles` es de toda la sesión y otras pruebas del módulo
    # (`filas_base`) siembran sus propias filas; esta prueba limpia SOLO las suyas, por id (L7).
    socio, plan, membresia, sesion_id = uuid4(), uuid4(), uuid4(), uuid4()
    hoy = consultar(apex_roles.dsn(), "SELECT (now() AT TIME ZONE 'America/Bogota')::date AS hoy")[
        0
    ]["hoy"]
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "
        f"document_idx) VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Tiquetera', 'apx1.doc', "
        f"'idx-{socio}')",
        "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days, "
        f"class_count) VALUES ('{plan}', '{SYSTEM}', 'Plan {plan}', 100000, 'classes', 60, 4)",
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "
        "agreed_price_cop, start_date, end_date, classes_total, classes_remaining, status) "
        f"VALUES ('{membresia}', '{SYSTEM}', '{socio}', '{plan}', 100000, "
        f"'{hoy - timedelta(days=5)}', '{hoy + timedelta(days=50)}', 4, 1, 'active')",
        "INSERT INTO classes.class_sessions (id, created_by, session_date, starts_at, "
        f"duration_min, capacity) VALUES ('{sesion_id}', '{SYSTEM}', "
        "(now() AT TIME ZONE 'America/Bogota')::date, now(), 60, 15)",
    )

    async def registrar(sesion: AsyncSession) -> list[str]:
        datos = AttendanceCreate.model_validate({"session_id": sesion_id, "member_id": socio})
        with actor_scope(SYSTEM_USER_ID):
            salida = await classes_service.check_in(sesion, datos, by=SYSTEM_USER_ID)
        return salida.flags

    try:
        assert _como_api(apex_roles, registrar) == []
        fila = consultar(
            apex_roles.dsn(),
            "SELECT classes_remaining, status, end_date, original_end_date "
            "FROM memberships.memberships WHERE id = $1",
            membresia,
        )[0]
        assert fila["classes_remaining"] == 0 and fila["status"] == "expired"
        assert fila["original_end_date"] == hoy + timedelta(days=50)
        # recortado al día del consumo, en la fecha de Bogotá que calcula la base (L7)
        assert fila["end_date"] == hoy
    finally:
        propietario(
            apex_roles,
            LIMPIAR_ATTENDANCE,
            LIMPIAR_CLASS_SESSIONS,
            LIMPIAR_CLASS_SLOTS,
            # por id: la guarda rechaza el DELETE; se apaga y se rearma `ALWAYS` (S3-D49)
            "ALTER TABLE memberships.memberships DISABLE TRIGGER USER",
            f"DELETE FROM memberships.memberships WHERE id = '{membresia}'",
            "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_guard_identity",
            "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_delete",
            "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_truncate",
            f"DELETE FROM plans.plans WHERE id = '{plan}'",
            f"DELETE FROM members.members WHERE id = '{socio}'",
        )
    residuos = consultar(
        apex_roles.dsn(),
        "SELECT (SELECT count(*) FROM memberships.memberships WHERE id = $1) "
        "+ (SELECT count(*) FROM members.members WHERE id = $2) "
        "+ (SELECT count(*) FROM plans.plans WHERE id = $3) AS n",
        membresia,
        socio,
        plan,
    )
    assert residuos[0]["n"] == 0  # la prueba no deja socio, plan ni membresía (L7)


def test_apex_api_escribe_wod_id(apex_roles: RolesDb) -> None:
    """S8-A4 (S8-D3, C2): `classes.service.assign_wod` con los privilegios reales de `apex_api`:
    `SELECT ... FOR UPDATE` de la sesión, `SELECT` de `wods.wods` y `UPDATE (wod_id)` por columna.
    Sin FK entre esquemas: el WOD se valida en el service."""
    from app.modules.classes import service as classes_service
    from app.modules.classes.schemas import SessionPatch
    from tests.conftest import LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS, LIMPIAR_WODS

    sesion_id, wod_id = uuid4(), uuid4()
    propietario(
        apex_roles,
        "INSERT INTO wods.wods (id, created_by, date, title, score_type) "
        f"VALUES ('{wod_id}', '{SYSTEM}', '2031-01-05', 'Fran', 'none')",
        "INSERT INTO classes.class_sessions (id, created_by, session_date, starts_at, "
        f"duration_min, capacity) VALUES ('{sesion_id}', '{SYSTEM}', "
        "(now() AT TIME ZONE 'America/Bogota')::date, now(), 60, 15)",
    )

    async def asignar(sesion: AsyncSession) -> UUID | None:
        datos = SessionPatch.model_validate({"wod_id": wod_id})
        with actor_scope(SYSTEM_USER_ID):
            salida = await classes_service.assign_wod(sesion, sesion_id, datos, by=SYSTEM_USER_ID)
        return salida.wod_id

    try:
        assert _como_api(apex_roles, asignar) == wod_id
        fila = consultar(
            apex_roles.dsn(), "SELECT wod_id FROM classes.class_sessions WHERE id = $1", sesion_id
        )
        assert fila[0]["wod_id"] == wod_id
    finally:
        propietario(
            apex_roles,
            LIMPIAR_CLASS_SESSIONS,
            LIMPIAR_CLASS_SLOTS,
            LIMPIAR_WODS,
        )


def test_apex_api_inserta_y_apaga_sin_delete(apex_roles: RolesDb) -> None:
    """S8-B1 (S8-D35, P-ROL): `results.service.record_result` con los privilegios reales de
    `apex_api`: `SELECT` del WOD y del socio, `INSERT` del resultado y `UPDATE (is_current)` al
    corregir; `DELETE` y `UPDATE` de otras columnas siguen negados."""
    from sqlalchemy.exc import DBAPIError

    from app.modules.results import service as results_service
    from app.modules.results.schemas import ResultIn
    from tests.conftest import LIMPIAR_WOD_RESULTS, LIMPIAR_WODS

    socio, wod_id = uuid4(), uuid4()
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "
        "document_idx, phone, phone_idx, email, email_idx) "
        f"VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Api', "
        f"'apx1.doc', 'idx-{socio}', 'apx1.fono', 'pidx-{socio}', 'apx1.correo', 'eidx-{socio}')",
        "INSERT INTO wods.wods (id, created_by, date, title, score_type) "
        f"VALUES ('{wod_id}', '{SYSTEM}', '2026-01-05', 'Fran', 'time')",
    )

    async def registrar_y_corregir(sesion: AsyncSession) -> tuple[UUID, UUID]:
        primero = await results_service.record_result(
            sesion,
            ResultIn.model_validate(
                {"wod_id": wod_id, "member_id": socio, "level": "rx", "seconds": 300}
            ),
            by=SYSTEM_USER_ID,
        )
        segundo = await results_service.record_result(
            sesion,
            ResultIn.model_validate(
                {
                    "wod_id": wod_id,
                    "member_id": socio,
                    "level": "rx",
                    "seconds": 280,
                    "supersedes_id": primero.id,
                }
            ),
            by=SYSTEM_USER_ID,
        )
        return primero.id, segundo.id

    async def intentar_borrar(sesion: AsyncSession) -> str:
        try:
            await sesion.execute(text("DELETE FROM results.wod_results"))
        except DBAPIError as error:
            return str(getattr(error.orig, "sqlstate", ""))
        return ""

    from app.core.crypto import oplog

    oplog.reset_buffer()  # filas de `crypto_ops` que una prueba anterior dejó pendientes
    try:
        primero, segundo = _como_api(apex_roles, registrar_y_corregir)
        filas = consultar(
            apex_roles.dsn(),
            "SELECT id, is_current, source, status FROM results.wod_results ORDER BY created_at",
        )
        assert [(r["id"], r["is_current"], r["source"], r["status"]) for r in filas] == [
            (primero, False, "desk", "validated"),
            (segundo, True, "desk", "validated"),
        ]
        assert _como_api(apex_roles, intentar_borrar) == "42501"
    finally:
        propietario(apex_roles, LIMPIAR_WOD_RESULTS, LIMPIAR_WODS)
