"""Triggers inmutables que las limpiezas de prueba apagan y vuelven a encender (S4B-D6, E5).

Las limpiezas de `db_test` necesitan borrar filas de tablas protegidas: apagan los triggers con
`DISABLE TRIGGER USER`, borran y los vuelven a encender **por nombre** con
`ENABLE ALWAYS TRIGGER <nombre>`. Nunca `ENABLE TRIGGER USER`: dejaría `tgenabled = 'O'` y pisaría
el `'A'` de la migración (`session_replication_role = replica` los saltaría).

`rearm_always_sql` devuelve **una sola sentencia** (un bloque `DO`), porque el controlador asyncpg
no admite varias sentencias en un `execute` con `text()`.

Con `0014_audit_log_triggers_always` los diez quedan en `'A'`; antes de ella los ocho de
`audit_log` y `crypto.*` estaban en `'O'` y los dos de `verifications` en `'A'`. Apagar, borrar y
encender por nombre con `ALWAYS` es válido en los dos estados.
"""

from __future__ import annotations

from typing import Final

AUDIT_LOG_TABLE: Final = "audit.audit_log"
VERIFICATIONS_TABLE: Final = "audit.verifications"
SIGNATURES_TABLE: Final = "audit.signatures"
ATTACHMENTS_TABLE: Final = "attachments.attachments"
CLASS_SLOTS_TABLE: Final = "classes.class_slots"
CLASS_SESSIONS_TABLE: Final = "classes.class_sessions"
ATTENDANCE_TABLE: Final = "classes.attendance"
MOVEMENTS_TABLE: Final = "wods.movements"
BENCHMARKS_TABLE: Final = "wods.benchmarks"
WODS_TABLE: Final = "wods.wods"
WOD_RESULTS_TABLE: Final = "results.wod_results"
BODY_METRICS_TABLE: Final = "athletes.body_metrics"
PERSONAL_RECORDS_TABLE: Final = "athletes.personal_records"

AUDIT_LOG_TRIGGERS: Final = ("audit_log_forbid_mutation", "audit_log_forbid_truncate")
VERIFICATIONS_TRIGGERS: Final = ("verifications_forbid_mutation", "verifications_forbid_truncate")
SIGNATURES_TRIGGERS: Final = ("signatures_forbid_mutation", "signatures_forbid_truncate")
ATTACHMENTS_TRIGGERS: Final = (
    "attachments_guard_update",
    "attachments_forbid_delete",
    "attachments_forbid_truncate",
)
CLASS_SLOTS_TRIGGERS: Final = ("class_slots_forbid_delete", "class_slots_forbid_truncate")
CLASS_SESSIONS_TRIGGERS: Final = (
    "class_sessions_guard_update",
    "class_sessions_forbid_delete",
    "class_sessions_forbid_truncate",
)
ATTENDANCE_TRIGGERS: Final = (
    "attendance_guard_update",
    "attendance_forbid_delete",
    "attendance_forbid_truncate",
)
MOVEMENTS_TRIGGERS: Final = ("movements_forbid_delete", "movements_forbid_truncate")
BENCHMARKS_TRIGGERS: Final = ("benchmarks_forbid_delete", "benchmarks_forbid_truncate")
WODS_TRIGGERS: Final = ("wods_forbid_delete", "wods_forbid_truncate")
WOD_RESULTS_TRIGGERS: Final = (
    "wod_results_guard_insert",
    "wod_results_guard_update",
    "wod_results_forbid_delete",
    "wod_results_forbid_truncate",
    "wod_results_require_successor",
)
BODY_METRICS_TRIGGERS: Final = (
    "body_metrics_guard_insert",
    "body_metrics_guard_update",
    "body_metrics_forbid_delete",
    "body_metrics_forbid_truncate",
)
PERSONAL_RECORDS_TRIGGERS: Final = (
    "personal_records_guard_insert",
    "personal_records_guard_update",
    "personal_records_forbid_delete",
    "personal_records_forbid_truncate",
)
CRYPTO_TRIGGERS: Final[dict[str, tuple[str, ...]]] = {
    "crypto.crypto_ops": ("crypto_ops_forbid_mutation", "crypto_ops_forbid_truncate"),
    "crypto.crypto_keys": ("crypto_keys_guard", "crypto_keys_forbid_truncate"),
    "crypto.crypto_jobs": ("crypto_jobs_guard", "crypto_jobs_forbid_truncate"),
}
ROTACION_TRIGGERS: Final[dict[str, tuple[str, ...]]] = {
    "crypto.crypto_keys": ("crypto_keys_guard_cierre",),
    "crypto.crypto_jobs": ("crypto_jobs_guard_insert", "crypto_jobs_guard_update"),
}
"""Guardas por rol de `0024_crypto_rotation_from_api` (S6-R1): también `ENABLE ALWAYS`; las
limpiezas las rearman por nombre (si no, `DISABLE TRIGGER USER` las dejaría apagadas)."""
ALWAYS_TRIGGERS: Final[dict[str, tuple[str, ...]]] = {
    AUDIT_LOG_TABLE: AUDIT_LOG_TRIGGERS,
    VERIFICATIONS_TABLE: VERIFICATIONS_TRIGGERS,
    SIGNATURES_TABLE: SIGNATURES_TRIGGERS,  # S6-A1 (0021)
    ATTACHMENTS_TABLE: ATTACHMENTS_TRIGGERS,  # S6-C1 (0023)
    CLASS_SLOTS_TABLE: CLASS_SLOTS_TRIGGERS,  # S7-A2 (0026)
    CLASS_SESSIONS_TABLE: CLASS_SESSIONS_TRIGGERS,  # S7-B1 (0027)
    ATTENDANCE_TABLE: ATTENDANCE_TRIGGERS,  # S7-C1 (0028)
    MOVEMENTS_TABLE: MOVEMENTS_TRIGGERS,  # S8-A1 (0032)
    BENCHMARKS_TABLE: BENCHMARKS_TRIGGERS,  # S8-A2 (0033)
    WODS_TABLE: WODS_TRIGGERS,  # S8-A3 (0034)
    WOD_RESULTS_TABLE: WOD_RESULTS_TRIGGERS,  # S8-B1 (0037)
    BODY_METRICS_TABLE: BODY_METRICS_TRIGGERS,  # S9-A1 (0042)
    PERSONAL_RECORDS_TABLE: PERSONAL_RECORDS_TRIGGERS,  # S9-B1 (0043)
    **{t: (*n, *ROTACION_TRIGGERS.get(t, ())) for t, n in CRYPTO_TRIGGERS.items()},
}
"""Los quince triggers inmutables por tabla (`tgenabled = 'A'`; S6-A1 suma `audit.signatures`, S6-C1
`attachments.attachments`)."""


def disable_user_sql(tabla: str) -> str:
    """Apaga todos los triggers de usuario de `tabla` (incluidos los `ALWAYS`)."""
    if tabla not in ALWAYS_TRIGGERS:
        raise KeyError(tabla)
    return f"ALTER TABLE {tabla} DISABLE TRIGGER USER"


def rearm_always_sql(tabla: str) -> str:
    """Vuelve a encender, uno por nombre y con `ENABLE ALWAYS`, los triggers de `tabla`."""
    opcionales = ROTACION_TRIGGERS.get(tabla, ())
    altas = " ".join(
        f"ALTER TABLE {tabla} ENABLE ALWAYS TRIGGER {nombre};"
        if nombre not in opcionales
        # los de 0024 no existen si la prueba bajó la base a una revisión anterior
        else f"IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '{nombre}' "  # noqa: S608
        f"AND tgrelid = '{tabla}'::regclass) "
        f"THEN ALTER TABLE {tabla} ENABLE ALWAYS TRIGGER {nombre}; END IF;"
        for nombre in ALWAYS_TRIGGERS[tabla]
    )
    return f"DO $$ BEGIN {altas} END $$"
