"""`0019_notifications` (S5-B7, US-124; S5-D24, RN-17, N-37). # Rojo B7

Padre `0018_notification_rules`; en la cadena (`0020` cuelga de ella). Tabla
`notifications.notifications`:
- comunes más `rule_id` (`uuid`, FK a reglas `ON DELETE RESTRICT`), `member_id` y `membership_id`
  (`uuid`, sin FK), `target_date` (`date`), `channel`, `status`, `rendered_subject`,
  `rendered_body` (`text`) y `attempts` (`integer`), todas obligatorias; `last_error`, `sent_at`,
  `sent_by` y `skip_reason` opcionales;
- CHECK de canal, estado, intentos (`>= 0`), motivo de omisión y código de error cerrado;
- único `(rule_id, membership_id, target_date)` (RN-17) e índices `(status, target_date)` y
  `(member_id, target_date DESC)`;
- sin triggers. El `downgrade` borra la tabla y deja plantillas y reglas.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    NOT_NULL_VIOLATION,
    TIMESTAMPTZ,
    UNIQUE_VIOLATION,
    Paso,
    aviso,
    columnas,
    consultar,
    existe,
    insert,
    plantilla,
    regla,
    resultados,
)

REVISION = "0019_notifications"
PADRE = "0018_notification_rules"
TABLA = "notifications.notifications"
REGLAS = "notifications.notification_rules"
UNICO = "uq_notifications_rule_membership_target"
IDX_ESTADO = "ix_notifications_status_target_date"
IDX_SOCIO = "ix_notifications_member_target_date"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "rule_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "membership_id": ("uuid", "NO"),
    "target_date": ("date", "NO"),
    "channel": ("text", "NO"),
    "status": ("text", "NO"),
    "rendered_subject": ("text", "NO"),
    "rendered_body": ("text", "NO"),
    "attempts": ("integer", "NO"),
    "last_error": ("text", "YES"),
    "sent_at": (TIMESTAMPTZ, "YES"),
    "sent_by": ("uuid", "YES"),
    "skip_reason": ("text", "YES"),
}


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _con_regla(*avisos: dict[str, object]) -> list[Paso]:
    """Plantilla, regla y los avisos dados (todos con el `rule_id` de esa regla)."""
    plant = plantilla()
    base = regla(plant["id"])
    pasos = [insert("notification_templates", plant), insert("notification_rules", base)]
    pasos += [insert("notifications", {**a, "rule_id": base["id"]}) for a in avisos]
    return pasos


def test_la_revision_cuelga_de_0018_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert REVISION in {r.revision for r in scripts.walk_revisions("base", "heads")}


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert columnas(migrated_database, TABLA) == COLUMNAS


def test_attempts_vale_cero_por_defecto(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = 'notifications' AND table_name = 'notifications' "
        "AND column_name = 'attempts'",
    )
    assert filas[0]["column_default"] == "0"


def test_membership_id_es_obligatorio_y_solo_la_regla_tiene_fk(
    alembic_config: Config, migrated_database: str
) -> None:
    """N-37: `membership_id NOT NULL`; ni él ni `member_id` apuntan a otro esquema."""
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, membership_id=None))
    assert resultados(migrated_database, [pasos])[0][0] == NOT_NULL_VIOLATION
    filas = consultar(
        migrated_database,
        "SELECT confrelid::regclass::text AS destino FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert [f["destino"] for f in filas] == [REGLAS]


def test_la_fk_de_la_regla_es_on_delete_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT confdeltype::text AS borrado, pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert len(filas) == 1 and filas[0]["borrado"] == "r"
    assert "(rule_id)" in filas[0]["def"]


def test_los_check_existen_con_su_nombre(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass($1) AND contype = 'c'",
        TABLA,
    )
    assert {f["conname"] for f in filas} == {
        "ck_notifications_channel",
        "ck_notifications_status",
        "ck_notifications_attempts",
        "ck_notifications_skip_reason",
        "ck_notifications_last_error",
    }


def test_el_unico_cubre_regla_membresia_y_fecha(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND conname = $2 AND contype = 'u'",
        TABLA,
        UNICO,
    )
    assert len(filas) == 1
    assert "(rule_id, membership_id, target_date)" in filas[0]["def"]


def test_los_indices_de_hoy_y_del_socio_existen(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'notifications' "
        "AND tablename = 'notifications'",
    )
    por_nombre = {f["indexname"]: f["indexdef"] for f in filas}
    assert "(status, target_date)" in por_nombre.get(IDX_ESTADO, "")
    assert "(member_id, target_date DESC)" in por_nombre.get(IDX_SOCIO, "")


def test_la_tabla_no_tiene_triggers_de_usuario(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass($1) AND NOT tgisinternal",
        TABLA,
    )
    assert [f["tgname"] for f in filas] == []


@pytest.mark.parametrize("canal", ["email", "whatsapp_link"])
@pytest.mark.parametrize("estado", ["pending", "sent", "failed"])
def test_las_combinaciones_validas_entran(
    alembic_config: Config, migrated_database: str, canal: str, estado: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, channel=canal, status=estado))
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize("canal", ["sms", "telegram", "EMAIL", ""])
def test_un_canal_fuera_de_la_lista_viola_el_check(
    alembic_config: Config, migrated_database: str, canal: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, channel=canal))
    assert resultados(migrated_database, [pasos]) == [(CHECK_VIOLATION, "ck_notifications_channel")]


@pytest.mark.parametrize("estado", ["queued", "SENT", "done", ""])
def test_un_estado_fuera_de_la_lista_viola_el_check(
    alembic_config: Config, migrated_database: str, estado: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, status=estado))
    assert resultados(migrated_database, [pasos]) == [(CHECK_VIOLATION, "ck_notifications_status")]


def test_attempts_negativo_viola_el_check_y_cero_o_mas_entra(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    malo = _con_regla(aviso(None, attempts=-1))
    bueno_cero = _con_regla(aviso(None, attempts=0))
    bueno_tres = _con_regla(aviso(None, attempts=3))
    assert resultados(migrated_database, [malo, bueno_cero, bueno_tres]) == [
        (CHECK_VIOLATION, "ck_notifications_attempts"),
        ("", None),
        ("", None),
    ]


def test_omitido_exige_motivo(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    sin_motivo = _con_regla(aviso(None, status="skipped"))
    con_motivo = _con_regla(aviso(None, status="skipped", skip_reason="El socio ya renovó"))
    pendiente_con_motivo = _con_regla(aviso(None, status="pending", skip_reason="x"))
    assert resultados(migrated_database, [sin_motivo, con_motivo, pendiente_con_motivo]) == [
        (CHECK_VIOLATION, "ck_notifications_skip_reason"),
        ("", None),
        ("", None),
    ]


@pytest.mark.parametrize("codigo", ["timeout", "auth", "refused", "invalid_recipient", "unknown"])
def test_los_codigos_de_error_cerrados_entran(
    alembic_config: Config, migrated_database: str, codigo: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, status="failed", last_error=codigo))
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize("texto", ["connection refused by smtp.example.com", "", "TIMEOUT"])
def test_un_texto_libre_en_last_error_viola_el_check(
    alembic_config: Config, migrated_database: str, texto: str
) -> None:
    """S5-D24: `last_error` guarda un código del conjunto cerrado, nunca texto del servidor."""
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, status="failed", last_error=texto))
    assert resultados(migrated_database, [pasos]) == [
        (CHECK_VIOLATION, "ck_notifications_last_error")
    ]


def test_la_misma_regla_membresia_y_fecha_viola_el_unico(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    membresia = uuid4()
    pasos = _con_regla(aviso(None, membership_id=membresia), aviso(None, membership_id=membresia))
    assert resultados(migrated_database, [pasos]) == [(UNIQUE_VIOLATION, UNICO)]


@pytest.mark.parametrize("parte", ["membership_id", "target_date", "rule_id"])
def test_cambiar_cualquier_parte_de_la_clave_evita_el_choque(
    alembic_config: Config, migrated_database: str, parte: str
) -> None:
    _revision_existe(alembic_config)
    plant = plantilla()
    base = regla(plant["id"])
    otra = regla(plant["id"], name="Otra", offset_days=0)
    primero = aviso(base["id"])
    cambios: dict[str, object] = {
        "membership_id": uuid4(),
        "target_date": date(2026, 11, 6),
        "rule_id": otra["id"],
    }
    segundo = {**primero, "id": uuid4(), parte: cambios[parte]}
    pasos = [
        insert("notification_templates", plant),
        insert("notification_rules", base),
        insert("notification_rules", otra),
        insert("notifications", primero),
        insert("notifications", segundo),
    ]
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize(
    "columna",
    [
        "member_id",
        "target_date",
        "channel",
        "status",
        "rendered_subject",
        "rendered_body",
        "attempts",
    ],
)
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None, **{columna: None}))
    assert resultados(migrated_database, [pasos])[0][0] == NOT_NULL_VIOLATION


def test_una_regla_inexistente_viola_la_fk(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pasos = [insert("notifications", aviso(uuid4()))]
    assert resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


def test_borrar_una_regla_con_avisos_se_rechaza_por_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_regla(aviso(None))
    regla_id = pasos[1][1][0]
    pasos.append(("DELETE FROM notifications.notification_rules WHERE id = $1", [regla_id]))
    assert resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


def test_ciclo_head_base_head_de_0019(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    assert existe(migrated_database, TABLA) is True
    command.downgrade(alembic_config, PADRE)
    try:
        assert existe(migrated_database, TABLA) is False
        assert existe(migrated_database, REGLAS) is True, "el downgrade deja las reglas"
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(migrated_database, TABLA) is True
    assert columnas(migrated_database, TABLA) == COLUMNAS
