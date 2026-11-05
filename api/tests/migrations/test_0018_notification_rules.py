"""`0018_notification_rules` (S5-B6, US-121; S5-D24). # Rojo B6

Padre `0017_notification_templates`; es head. Tabla `notifications.notification_rules`:
- comunes más `name`, `trigger`, `channel` (`text`), `offset_days` (`integer`), `template_id`
  (`uuid`, FK a plantillas `ON DELETE RESTRICT`) e `is_active` (`boolean`), todas obligatorias;
- CHECK de `trigger`, de `channel`, de nombre no vacío y del signo del desfase (por venir `<= 0`,
  vencida `>= 1`);
- único parcial `uq_notification_rules_active_key (trigger, offset_days, channel) WHERE
  is_active`;
- sin triggers. El `downgrade` borra la tabla y deja las plantillas.
"""

from __future__ import annotations

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
    columnas,
    consultar,
    existe,
    insert,
    plantilla,
    regla,
    resultados,
)

REVISION = "0018_notification_rules"
PADRE = "0017_notification_templates"
TABLA = "notifications.notification_rules"
PLANTILLAS = "notifications.notification_templates"
UNICO_ACTIVO = "uq_notification_rules_active_key"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "name": ("text", "NO"),
    "trigger": ("text", "NO"),
    "offset_days": ("integer", "NO"),
    "channel": ("text", "NO"),
    "template_id": ("uuid", "NO"),
    "is_active": ("boolean", "NO"),
}


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _con_plantilla(*reglas: dict[str, object]) -> list[Paso]:
    base = plantilla()
    pasos = [insert("notification_templates", base)]
    pasos += [insert("notification_rules", {**r, "template_id": base["id"]}) for r in reglas]
    return pasos


def test_la_revision_cuelga_de_0017_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert columnas(migrated_database, TABLA) == COLUMNAS


def test_la_fk_apunta_a_plantillas_con_on_delete_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT confrelid::regclass::text AS destino, confdeltype::text AS borrado, "
        "pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert [f["destino"] for f in filas] == [PLANTILLAS]
    assert filas[0]["borrado"] == "r"
    assert "(template_id)" in filas[0]["def"] and "(id)" in filas[0]["def"]


def test_los_check_existen_con_su_nombre(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass($1) AND contype = 'c'",
        TABLA,
    )
    assert {f["conname"] for f in filas} == {
        "ck_notification_rules_name_not_blank",
        "ck_notification_rules_trigger",
        "ck_notification_rules_channel",
        "ck_notification_rules_offset_days_sign",
    }


def test_el_indice_unico_es_parcial_sobre_las_activas(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = consultar(
        migrated_database,
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'notifications' "
        "AND tablename = 'notification_rules' AND indexname = $1",
        UNICO_ACTIVO,
    )
    assert len(filas) == 1
    definicion = filas[0]["indexdef"]
    assert "UNIQUE" in definicion
    assert "(trigger, offset_days, channel)" in definicion
    assert "WHERE is_active" in definicion


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


@pytest.mark.parametrize(
    ("disparador", "desfase", "canal"),
    [
        ("membership_expiring", -3, "whatsapp_link"),
        ("membership_expiring", 0, "email"),
        ("membership_expired", 1, "whatsapp_link"),
        ("membership_expired", 15, "email"),
    ],
)
def test_las_combinaciones_validas_entran(
    alembic_config: Config,
    migrated_database: str,
    disparador: str,
    desfase: int,
    canal: str,
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, trigger=disparador, offset_days=desfase, channel=canal))
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize(
    ("disparador", "desfase"),
    [
        ("membership_expiring", 1),
        ("membership_expiring", 15),
        ("membership_expired", 0),
        ("membership_expired", -1),
        ("membership_expired", -3),
    ],
)
def test_un_desfase_con_el_signo_equivocado_viola_el_check(
    alembic_config: Config, migrated_database: str, disparador: str, desfase: int
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, trigger=disparador, offset_days=desfase))
    assert resultados(migrated_database, [pasos]) == [
        (CHECK_VIOLATION, "ck_notification_rules_offset_days_sign")
    ]


@pytest.mark.parametrize("disparador", ["membership_started", "EXPIRING", ""])
def test_un_disparador_fuera_de_la_lista_viola_el_check(
    alembic_config: Config, migrated_database: str, disparador: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, trigger=disparador))
    [(sqlstate, constraint)] = resultados(migrated_database, [pasos])
    # un disparador desconocido incumple también el CHECK del signo: Postgres informa uno de los dos
    assert sqlstate == CHECK_VIOLATION
    assert constraint in {"ck_notification_rules_trigger", "ck_notification_rules_offset_days_sign"}


@pytest.mark.parametrize("canal", ["sms", "telegram", "push", "EMAIL", ""])
def test_un_canal_fuera_de_la_lista_viola_el_check(
    alembic_config: Config, migrated_database: str, canal: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, channel=canal))
    assert resultados(migrated_database, [pasos]) == [
        (CHECK_VIOLATION, "ck_notification_rules_channel")
    ]


def test_un_nombre_en_blanco_viola_el_check(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, name="   "))
    assert resultados(migrated_database, [pasos]) == [
        (CHECK_VIOLATION, "ck_notification_rules_name_not_blank")
    ]


def test_dos_activas_con_la_misma_clave_violan_el_unico_parcial(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, name="A"), regla(None, name="B"))
    assert resultados(migrated_database, [pasos]) == [(UNIQUE_VIOLATION, UNICO_ACTIVO)]


def test_una_inactiva_no_choca_con_una_activa_ni_con_otra_inactiva(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(
        regla(None, name="A"),
        regla(None, name="B", is_active=False),
        regla(None, name="C", is_active=False),
    )
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize(
    "cambio",
    [{"offset_days": 0}, {"channel": "email"}, {"trigger": "membership_expired", "offset_days": 1}],
)
def test_cambiar_cualquier_parte_de_la_clave_evita_el_choque(
    alembic_config: Config, migrated_database: str, cambio: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, name="A"), regla(None, name="B", **cambio))
    assert resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize("columna", ["name", "trigger", "offset_days", "channel", "is_active"])
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None, **{columna: None}))
    assert resultados(migrated_database, [pasos])[0][0] == NOT_NULL_VIOLATION


def test_una_plantilla_inexistente_viola_la_fk(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = [insert("notification_rules", regla(uuid4()))]
    assert resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


def test_borrar_una_plantilla_con_reglas_se_rechaza_por_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_plantilla(regla(None))
    pasos.append(
        ("DELETE FROM notifications.notification_templates WHERE id = $1", [pasos[0][1][0]])
    )
    assert resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


def test_ciclo_head_base_head_de_0018(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    assert existe(migrated_database, TABLA) is True
    command.downgrade(alembic_config, PADRE)
    try:
        assert existe(migrated_database, TABLA) is False
        assert existe(migrated_database, PLANTILLAS) is True, "el downgrade deja las plantillas"
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(migrated_database, TABLA) is True
    assert columnas(migrated_database, TABLA) == COLUMNAS
