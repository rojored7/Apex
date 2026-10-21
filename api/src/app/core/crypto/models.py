"""Tablas del bus: `crypto_keys`, `crypto_ops` y `crypto_jobs` (US-024 T5; esquema `crypto`).

- `crypto_keys`: inventario de llaves con material solo envuelto (`wrapped_material` es la
  salida de `KeyProvider.wrap`); una sola llave `active` por (`purpose`, `data_class`);
  las transiciones de `state` las vigila el trigger `crypto.guard_keys_update`
  (`active → decrypt_only`, `decrypt_only → retired`, `active → retired`); nunca se borra.
- `crypto_ops`: bitácora append-only (quién, verbo, data_class, llave, registro, resultado,
  `batch_id` y `count` por lote, `purpose` del descifrado). Sin columnas para valores.
- `crypto_jobs`: progreso de rotaciones, recifrados, migraciones de proveedor y
  re-envolturas; un solo job en curso por clase.

Estas tablas no son `__audited__`: su bitácora propia es `crypto_ops`
(`tests/architecture/test_audited_tables.py` las excluye). Ningún módulo de negocio las
importa; solo el bus, el keyring y `core/crypto/service.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

KeyPurpose = Literal["encrypt", "index", "sign"]
KeyState = Literal["active", "decrypt_only", "retired"]
Algorithm = Literal["A256GCM", "HMAC-SHA256", "Ed25519", "ML-DSA-65"]
Provider = Literal["local", "openbao"]
OpVerb = Literal[
    "encrypt", "decrypt", "index", "sign", "verify", "wrap", "unwrap", "rotate", "export"
]
OpResult = Literal["ok", "error"]
OpPurpose = Literal["mask", "reveal", "notify", "auth_link", "export"]
JobKind = Literal["rotate", "reencrypt", "migrate_provider", "rewrap"]
JobStatus = Literal["pending", "running", "done", "failed"]

KEY_PURPOSES: tuple[str, ...] = ("encrypt", "index", "sign")
KEY_STATES: tuple[str, ...] = ("active", "decrypt_only", "retired")
ALGORITHMS: tuple[str, ...] = ("A256GCM", "HMAC-SHA256", "Ed25519", "ML-DSA-65")
PROVIDERS: tuple[str, ...] = ("local", "openbao")
OP_VERBS: tuple[str, ...] = (
    "encrypt",
    "decrypt",
    "index",
    "sign",
    "verify",
    "wrap",
    "unwrap",
    "rotate",
    "export",
)
OP_RESULTS: tuple[str, ...] = ("ok", "error")
OP_PURPOSES: tuple[str, ...] = ("mask", "reveal", "notify", "auth_link", "export")
JOB_KINDS: tuple[str, ...] = ("rotate", "reencrypt", "migrate_provider", "rewrap")
JOB_STATUSES: tuple[str, ...] = ("pending", "running", "done", "failed")
DATA_CLASS_PATTERN = r"^[a-z_]+\.[a-z_]+$"


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class CryptoKey(CommonColumnsMixin, Base):
    __tablename__ = "crypto_keys"
    __table_args__ = (
        CheckConstraint(f"purpose IN ({_in(KEY_PURPOSES)})", name="purpose"),
        CheckConstraint(f"data_class ~ '{DATA_CLASS_PATTERN}'", name="data_class"),
        CheckConstraint(f"algorithm IN ({_in(ALGORITHMS)})", name="algorithm"),
        CheckConstraint(
            "(purpose = 'encrypt' AND algorithm = 'A256GCM') OR "
            "(purpose = 'index' AND algorithm = 'HMAC-SHA256') OR "
            "(purpose = 'sign' AND algorithm IN ('Ed25519', 'ML-DSA-65'))",
            name="purpose_algorithm",
        ),
        CheckConstraint(f"provider IN ({_in(PROVIDERS)})", name="provider"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint(f"state IN ({_in(KEY_STATES)})", name="state"),
        UniqueConstraint("purpose", "data_class", "version", name="uq_crypto_keys_version"),
        Index(
            "uq_crypto_keys_active",
            "purpose",
            "data_class",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        {"schema": "crypto"},
    )

    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    data_class: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    wrapped_material: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rotated_by: Mapped[UUID | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:  # sin wrapped_material
        return (
            f"CryptoKey(purpose={self.purpose!r}, data_class={self.data_class!r}, "
            f"version={self.version}, state={self.state!r})"
        )


class CryptoOp(CommonColumnsMixin, Base):
    __tablename__ = "crypto_ops"
    __table_args__ = (
        CheckConstraint(f"verb IN ({_in(OP_VERBS)})", name="verb"),
        CheckConstraint(f"result IN ({_in(OP_RESULTS)})", name="result"),
        CheckConstraint("count >= 1", name="count"),
        Index("ix_crypto_ops_at", text("at DESC")),
        Index("ix_crypto_ops_data_class_at", "data_class", text("at DESC")),
        Index("ix_crypto_ops_key_id", "key_id"),
        Index("ix_crypto_ops_batch_id", "batch_id", postgresql_where=text("batch_id IS NOT NULL")),
        Index(
            "ix_crypto_ops_record_id",
            "record_id",
            postgresql_where=text("record_id IS NOT NULL"),
        ),
        {"schema": "crypto"},
    )

    at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    verb: Mapped[str] = mapped_column(Text, nullable=False)
    data_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_id: Mapped[UUID | None] = mapped_column(nullable=True)
    key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CryptoJob(CommonColumnsMixin, Base):
    __tablename__ = "crypto_jobs"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(JOB_KINDS)})", name="kind"),
        CheckConstraint(f"status IN ({_in(JOB_STATUSES)})", name="status"),
        CheckConstraint("total >= 0", name="total"),
        CheckConstraint("done >= 0 AND done <= total", name="done"),
        Index(
            "uq_crypto_jobs_in_progress",
            text("coalesce(data_class, '*')"),
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        {"schema": "crypto"},
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    data_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
