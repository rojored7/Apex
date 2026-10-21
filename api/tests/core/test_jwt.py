"""JWT Ed25519 de 15 minutos con tolerancia de 30 s, refresh opaco y carga de llaves (US-033)."""

from __future__ import annotations

import base64
import hashlib  # noqa: TID251 - construye un token de ataque HS256
import hmac  # noqa: TID251
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt  # noqa: TID251 - las pruebas forjan tokens; el api solo usa core.security
import pytest
from cryptography.hazmat.primitives import serialization  # noqa: TID251
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: TID251
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key  # noqa: TID251

from app.cli import init_keys_files, key_paths_in
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.crypto.digest import sha256_hex
from app.core.security import (
    AccessClaims,
    JwtKeys,
    StartupError,
    TokenExpired,
    TokenInvalid,
    access_claims,
    configure_jwt,
    create_access_token,
    decode_access_token,
    generate_jwt_keypair_pem,
    hash_opaque_token,
    load_jwt_keys,
    new_opaque_token,
    new_refresh_token,
)

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
USER = UUID(int=5)
MEMBER = UUID(int=6)


@pytest.fixture
def llaves() -> Iterator[JwtKeys]:
    privada, publica = generate_jwt_keypair_pem()
    claves = JwtKeys(private_pem=privada, public_pem=publica)
    configure_jwt(claves, ttl_s=900, leeway_s=30)
    try:
        yield claves
    finally:
        configure_jwt(None)


def test_access_claims_es_pura() -> None:
    claims = access_claims(USER, "coach", MEMBER, T0, ttl_s=900)
    assert claims["sub"] == str(USER) and claims["role"] == "coach"
    assert claims["member_id"] == str(MEMBER)
    assert claims["iat"] == int(T0.timestamp()) and claims["exp"] == claims["iat"] + 900
    assert len(str(claims["jti"])) == 36
    assert access_claims(USER, "admin", None, T0)["member_id"] is None


def test_token_valido_y_claims(llaves: JwtKeys) -> None:
    token = create_access_token(USER, "admin", None, FrozenClock(T0))
    assert jwt.get_unverified_header(token) == {"alg": "EdDSA", "typ": "JWT"}
    claims = decode_access_token(token, FrozenClock(T0 + timedelta(minutes=5)))
    assert isinstance(claims, AccessClaims)
    assert claims.sub == USER and claims.role == "admin" and claims.member_id is None
    assert claims.exp - claims.iat == 900 and claims.jti


def test_vencido_a_los_16_y_valido_a_los_15_20(llaves: JwtKeys) -> None:
    token = create_access_token(USER, "member", MEMBER, FrozenClock(T0))
    decode_access_token(token, FrozenClock(T0 + timedelta(minutes=15, seconds=20)))
    with pytest.raises(TokenExpired):
        decode_access_token(token, FrozenClock(T0 + timedelta(minutes=16)))


def test_otra_llave_alg_none_y_hs256_son_invalidos(llaves: JwtKeys) -> None:
    reloj = FrozenClock(T0)
    otra = Ed25519PrivateKey.generate()
    claims = access_claims(USER, "admin", None, T0)
    ajeno = jwt.encode(claims, otra, algorithm="EdDSA")
    with pytest.raises(TokenInvalid):
        decode_access_token(ajeno, reloj)
    sin_firma = jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(TokenInvalid):
        decode_access_token(sin_firma, reloj)

    # Confusión de algoritmo: HS256 firmado con la pública como secreto (PyJWT se niega a
    # encodearlo, así que se arma a mano).
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    entrada = (
        _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        + "."
        + _b64(json.dumps(claims).encode())
    )
    firma = hmac.new(llaves.public_pem, entrada.encode(), hashlib.sha256).digest()
    hs = entrada + "." + _b64(firma)
    with pytest.raises(TokenInvalid):
        decode_access_token(hs, reloj)
    with pytest.raises(TokenInvalid):
        decode_access_token("no.es.jwt", reloj)


@pytest.mark.parametrize(
    "cambio",
    [{"role": None}, {"role": "superadmin"}, {"jti": None}, {"sub": "no-uuid"}, {"exp": None}],
    ids=["sin-role", "role-ajeno", "sin-jti", "sub-no-uuid", "sin-exp"],
)
def test_claims_faltantes_o_invalidos(llaves: JwtKeys, cambio: dict[str, object]) -> None:
    claims = access_claims(USER, "admin", None, T0)
    for k, v in cambio.items():
        if v is None:
            claims.pop(k)
        else:
            claims[k] = v
    privada = serialization.load_pem_private_key(llaves.private_pem, password=None)
    token = jwt.encode(claims, privada, algorithm="EdDSA")  # type: ignore[arg-type]
    with pytest.raises(TokenInvalid):
        decode_access_token(token, FrozenClock(T0))


def test_refresh_opaco_y_hash() -> None:
    token, h = new_refresh_token()
    crudo = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(crudo) == 32
    assert h == sha256_hex(token.encode("ascii")) == hash_opaque_token(token)
    assert len(h) == 64
    assert new_refresh_token()[0] != token and new_opaque_token() != token


def test_load_jwt_keys_ok_y_fallos(tmp_path: Path, test_database_url: str) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)

    def _settings(privada: Path, publica: Path | None = None) -> Settings:
        return Settings.model_construct(
            DATABASE_URL=test_database_url,
            JWT_PRIVATE_KEY_PATH=privada,
            JWT_PUBLIC_KEY_PATH=publica,
            CRYPTO_PROVIDER="local",
        )

    claves = load_jwt_keys(_settings(rutas.jwt_private, rutas.jwt_public))
    assert claves.public_pem == rutas.jwt_public.read_bytes()
    assert claves.private_pem == rutas.jwt_private.read_bytes()
    with pytest.raises(StartupError, match="JWT_PRIVATE_KEY_PATH") as inexistente:
        load_jwt_keys(_settings(tmp_path / "no.pem"))
    assert "BEGIN" not in str(inexistente.value)
    vacio = tmp_path / "vacio.pem"
    vacio.write_bytes(b"")
    with pytest.raises(StartupError, match="JWT_PRIVATE_KEY_PATH"):
        load_jwt_keys(_settings(vacio))
    rsa = tmp_path / "rsa.pem"
    rsa.write_bytes(
        generate_private_key(65537, 2048).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(StartupError, match="Ed25519"):
        load_jwt_keys(_settings(rsa))
    otra_pub = tmp_path / "otra.pub"
    otra_pub.write_bytes(generate_jwt_keypair_pem()[1])
    with pytest.raises(StartupError, match="JWT_PUBLIC_KEY_PATH"):
        load_jwt_keys(_settings(rutas.jwt_private, otra_pub))


def test_sin_tokens_ni_llaves_en_logs(llaves: JwtKeys, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        token = create_access_token(USER, "admin", None, FrozenClock(T0))
        decode_access_token(token, FrozenClock(T0))
        with pytest.raises(TokenInvalid) as excinfo:
            decode_access_token(token[:-3] + "xyz", FrozenClock(T0))
        refresh, _ = new_refresh_token()
    texto = caplog.text + str(excinfo.value)
    assert "eyJ" not in texto and refresh not in texto
    assert llaves.private_pem.decode()[30:60] not in texto


def test_sin_llaves_configuradas() -> None:
    configure_jwt(None)
    with pytest.raises(StartupError):
        create_access_token(uuid4(), "admin", None, FrozenClock(T0))
