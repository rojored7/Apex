"""`0017_notification_templates` (S5-B6, US-120; S5-D24). # Rojo B6

Padre `0016_member_channel_preferences`; está en la cadena de head (`0018` cuelga de ella). Crea el
esquema `notifications` y la tabla `notifications.notification_templates`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`) más `name`, `subject` y `body`
  (`text`, obligatorias);
- CHECK `ck_notification_templates_name_not_blank`, `..._subject_not_blank` y `..._body_not_blank`;
- único `uq_notification_templates_name (name)`;
- sin triggers ni `deleted_at`.
El `downgrade` borra la tabla y el esquema.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    NOT_NULL_VIOLATION,
    TIMESTAMPTZ,
    UNIQUE_VIOLATION,
    columnas,
    consultar,
    existe,
    insert,
    plantilla,
    resultados,
)

REVISION = "0017_notification_templates"
PADRE = "0016_member_channel_preferences"
TABLA = "notifications.notification_templates"
UNICO = "uq_notification_templates_name"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "name": ("text", "NO"),
    "subject": ("text", "NO"),
    "body": ("text", "NO"),
}


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def test_la_revision_cuelga_de_0016_y_esta_en_la_cadena_de_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    cadena = {r.revision for r in scripts.walk_revisions("base", "heads")}
    assert REVISION in cadena
    assert len(scripts.get_heads()) == 1


def test_el_esquema_notifications_existe(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database, "SELECT 1 FROM pg_namespace WHERE nspname = 'notifications'"
    )
    assert len(filas) == 1


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert columnas(migrated_database, TABLA) == COLUMNAS


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


def test_el_unico_y_los_check_existen_con_su_nombre(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND contype IN ('c','u')",
        TABLA,
    )
    assert {f["conname"] for f in filas} == {
        UNICO,
        "ck_notification_templates_name_not_blank",
        "ck_notification_templates_subject_not_blank",
        "ck_notification_templates_body_not_blank",
    }


def test_una_plantilla_valida_entra(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pasos = [insert("notification_templates", plantilla())]
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize("columna", ["name", "subject", "body"])
@pytest.mark.parametrize("valor", ["", "   "])
def test_un_texto_en_blanco_viola_su_check(
    alembic_config: Config, migrated_database: str, columna: str, valor: str
) -> None:
    _revision_existe(alembic_config)
    pasos = [insert("notification_templates", plantilla(**{columna: valor}))]
    assert resultados(migrated_database, [pasos]) == [
        (CHECK_VIOLATION, f"ck_notification_templates_{columna}_not_blank")
    ]


@pytest.mark.parametrize("columna", ["name", "subject", "body", "created_by"])
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    pasos = [insert("notification_templates", plantilla(**{columna: None}))]
    assert resultados(migrated_database, [pasos])[0][0] == NOT_NULL_VIOLATION


def test_el_mismo_nombre_dos_veces_viola_el_unico(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = [
        insert("notification_templates", plantilla(name="Vence pronto")),
        insert("notification_templates", plantilla(name="Vence pronto")),
    ]
    assert resultados(migrated_database, [pasos]) == [(UNIQUE_VIOLATION, UNICO)]


def test_nombres_distintos_no_chocan(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pasos = [
        insert("notification_templates", plantilla(name="Vence pronto")),
        insert("notification_templates", plantilla(name="Venció")),
    ]
    assert resultados(migrated_database, [pasos]) == [("", None)]


def test_ciclo_head_base_head_de_0017(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    assert existe(migrated_database, TABLA) is True
    command.downgrade(alembic_config, PADRE)
    try:
        assert existe(migrated_database, TABLA) is False
        esquema = consultar(
            migrated_database, "SELECT 1 FROM pg_namespace WHERE nspname = 'notifications'"
        )
        assert esquema == [], "el downgrade borra también el esquema"
        socios = consultar(migrated_database, "SELECT to_regclass('members.members') AS t")
        assert socios[0]["t"] == "members.members"
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(migrated_database, TABLA) is True
    assert columnas(migrated_database, TABLA) == COLUMNAS
