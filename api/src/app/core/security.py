"""Seguridad de la plataforma: llaves JWT Ed25519 (US-023 A-1); argon2id, JWT, `Principal`,
`PrincipalLoader` y `require_role` llegan en US-032 a US-035.

Es, junto con `core/crypto`, el único lugar que importa `cryptography`, `jwt` y `argon2`
(regla 8 del bus, lint `banned-api`).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_jwt_keypair_pem() -> tuple[bytes, bytes]:
    """Par Ed25519 nuevo: (privada PKCS8 PEM sin cifrar, pública SubjectPublicKeyInfo PEM)."""
    privada = Ed25519PrivateKey.generate()
    return _private_pem(privada), _public_pem(privada)


def public_pem_from_private_pem(private_pem: bytes) -> bytes:
    """La pública PEM que corresponde a una privada PEM existente (sin contraseña)."""
    privada = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(privada, Ed25519PrivateKey):
        raise ValueError("la llave JWT debe ser Ed25519")
    return _public_pem(privada)


def _private_pem(privada: Ed25519PrivateKey) -> bytes:
    return privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_pem(privada: Ed25519PrivateKey) -> bytes:
    return privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
