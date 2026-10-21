"""Seguridad de la plataforma (US-023 A-1, US-032, US-033; US-034/035 agregan `Principal`,
`PrincipalLoader` y `require_role`).

Es, junto con `core/crypto`, el único lugar que importa `cryptography`, `jwt`, `argon2` y
`hashlib` (regla 8 del bus, lint `banned-api`). No importa ningún módulo: recibe `user_id`,
`role` y `member_id` como valores, nunca el modelo `User`.

- Llaves JWT Ed25519: `generate_jwt_keypair_pem` (las crea `init-keys`), `load_jwt_keys`
  (lee `JWT_PRIVATE_KEY_PATH`, exige Ed25519, deriva la pública y, si viene
  `JWT_PUBLIC_KEY_PATH`, comprueba que coincide; nunca imprime contenido).
- Contraseñas (US-032): argon2id con parámetros de `Settings`; política N-10
  (`PASSWORD_MIN_LENGTH` y lista corta de comunes en `common_passwords.txt`). `hash_password`
  y `verify_password` cuestan CPU: el service de auth los envuelve en
  `anyio.to_thread.run_sync`. `dummy_verify` iguala el tiempo de un correo inexistente.
- Sesiones (US-033): access JWT `EdDSA` de `ACCESS_TOKEN_TTL_S` con tolerancia
  `JWT_LEEWAY_S` (N-14); la lista de algoritmos es fija y nunca hay `verify_signature=False`.
  `TokenExpired` solo para vencido con firma válida (401 `token_expired`); todo lo demás es
  `TokenInvalid` (401 `unauthorized`). El refresh es opaco (32 bytes base64url) y solo se
  persiste su SHA-256 (`hash_opaque_token`, también para los tokens de un solo uso).
`configure_security(settings)` lo llama el lifespan de `create_app`, el worker y el CLI.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any, Final, Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.clock import Clock
from app.core.config import Settings

Role = Literal["admin", "coach", "member"]
ROLES: Final[tuple[str, ...]] = ("admin", "coach", "member")
WeakReason = Literal["too_short", "too_common"]
JWT_ALGORITHM: Final = "EdDSA"
REQUIRED_CLAIMS: Final[tuple[str, ...]] = ("exp", "iat", "sub", "role", "jti")
OPAQUE_TOKEN_BYTES: Final = 32


class StartupError(RuntimeError):
    """El arranque no puede continuar (llave JWT ausente o inválida)."""


class WeakPasswordError(ValueError):
    """La contraseña no cumple la política (N-10). El mensaje nunca la incluye."""

    def __init__(self, reason: WeakReason) -> None:
        super().__init__(f"contraseña débil: {reason}")
        self.reason: WeakReason = reason


class TokenExpired(Exception):
    """Access token vencido con firma válida (401 `token_expired`)."""


class TokenInvalid(Exception):
    """Cualquier otro fallo del token (401 `unauthorized`)."""


@dataclass(frozen=True)
class JwtKeys:
    private_pem: bytes
    public_pem: bytes

    def __repr__(self) -> str:
        return "JwtKeys(•••)"


@dataclass(frozen=True)
class AccessClaims:
    sub: UUID
    role: Role
    member_id: UUID | None
    iat: int
    exp: int
    jti: str


# Llaves JWT -----------------------------------------------------------------------------


def generate_jwt_keypair_pem() -> tuple[bytes, bytes]:
    """Par Ed25519 nuevo: (privada PKCS8 PEM sin cifrar, pública SubjectPublicKeyInfo PEM)."""
    privada = Ed25519PrivateKey.generate()
    return _private_pem(privada), _public_pem(privada)


def public_pem_from_private_pem(private_pem: bytes) -> bytes:
    """La pública PEM que corresponde a una privada PEM existente (sin contraseña)."""
    return _public_pem(_load_private(private_pem))


def _load_private(private_pem: bytes) -> Ed25519PrivateKey:
    privada = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(privada, Ed25519PrivateKey):
        raise ValueError("la llave JWT debe ser Ed25519")
    return privada


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


def load_jwt_keys(settings: Settings) -> JwtKeys:
    """Lee la privada del volumen `keys` y deriva la pública. Falla sin mostrar contenido."""
    ruta = settings.JWT_PRIVATE_KEY_PATH
    try:
        private_pem = ruta.read_bytes()
    except OSError:
        raise StartupError(
            f"JWT_PRIVATE_KEY_PATH: archivo inexistente o ilegible ({ruta})"
        ) from None
    if not private_pem.strip():
        raise StartupError(f"JWT_PRIVATE_KEY_PATH: archivo vacío ({ruta})")
    try:
        privada = _load_private(private_pem)
    except ValueError:
        raise StartupError("JWT_PRIVATE_KEY_PATH: la llave debe ser Ed25519 en PEM PKCS8") from None
    public_pem = _public_pem(privada)
    if settings.JWT_PUBLIC_KEY_PATH is not None:
        try:
            declarada = settings.JWT_PUBLIC_KEY_PATH.read_bytes()
        except OSError:
            raise StartupError("JWT_PUBLIC_KEY_PATH: archivo inexistente o ilegible") from None
        if declarada.strip() != public_pem.strip():
            raise StartupError("JWT_PUBLIC_KEY_PATH: la pública no corresponde a la privada")
    return JwtKeys(private_pem=private_pem, public_pem=public_pem)


_jwt_keys: JwtKeys | None = None
_jwt_private: Ed25519PrivateKey | None = None
_ttl_s = 900
_leeway_s = 30


def configure_jwt(keys: JwtKeys | None, *, ttl_s: int = 900, leeway_s: int = 30) -> None:
    global _jwt_keys, _jwt_private, _ttl_s, _leeway_s
    _jwt_keys = keys
    _jwt_private = _load_private(keys.private_pem) if keys is not None else None
    _ttl_s = ttl_s
    _leeway_s = leeway_s


def _keys() -> tuple[JwtKeys, Ed25519PrivateKey]:
    if _jwt_keys is None or _jwt_private is None:
        raise StartupError("las llaves JWT no están configuradas (configure_security)")
    return _jwt_keys, _jwt_private


def access_claims(
    user_id: UUID, role: Role, member_id: UUID | None, now: datetime, *, ttl_s: int = 900
) -> dict[str, object]:
    """Claims del access token (pura): `sub`, `role`, `member_id`, `iat`, `exp`, `jti`."""
    iat = int(now.timestamp())
    return {
        "sub": str(user_id),
        "role": role,
        "member_id": str(member_id) if member_id is not None else None,
        "iat": iat,
        "exp": iat + ttl_s,
        "jti": str(uuid4()),
    }


def create_access_token(user_id: UUID, role: Role, member_id: UUID | None, clock: Clock) -> str:
    _, privada = _keys()
    claims = access_claims(user_id, role, member_id, clock.now_utc(), ttl_s=_ttl_s)
    return jwt.encode(claims, privada, algorithm=JWT_ALGORITHM, headers={"typ": "JWT"})


def decode_access_token(token: str, clock: Clock) -> AccessClaims:
    keys, _ = _keys()
    ahora = int(clock.now_utc().timestamp())
    try:
        # La firma y los claims obligatorios los valida PyJWT; `exp` e `iat` se comparan
        # aquí contra `core/clock` (único reloj del api), con la tolerancia N-14.
        datos: dict[str, Any] = jwt.decode(
            token,
            keys.public_pem,
            algorithms=[JWT_ALGORITHM],
            options={"require": list(REQUIRED_CLAIMS), "verify_exp": False, "verify_iat": False},
        )
    except jwt.PyJWTError:
        raise TokenInvalid from None
    try:
        exp, iat = int(datos["exp"]), int(datos["iat"])
    except (TypeError, ValueError):
        raise TokenInvalid from None
    if iat - _leeway_s > ahora:
        raise TokenInvalid  # emitido en el futuro
    if exp + _leeway_s < ahora:
        raise TokenExpired
    role = datos.get("role")
    if role not in ROLES:
        raise TokenInvalid
    try:
        sub = UUID(str(datos["sub"]))
        member = datos.get("member_id")
        member_id = UUID(str(member)) if member is not None else None
    except ValueError:
        raise TokenInvalid from None
    return AccessClaims(
        sub=sub,
        role=role,
        member_id=member_id,
        iat=int(datos["iat"]),
        exp=int(datos["exp"]),
        jti=str(datos["jti"]),
    )


def new_opaque_token() -> str:
    """32 bytes aleatorios en base64url sin relleno (refresh y tokens de un solo uso)."""
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """SHA-256 hexadecimal del token: lo único que se persiste (N-13)."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    token = new_opaque_token()
    return token, hash_opaque_token(token)


# Contraseñas ----------------------------------------------------------------------------


def _load_common_passwords() -> frozenset[str]:
    texto = resources.files("app.core").joinpath("common_passwords.txt").read_text("utf-8")
    return frozenset(linea.strip().lower() for linea in texto.splitlines() if linea.strip())


COMMON_PASSWORDS: Final[frozenset[str]] = _load_common_passwords()

_hasher = PasswordHasher(type=Type.ID)
_min_length = 12


def configure_password_hasher(time_cost: int, memory_cost_kib: int, parallelism: int) -> None:
    global _hasher
    _hasher = PasswordHasher(
        time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=parallelism, type=Type.ID
    )
    _refresh_dummy()


def configure_password_policy(min_length: int) -> None:
    global _min_length
    _min_length = min_length


def validate_password_policy(plain: str) -> None:
    if len(plain) < _min_length:
        raise WeakPasswordError("too_short")
    if plain.lower() in COMMON_PASSWORDS:
        raise WeakPasswordError("too_common")


def hash_password(plain: str) -> str:
    validate_password_policy(plain)
    return _hasher.hash(plain)


def verify_password(hash_: str, plain: str) -> bool:
    try:
        return bool(_hasher.verify(hash_, plain))
    except (VerifyMismatchError, InvalidHashError, VerificationError, HashingError):
        return False


def needs_rehash(hash_: str) -> bool:
    try:
        return bool(_hasher.check_needs_rehash(hash_))
    except (InvalidHashError, VerificationError, ValueError):
        return True


_dummy_hash = ""


def _refresh_dummy() -> None:
    global _dummy_hash
    _dummy_hash = _hasher.hash(secrets.token_urlsafe(24))


_refresh_dummy()


def dummy_verify(plain: str) -> None:
    """Verifica contra un hash ficticio: un correo inexistente tarda lo mismo que uno real."""
    verify_password(_dummy_hash, plain)


# Arranque -------------------------------------------------------------------------------


def configure_security(settings: Settings) -> None:
    """Carga las llaves JWT y fija parámetros de argon2 y política desde `Settings`."""
    configure_password_hasher(
        settings.ARGON2_TIME_COST, settings.ARGON2_MEMORY_COST_KIB, settings.ARGON2_PARALLELISM
    )
    configure_password_policy(settings.PASSWORD_MIN_LENGTH)
    configure_jwt(
        load_jwt_keys(settings), ttl_s=settings.ACCESS_TOKEN_TTL_S, leeway_s=settings.JWT_LEEWAY_S
    )
