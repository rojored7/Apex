"""CBOM `apex-cbom/1`: inventario criptográfico sin material ni referencias (S6-D17, S6-D57, Q26).

`build_cbom` es pura: sin sesión, reloj, entorno ni proveedor, y no importa `app.modules` ni
`core.audit*`. Ordena las llaves por `(data_class, purpose, version)` y conserva solo `id`,
`purpose`, `data_class`, `algorithm`, `version`, `state`, `provider`, `created_at` y
`rotated_at`: nunca `records_count`, `age_days`, material ni referencias. Devuelve un `dict`
listo para JSON (fechas ISO 8601 en UTC con `Z`). `tls` es declarativo: viene de la
configuración, no de una sonda de red.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final

from app.core.crypto.schemas import CryptoKeyOut, ProviderSummary

CBOM_FORMAT: Final = "apex-cbom/1"

# Algoritmos fijos del sistema, uno por uso (ADR-002).
FIXED_ALGORITHMS: Final[tuple[dict[str, str], ...]] = (
    {"use": "JWT de acceso (firma)", "algorithm": "Ed25519"},
    {"use": "Contraseñas (password hash)", "algorithm": "argon2id"},
    {"use": "Índices ciegos (index)", "algorithm": "HMAC-SHA256"},
    {"use": "Cadena de auditoría (chain)", "algorithm": "SHA-256"},
    {"use": "Firma de la auditoría (sign)", "algorithm": "Ed25519"},
    {"use": "Respaldos (backup)", "algorithm": "age"},
)


def _iso(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _llave(k: CryptoKeyOut) -> dict[str, Any]:
    return {
        "id": str(k.id),
        "purpose": k.purpose,
        "data_class": k.data_class,
        "algorithm": k.algorithm,
        "version": k.version,
        "state": k.state,
        "provider": k.provider,
        "created_at": _iso(k.created_at),
        "rotated_at": _iso(k.rotated_at),
    }


def build_cbom(
    keys: Sequence[CryptoKeyOut],
    *,
    app_version: str,
    generated_at: datetime,
    provider: ProviderSummary,
    tls_declared: bool,
) -> dict[str, Any]:
    ordenadas = sorted(keys, key=lambda k: (k.data_class, k.purpose, k.version))
    return {
        "format": CBOM_FORMAT,
        "generated_at": _iso(generated_at),
        "app_version": app_version,
        "provider": {"names": list(provider.names), "state": provider.state},
        "keys": [_llave(k) for k in ordenadas],
        "fixed_algorithms": [dict(a) for a in FIXED_ALGORITHMS],
        "tls": {"declared": tls_declared, "source": "configuration"},
    }
