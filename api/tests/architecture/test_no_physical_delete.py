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
  `audit.audit_log`, `crypto.crypto_keys`, `crypto.crypto_ops`).
`delete(RefreshToken)` (purga de sesiones caducadas) y `@router.delete(` no son borrados de estas
tablas y pasan. Controles con fuentes falsas.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def _violaciones() -> list[str]:
    salida: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        texto = path.read_text(encoding="utf-8")
        for patron in PATRONES:
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
    )
    assert len(violaciones_en(fuente)) == 10


def test_el_patron_deja_pasar_lo_legitimo() -> None:
    fuente = (
        '@router.delete("/members/{member_id}", status_code=204)\n'
        "stmt = delete(RefreshToken).where(RefreshToken.expires_at < ahora)\n"
        "socio.deleted_at = ahora  # baja logica\n"
        "SQL = 'DELETE FROM auth.refresh_tokens WHERE expires_at < now()'\n"
        "SQL = 'DELETE FROM members.members_staging'\n"
    )
    assert violaciones_en(fuente) == []
