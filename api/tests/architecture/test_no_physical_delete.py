"""Sin borrado físico de las tablas con borrado lógico o inmutables (US-041 T12, US-076; RN-14,
D21; reglas de datos 4 y 5).

Reemplaza a `test_no_physical_delete_users.py` (S3-B10, D21): ningún archivo de `src/app` borra
físicamente socios, planes, usuarios, membresías (con sus congelaciones), pagos, la auditoría
ni las llaves del bus. Se busca en el texto de cada `.py`:
- `session.delete(` con cualquier objeto (el ORM nunca borra filas en este api);
- `delete(<Modelo>)` de Core sobre `Member`, `Plan`, `User`, `Membership`, `MembershipFreeze`,
  `Payment`, `AuditEntry`, `CryptoKey` y `CryptoOp`;
- `DELETE FROM` y `TRUNCATE` sobre sus tablas (`members.members`, `plans.plans`, `auth.users`,
  `memberships.memberships`, `memberships.membership_freezes`, `payments.payments`,
  `audit.audit_log`, `crypto.crypto_keys`, `crypto.crypto_ops`); S4A-B3 (S4A-D74) suma
  `AuditVerification` y `audit.verifications` (append-only, N-30).
`delete(RefreshToken)` (purga de sesiones caducadas) y `@router.delete(` no son borrados de estas
tablas y pasan. Controles con fuentes falsas.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
MODELOS = (
    "Member",
    "Plan",
    "User",
    "Membership",
    "MembershipFreeze",
    "Payment",
    "AuditEntry",
    "CryptoKey",
    "CryptoOp",
    "AuditVerification",  # S4A-B3 (S4A-D74): append-only (N-30)
    "Notification",  # S5-B7 (RN-14): los avisos se envían u omiten, no se borran
    "NotificationRule",  # S5-B7: las reglas se desactivan
    "NotificationTemplate",  # S5-B7: las plantillas no se borran
    "ClassSlot",  # S7-B1: las franjas se pausan
    "ClassSession",  # S7-B1: las sesiones se cancelan
    "Attendance",  # S7-C1 (RN-14): la asistencia se quita con removed_*, no se borra
    "Movement",  # S8-A1 (RN-14): los movimientos se desactivan
    "Benchmark",  # S8-A2 (RN-14): los benchmarks no se borran
    "Wod",  # S8-A3 (RN-14): los WODs no se borran (`WodMovement` sí: reemplazo de lista, E6)
    "Attachment",  # S6-C1 (S6-D25, RN-14): fila append-only; el objeto se suprime a mano
)
TABLAS = (
    "members.members",
    "plans.plans",
    "auth.users",
    "memberships.memberships",
    "memberships.membership_freezes",
    "payments.payments",
    "audit.audit_log",
    "crypto.crypto_keys",
    "crypto.crypto_ops",
    "audit.verifications",  # S4A-B3 (S4A-D74)
    "notifications.notifications",  # S5-B7
    "notifications.notification_rules",  # S5-B7
    "notifications.notification_templates",  # S5-B7
    "attachments.attachments",  # S6-C1
    "classes.class_slots",  # S7-B1
    "classes.class_sessions",  # S7-B1
    "classes.attendance",  # S7-C1
    "wods.movements",  # S8-A1
    "wods.benchmarks",  # S8-A2
    "wods.wods",  # S8-A3
)
_TABLA = "|".join(re.escape(t) for t in TABLAS)
PATRONES = (
    re.compile(r"session\.delete\("),
    re.compile(rf"(?<![\w.])delete\(\s*(?:{'|'.join(MODELOS)})\s*\)"),
    re.compile(rf"DELETE\s+FROM\s+(?:ONLY\s+)?(?:{_TABLA})\b", re.IGNORECASE),
    re.compile(rf"TRUNCATE\s+(?:TABLE\s+)?(?:ONLY\s+)?(?:{_TABLA})\b", re.IGNORECASE),
)


def violaciones_en(fuente: str) -> list[str]:
    return [m.group(0) for patron in PATRONES for m in patron.finditer(fuente)]


# S8-A3 (E6, regla de datos 4): `wods.wod_movements` no es una tabla de borrado prohibido; `POST` y
# `PATCH /wods` reemplazan la lista completa y el reemplazo se audita fila a fila, por eso se borra
# por la sesión (el hook `after_flush` ve `session.deleted`; un `DELETE` de Core no se auditaría).
# Es la única excepción a `session.delete(`, por archivo.
EXENTO_SESSION_DELETE: Final = frozenset({"modules/wods/programming.py"})


def _violaciones() -> list[str]:
    salida: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        texto = path.read_text(encoding="utf-8")
        relativa = path.relative_to(SRC).as_posix()
        for patron in PATRONES:
            if patron is PATRONES[0] and relativa in EXENTO_SESSION_DELETE:
                continue
            for m in patron.finditer(texto):
                linea = texto.count("\n", 0, m.start()) + 1
                salida.append(f"{path.relative_to(SRC).as_posix()}:{linea}: {m.group(0)}")
    return salida


def test_hay_fuentes_que_revisar() -> None:
    assert len(list(SRC.rglob("*.py"))) > 50


def test_sin_borrado_fisico_en_src() -> None:
    assert _violaciones() == []


def test_el_patron_detecta_cada_forma_de_borrado() -> None:
    fuente = (
        "await session.delete(socio)\n"
        "await session.delete(user)\n"
        "stmt = delete(Member)\n"
        "stmt = delete( Payment )\n"
        "stmt = delete(MembershipFreeze)\n"
        "SQL = 'DELETE FROM members.members WHERE id = :id'\n"
        "SQL = 'delete from payments.payments'\n"
        "SQL = 'DELETE FROM ONLY auth.users'\n"
        "SQL = 'TRUNCATE memberships.memberships'\n"
        "SQL = 'TRUNCATE TABLE audit.audit_log'\n"
        "stmt = delete(AuditVerification)\n"
        "SQL = 'DELETE FROM audit.verifications'\n"
        "SQL = 'TRUNCATE audit.verifications'\n"
    )
    assert len(violaciones_en(fuente)) == 13


def test_el_patron_detecta_el_borrado_de_avisos_reglas_y_plantillas() -> None:
    """S5-B7 (RN-14): las tres tablas de `notifications` no se borran físicamente."""
    fuente = (
        "stmt = delete(Notification)\n"
        "stmt = delete(NotificationRule)\n"
        "stmt = delete(NotificationTemplate)\n"
        "SQL = 'DELETE FROM notifications.notifications'\n"
        "SQL = 'delete from notifications.notification_rules'\n"
        "SQL = 'TRUNCATE notifications.notification_templates'\n"
        "await session.delete(aviso)\n"
    )
    assert len(violaciones_en(fuente)) == 7


def test_el_patron_deja_pasar_lo_legitimo() -> None:
    fuente = (
        '@router.delete("/members/{member_id}", status_code=204)\n'
        "stmt = delete(RefreshToken).where(RefreshToken.expires_at < ahora)\n"
        "socio.deleted_at = ahora  # baja logica\n"
        "SQL = 'DELETE FROM auth.refresh_tokens WHERE expires_at < now()'\n"
        "SQL = 'DELETE FROM members.members_staging'\n"
    )
    assert violaciones_en(fuente) == []


def test_el_patron_detecta_el_borrado_de_adjuntos() -> None:
    """S6-C1 (S6-D25, S6-D76): la fila de `attachments.attachments` no se borra desde el api; la
    supresión a petición es manual y no toca la fila (el trigger la prohíbe)."""
    fuente = (
        "stmt = delete(Attachment)\n"
        "SQL = 'DELETE FROM attachments.attachments'\n"
        "SQL = 'TRUNCATE attachments.attachments'\n"
        "await session.delete(adjunto)\n"
    )
    assert len(violaciones_en(fuente)) == 4
    assert violaciones_en("await storage.delete_object(clave)\n") == []


def test_el_patron_detecta_el_borrado_de_franjas_y_sesiones() -> None:
    """S7-B1 (S7-D10, RN-14): franjas y sesiones no se borran; se pausan y se cancelan."""
    fuente = (
        "stmt = delete(ClassSession)\n"
        "stmt = delete(ClassSlot)\n"
        "SQL = 'DELETE FROM classes.class_sessions'\n"
        "SQL = 'TRUNCATE classes.class_slots'\n"
    )
    assert len(violaciones_en(fuente)) == 4


def test_el_patron_detecta_el_borrado_de_asistencias() -> None:
    """S7-C1 (S7-D13, RN-14): una asistencia se quita con `removed_*`; nunca se borra."""
    fuente = (
        "stmt = delete(Attendance)\n"
        "SQL = 'DELETE FROM classes.attendance'\n"
        "SQL = 'TRUNCATE classes.attendance'\n"
    )
    assert len(violaciones_en(fuente)) == 3
