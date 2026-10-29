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

AUDIT_LOG_TRIGGERS: Final = ("audit_log_forbid_mutation", "audit_log_forbid_truncate")
VERIFICATIONS_TRIGGERS: Final = ("verifications_forbid_mutation", "verifications_forbid_truncate")
CRYPTO_TRIGGERS: Final[dict[str, tuple[str, ...]]] = {
    "crypto.crypto_ops": ("crypto_ops_forbid_mutation", "crypto_ops_forbid_truncate"),
    "crypto.crypto_keys": ("crypto_keys_guard", "crypto_keys_forbid_truncate"),
    "crypto.crypto_jobs": ("crypto_jobs_guard", "crypto_jobs_forbid_truncate"),
}
ALWAYS_TRIGGERS: Final[dict[str, tuple[str, ...]]] = {
    AUDIT_LOG_TABLE: AUDIT_LOG_TRIGGERS,
    VERIFICATIONS_TABLE: VERIFICATIONS_TRIGGERS,
    **CRYPTO_TRIGGERS,
}
"""Los diez triggers inmutables por tabla (`tgenabled = 'A'` tras `0014`)."""


def disable_user_sql(tabla: str) -> str:
    """Apaga todos los triggers de usuario de `tabla` (incluidos los `ALWAYS`)."""
    if tabla not in ALWAYS_TRIGGERS:
        raise KeyError(tabla)
    return f"ALTER TABLE {tabla} DISABLE TRIGGER USER"


def rearm_always_sql(tabla: str) -> str:
    """Vuelve a encender, uno por nombre y con `ENABLE ALWAYS`, los triggers de `tabla`."""
    altas = " ".join(
        f"ALTER TABLE {tabla} ENABLE ALWAYS TRIGGER {nombre};" for nombre in ALWAYS_TRIGGERS[tabla]
    )
    return f"DO $$ BEGIN {altas} END $$"
