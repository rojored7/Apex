"""Datos y consultas compartidos por las pruebas de settings (S2-B1).

Los valores válidos siguen N-18 (desgloses US-055, US-057 y US-058). Las consultas leen la
base con SQL directo para no depender de lo que el service devuelva.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry

API = "/api/v1"
TABLA = "settings.settings_sections"
ADMIN_ID = UUID(int=201)  # int=1 es SYSTEM_USER_ID

GYM_OK: dict[str, Any] = {
    "name": "CrossFit Envigado",
    "nit": "901234567-8",
    "address": "Cra 43A # 1-50",
    "city": "Envigado",
    "phone": "6044440000",
    "whatsapp": "3001234567",
    "email": "hola@crossfitenvigado.co",
}
GYM_DEFAULTS: dict[str, Any] = {
    "name": "APEX",
    "nit": None,
    "address": None,
    "city": None,
    "phone": None,
    "whatsapp": None,
    "email": None,
}
PRIVACY_OK: dict[str, Any] = {
    "policy_version": "2026-10",
    "policy_text": "APEX trata tus datos según la Ley 1581 de 2012.",
    "retention_years": 5,
    "consent_required_from": None,
}
PRIVACY_DEFAULTS: dict[str, Any] = {
    "policy_version": None,
    "policy_text": None,
    "retention_years": 5,
    "consent_required_from": None,
}
MEMBERSHIPS_OK: dict[str, Any] = {
    "expiring_days": 5,
    "max_freeze_days_per_membership": 30,
    "max_freezes_per_membership": 2,
    "max_retroactive_days": 7,
}
MEMBERSHIPS_DEFAULTS: dict[str, Any] = {
    "expiring_days": 7,
    "max_freeze_days_per_membership": 30,
    "max_freezes_per_membership": 2,
    "max_retroactive_days": 7,
}

# Secciones que existen en el CHECK pero no están habilitadas en el Sprint 2 (S2-D15), más
# una clave inexistente y una con mayúsculas.
NO_HABILITADAS = ("tv", "hours", "channels", "classes", "payment_methods")
DESCONOCIDAS = ("inexistente", "GYM")

# Las ocho rutas del router (S2-D15): tipadas y genérica.
RUTAS = (
    ("GET", "/settings/gym"),
    ("PATCH", "/settings/gym"),
    ("GET", "/settings/privacy"),
    ("PATCH", "/settings/privacy"),
    ("GET", "/settings/memberships"),
    ("PATCH", "/settings/memberships"),
    ("GET", "/settings/tv"),  # genérica `/settings/{section}`
    ("PATCH", "/settings/tv"),
)
CUERPOS = {
    "/settings/gym": {"value": GYM_OK, "version": 0},
    "/settings/privacy": {"value": PRIVACY_OK, "version": 0},
    "/settings/memberships": {"value": MEMBERSHIPS_OK, "version": 0},
    "/settings/tv": {"value": {}, "version": 0},
}


async def filas_de_auditoria(session: AsyncSession) -> list[dict[str, Any]]:
    """Filas de `audit.audit_log` de la tabla de settings, en orden de la cadena."""
    tabla = AuditEntry.__table__
    consulta = select(tabla).where(tabla.c.table_name == TABLA).order_by(tabla.c.seq)
    return [dict(f) for f in (await session.execute(consulta)).mappings().all()]


async def fila(session: AsyncSession, key: str) -> dict[str, Any] | None:
    """La fila guardada de una sección, o `None` si nunca se guardó."""
    resultado = await session.execute(
        text(
            "SELECT key, value, version, created_by, updated_by, updated_at "
            "FROM settings.settings_sections WHERE key = :key"
        ),
        {"key": key},
    )
    encontrada = resultado.mappings().first()
    return dict(encontrada) if encontrada is not None else None


async def contar_filas(session: AsyncSession) -> int:
    total = await session.scalar(text("SELECT count(*) FROM settings.settings_sections"))
    return int(total or 0)
