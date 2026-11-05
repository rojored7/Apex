"""`OpenBaoProvider` sobre `FakeTransit` (S5-B1; S5-D17, D107, D108, D123, D124; M-4).

Cubre `map_error`, `parse_version`, el manejo del token (archivo, permisos, relectura, jamás en
repr, logs, excepciones ni `crypto_ops`), la política de red del cliente, la renovación con
`renew-self` (nunca `lookup-self`) y `status`.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import oplog
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.openbao_provider import (
    KEK_KEY,
    OpenBaoProvider,
    map_error,
    parse_version,
)
from tests.factories.fake_transit import ADDR_FAKE, TOKEN_FAKE, FakeTransit

DEK = bytes(range(32))
SOLO_POSIX = pytest.mark.skipif(
    os.name == "nt", reason="NTFS no conserva el modo POSIX: corre en CI/Linux"
)


async def _error_de(coro: Any) -> CryptoError:
    with pytest.raises(CryptoError) as info:
        await coro
    return info.value


def _reason(error: CryptoError) -> str:
    assert isinstance(error, CryptoUnavailable), repr(error)
    return error.reason


# map_error -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "errors", "code", "reason"),
    [
        (503, ["Vault is sealed"], "crypto_unavailable", "sealed"),
        (403, ["permission denied"], "crypto_unavailable", "forbidden"),
        (404, ["no existe la llave"], "key_missing", None),
        (500, ["internal error"], "crypto_unavailable", "unreachable"),
        (502, [], "crypto_unavailable", "unreachable"),
        (504, [], "crypto_unavailable", "unreachable"),
        (429, ["rate limit"], "crypto_unavailable", "unreachable"),
        (503, ["standby"], "crypto_unavailable", "unreachable"),
        (401, [], "crypto_unavailable", "forbidden"),
        (400, ["cipher: message authentication failed"], "unwrap_failed", None),
    ],
)
def test_map_error_tabla(status: int, errors: list[str], code: str, reason: str | None) -> None:
    error = map_error(status, errors)
    assert isinstance(error, CryptoError) and error.code == code
    if reason is not None:
        assert isinstance(error, CryptoUnavailable) and error.reason == reason


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
def test_map_error_nunca_copia_el_cuerpo(status: int) -> None:
    error = map_error(status, ["CUERPO-SECRETO-123 vault:v1:AAAA s.token"])
    assert "CUERPO-SECRETO" not in str(error) + repr(error) + error.message


# parse_version ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("envuelta", "version"),
    [(b"vault:v1:abc", 1), (b"vault:v2:abc=", 2), (b"vault:v12:xyz", 12)],
)
def test_parse_version(envuelta: bytes, version: int) -> None:
    assert parse_version(envuelta) == version


@pytest.mark.parametrize(
    "envuelta", [b"", b"apxw1" + b"x" * 40, b"vault:vX:abc", b"vault:v:abc", b"basura", b"v1:abc"]
)
def test_parse_version_sin_prefijo_valido_es_unwrap_failed(envuelta: bytes) -> None:
    with pytest.raises(CryptoError) as error:
        parse_version(envuelta)
    assert error.value.code == "unwrap_failed"


# Errores del servidor mapeados por el proveedor ------------------------------------------------


async def test_sellado_es_crypto_unavailable_sealed(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.seal()
    assert _reason(await _error_de(openbao_fake.wrap(DEK))) == "sealed"
    assert _reason(await _error_de(openbao_fake.unwrap(b"vault:v1:AAAA"))) == "sealed"


async def test_token_rechazado_es_forbidden(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.revoke_token()
    assert _reason(await _error_de(openbao_fake.wrap(DEK))) == "forbidden"


async def test_timeout_y_conexion_son_unreachable(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.timeout_en("/encrypt/")
    fake_transit.conexion_rota_en("/decrypt/")
    assert _reason(await _error_de(openbao_fake.wrap(DEK))) == "unreachable"
    assert _reason(await _error_de(openbao_fake.unwrap(b"vault:v1:AAAA"))) == "unreachable"


async def test_sin_reintentos_dentro_del_proveedor(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.timeout_en("/encrypt/")
    await _error_de(openbao_fake.wrap(DEK))
    assert len(fake_transit.llamadas("/encrypt/")) == 1


async def test_404_y_500_del_servidor(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.responder("/encrypt/", 404, ["no existe"], veces=1)
    assert (await _error_de(openbao_fake.wrap(DEK))).code == "key_missing"
    fake_transit.responder("/encrypt/", 500, ["CUERPO-SECRETO-XYZ"], veces=1)
    error = await _error_de(openbao_fake.wrap(DEK))
    assert _reason(error) == "unreachable" and "CUERPO-SECRETO-XYZ" not in str(error)


async def test_los_errores_no_llevan_url_ni_ruta(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.conexion_rota_en("/encrypt/")
    error = await _error_de(openbao_fake.wrap(DEK))
    texto = str(error) + repr(error) + "".join(traceback.format_exception(error))
    assert "openbao:8200" not in texto and "/v1/" not in texto


# El token no se filtra (S5-D17; M-4) -----------------------------------------------------------


def test_repr_fijo(openbao_fake: OpenBaoProvider) -> None:
    assert repr(openbao_fake) == "OpenBaoProvider()"
    assert TOKEN_FAKE not in str(openbao_fake)


async def test_el_token_solo_viaja_en_x_vault_token(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    await openbao_fake.unwrap(await openbao_fake.wrap(DEK))
    await openbao_fake.sign("apex-sign-audit", b"d")
    await openbao_fake.rotate(KEK_KEY)
    await openbao_fake.key_info(KEK_KEY)
    await openbao_fake.status()
    assert fake_transit.calls
    for llamada in fake_transit.calls:
        if llamada.path == "/v1/sys/seal-status":
            assert "x-vault-token" not in llamada.headers
            continue
        assert llamada.headers["x-vault-token"] == TOKEN_FAKE, llamada.path
        assert TOKEN_FAKE not in llamada.url
        assert TOKEN_FAKE not in json.dumps(llamada.body)
        assert "authorization" not in llamada.headers


async def test_el_token_no_esta_en_logs_excepciones_ni_crypto_ops(
    openbao_fake: OpenBaoProvider,
    fake_transit: FakeTransit,
    caplog: pytest.LogCaptureFixture,
    sin_llaves: Any,
) -> None:
    caplog.set_level(logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.INFO)
    visto: list[str] = []
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, openbao_fake, lambda _n: openbao_fake)
    visto.append(repr(oplog.pending_rows()))
    for preparar in (fake_transit.seal, fake_transit.unseal, fake_transit.revoke_token):
        preparar()
        try:
            await openbao_fake.wrap(DEK)
        except CryptoError as error:
            visto.append(str(error) + repr(error) + "".join(traceback.format_exception(error)))
    fake_transit.timeout_en("/decrypt/")
    try:
        await openbao_fake.unwrap(b"vault:v1:AAAA")
    except CryptoError as error:
        visto.append(str(error) + repr(error) + "".join(traceback.format_exception(error)))
    assert len(visto) == 4
    for texto in [*visto, caplog.text, repr(openbao_fake)]:
        assert TOKEN_FAKE not in texto


# Archivo del token (S5-D17, S5-D123) -----------------------------------------------------------


def _con_token(ruta: Path, contenido: str, modo: int = 0o600) -> Path:
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(modo)
    return ruta


async def test_archivo_inexistente_es_kek_missing(
    tmp_path: Path, fake_transit: FakeTransit
) -> None:
    with pytest.raises(CryptoError) as error:
        proveedor = OpenBaoProvider(
            ADDR_FAKE, tmp_path / "no-hay", timeout_s=1, client=fake_transit.cliente()
        )
        await proveedor.wrap(DEK)
    assert error.value.code == "kek_missing"


@SOLO_POSIX
@pytest.mark.parametrize("modo", [0o640, 0o644, 0o604, 0o660, 0o777])
async def test_archivo_con_permisos_de_grupo_u_otros_se_rechaza(
    tmp_path: Path, fake_transit: FakeTransit, modo: int
) -> None:
    ruta = _con_token(tmp_path / "token", TOKEN_FAKE, modo)
    with pytest.raises(CryptoError) as error:
        proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
        await proveedor.wrap(DEK)
    assert error.value.code == "kek_insecure_permissions"
    assert not fake_transit.calls  # no se llegó a hablar con el servidor


async def test_archivo_de_mas_de_256_bytes_se_rechaza(
    tmp_path: Path, fake_transit: FakeTransit
) -> None:
    ruta = _con_token(tmp_path / "token", "s." + "a" * 300)
    with pytest.raises(CryptoError) as error:
        proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
        await proveedor.wrap(DEK)
    assert error.value.code == "kek_invalid"
    assert not fake_transit.calls


async def test_archivo_vacio_se_rechaza(tmp_path: Path, fake_transit: FakeTransit) -> None:
    ruta = _con_token(tmp_path / "token", "\n")
    with pytest.raises(CryptoError) as error:
        proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
        await proveedor.wrap(DEK)
    assert error.value.code == "kek_invalid"


async def test_el_token_se_recorta_y_se_relee_al_cambiar_mtime(
    tmp_path: Path, fake_transit: FakeTransit
) -> None:
    ruta = _con_token(tmp_path / "token", "tok-uno\n")
    fake_transit.aceptar_token("tok-uno")
    proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
    await proveedor.wrap(DEK)
    assert fake_transit.calls[-1].headers["x-vault-token"] == "tok-uno"
    # el operador reemite el token (S5-D11) y el archivo cambia de mtime
    _con_token(ruta, "tok-dos\n")
    futuro = ruta.stat().st_mtime + 30
    os.utime(ruta, (futuro, futuro))
    fake_transit.aceptar_token("tok-dos")
    await proveedor.wrap(DEK)
    assert fake_transit.calls[-1].headers["x-vault-token"] == "tok-dos"


async def test_sin_cambio_de_mtime_no_se_relee(tmp_path: Path, fake_transit: FakeTransit) -> None:
    ruta = _con_token(tmp_path / "token", "tok-uno\n")
    fijo = ruta.stat().st_mtime_ns
    fake_transit.aceptar_token("tok-uno")
    proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
    await proveedor.wrap(DEK)
    ruta.write_text("tok-dos\n", encoding="utf-8")
    os.utime(ruta, ns=(fijo, fijo))  # exactamente lo que devolvía stat(): misma huella
    await proveedor.wrap(DEK)
    assert fake_transit.calls[-1].headers["x-vault-token"] == "tok-uno"


async def test_token_reemitido_con_mismo_tamano_y_mtime_se_relee_por_el_inodo(
    tmp_path: Path, fake_transit: FakeTransit
) -> None:
    """L1: `rename` atómico del archivo nuevo en el mismo segundo y con el mismo tamaño."""
    ruta = _con_token(tmp_path / "token", "tok-uno\n")
    fijo = ruta.stat().st_mtime_ns
    fake_transit.aceptar_token("tok-uno")
    proveedor = OpenBaoProvider(ADDR_FAKE, ruta, timeout_s=1, client=fake_transit.cliente())
    await proveedor.wrap(DEK)
    nuevo = _con_token(tmp_path / "token.nuevo", "tok-dos\n")
    os.utime(nuevo, ns=(fijo, fijo))
    os.replace(nuevo, ruta)
    fake_transit.aceptar_token("tok-dos")
    await proveedor.wrap(DEK)
    assert fake_transit.calls[-1].headers["x-vault-token"] == "tok-dos"


# Dirección: https obligatorio fuera de los hosts internos (S5-D124) ----------------------------


@pytest.mark.parametrize(
    "addr",
    [
        "http://evil.example:8200",
        "http://10.0.0.5:8200",
        "http://openbao.evil.com:8200",
        "ftp://openbao:8200",
        "openbao:8200",
    ],
)
def test_addr_no_permitida_se_rechaza(addr: str, token_file: Path) -> None:
    with pytest.raises(CryptoError):
        OpenBaoProvider(addr, token_file, timeout_s=1)


@pytest.mark.parametrize(
    "addr",
    [
        "http://openbao:8200",
        "http://localhost:8200",
        "http://127.0.0.1:8200",
        "https://bao.example.com",
        "https://10.0.0.5:8200",
    ],
)
def test_addr_permitida_se_acepta(addr: str, token_file: Path) -> None:
    assert OpenBaoProvider(addr, token_file, timeout_s=1).name == "openbao"


# Política de red del cliente (S5-D17) ----------------------------------------------------------


async def test_cliente_sin_redirecciones_ni_proxies_del_entorno(
    monkeypatch: pytest.MonkeyPatch, fake_transit: FakeTransit, token_file: Path
) -> None:
    recibidos: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "AsyncClient", fake_transit.fabrica_de_cliente(recibidos))
    proveedor = OpenBaoProvider(ADDR_FAKE, token_file, timeout_s=2.5)
    await proveedor.status()
    assert recibidos, "el proveedor debe crear su httpx.AsyncClient cuando no se inyecta"
    assert recibidos[0]["follow_redirects"] is False
    assert recibidos[0]["trust_env"] is False
    assert recibidos[0]["timeout"] == httpx.Timeout(2.5)


# Renovación del token (S5-D11, S5-D108) --------------------------------------------------------


async def test_maybe_renew_cada_12_horas_con_renew_self(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    reloj = FrozenClock(datetime(2026, 11, 4, 12, 0, tzinfo=UTC))

    def renovaciones() -> int:
        return len(fake_transit.llamadas("/auth/token/renew-self"))

    await openbao_fake.maybe_renew(reloj.now_utc())
    base = renovaciones()
    reloj.advance(hours=11, minutes=59)
    await openbao_fake.maybe_renew(reloj.now_utc())
    assert renovaciones() == base  # aún no pasaron 12 h
    reloj.advance(minutes=1)
    await openbao_fake.maybe_renew(reloj.now_utc())
    assert renovaciones() == base + 1  # 12 h exactas desde la primera
    reloj.advance(hours=11)
    await openbao_fake.maybe_renew(reloj.now_utc())
    assert renovaciones() == base + 1
    reloj.advance(hours=1)
    await openbao_fake.maybe_renew(reloj.now_utc())
    assert renovaciones() == base + 2
    renovacion = fake_transit.llamadas("/auth/token/renew-self")[0]
    assert renovacion.method == "POST" and renovacion.headers["x-vault-token"] == TOKEN_FAKE


async def test_renew_llama_renew_self_y_nunca_lookup_self(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    """Los tokens son huérfanos y `-no-default-policy`: `lookup-self` daría 403 (S5-D108)."""
    await openbao_fake.renew()
    await openbao_fake.maybe_renew(datetime(2026, 11, 4, tzinfo=UTC))
    await openbao_fake.status()
    await openbao_fake.wrap(DEK)
    assert len(fake_transit.llamadas("renew-self")) >= 1
    assert fake_transit.llamadas("lookup-self") == []


# status ----------------------------------------------------------------------------------------


async def test_status_ok(openbao_fake: OpenBaoProvider) -> None:
    assert await openbao_fake.status() == "ok"


async def test_status_sellado_y_sin_inicializar_son_sealed(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.seal()
    assert await openbao_fake.status() == "sealed"
    fake_transit.unseal()
    assert await openbao_fake.status() == "ok"
    fake_transit.uninitialize()
    assert await openbao_fake.status() == "sealed"


async def test_status_timeout_conexion_y_403_son_unreachable(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.revoke_token()
    assert await openbao_fake.status() == "unreachable"  # 403 en Transit
    fake_transit.aceptar_token(TOKEN_FAKE)
    assert await openbao_fake.status() == "ok"
    fake_transit.timeout_en("seal-status")
    assert await openbao_fake.status() == "unreachable"


async def test_status_con_el_servidor_caido_es_unreachable(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.conexion_rota_en("/v1/")
    assert await openbao_fake.status() == "unreachable"


async def test_status_nunca_lanza_y_no_usa_lookup_self(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    fake_transit.responder("/v1/", 500, ["boom"])
    resultado = await openbao_fake.status()
    assert resultado in ("sealed", "unreachable")
    assert fake_transit.llamadas("lookup-self") == []


# status sin sondeo con token en cada llamada (S5-D163, M1) --------------------------------------


async def test_cien_status_hacen_a_lo_sumo_una_renovacion(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    for _ in range(100):
        assert await openbao_fake.status() == "ok"
    assert len(fake_transit.llamadas("renew-self")) <= 1
    assert len(fake_transit.llamadas("seal-status")) == 100


async def test_status_tras_un_unwrap_exitoso_no_usa_el_token(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    await openbao_fake.unwrap(await openbao_fake.wrap(DEK))
    fake_transit.calls.clear()
    assert await openbao_fake.status() == "ok"
    assert [c.path for c in fake_transit.calls] == ["/v1/sys/seal-status"]
    assert all("x-vault-token" not in c.headers for c in fake_transit.calls)


async def test_status_tras_12_horas_sin_actividad_renueva_una_vez(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    from app.core.clock import reset_clock, set_clock

    reloj = FrozenClock(datetime(2026, 11, 4, 12, 0, tzinfo=UTC))
    token = set_clock(reloj)
    try:
        await openbao_fake.unwrap(await openbao_fake.wrap(DEK))
        reloj.advance(hours=12)
        assert await openbao_fake.status() == "ok"
        assert await openbao_fake.status() == "ok"
        assert len(fake_transit.llamadas("renew-self")) == 1
    finally:
        reset_clock(token)


async def test_status_tras_un_error_reciente_vuelve_a_sondear(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    await openbao_fake.unwrap(await openbao_fake.wrap(DEK))
    fake_transit.revoke_token()
    await _error_de(openbao_fake.wrap(DEK))
    assert await openbao_fake.status() == "unreachable"
