"""`crypto` en `/health` (S5-B3, US-136; S5-D13, S5-D70, M-3, L-7). Rojo B3.

- `health_state`: tabla completa de las doce combinaciones de (proveedor, keyring, umbral);
- `local` con keyring cargado -> 200 y `crypto: ok`; sellado o inalcanzable -> 503 `degraded`;
- caché de 5 s (medida con `FrozenClock`): una sola llamada a `status()` por ventana;
- `/health` nunca llama `recovery.try_load` ni abre llaves (D70, M-4): solo lee el estado del
  proceso y `status()` del proveedor;
- M-3: con `ENV=production` y un umbral de desello (`t`) menor que 2, `crypto` es `unreachable` y
  sale una línea CRITICAL sin URL; con `dev` o con `t >= 2` no;
- L-7: el cuerpo trae solo `status`, `db`, `version`, `backup`, `migrations` y `crypto`; nada del
  `seal-status` de OpenBao (versión, clúster).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.crypto import recovery
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.openbao_provider import OpenBaoProvider
from app.core.crypto.provider import ProviderStatus, configure_provider
from app.core.crypto.state import CryptoState, health_state
from app.main import create_app
from tests.conftest import T0
from tests.core._cripto_apoyo import proveedor_ctl
from tests.factories.fake_provider import ProveedorControlable
from tests.factories.fake_transit import ADDR_FAKE, TOKEN_FAKE, FakeTransit

__all__ = ["proveedor_ctl"]

CLAVES_DEL_CUERPO = {"status", "db", "version", "backup", "migrations", "crypto"}

TABLA_DE_VERDAD: list[tuple[ProviderStatus, bool, bool, CryptoState]] = [
    # (estado del proveedor, keyring cargado, umbral válido) -> estado público
    ("ok", True, True, "ok"),
    ("ok", False, True, "sealed"),
    ("sealed", True, True, "sealed"),
    ("sealed", False, True, "sealed"),
    ("unreachable", True, True, "unreachable"),
    ("unreachable", False, True, "unreachable"),
    ("ok", True, False, "unreachable"),
    ("ok", False, False, "unreachable"),
    ("sealed", True, False, "unreachable"),
    ("sealed", False, False, "unreachable"),
    ("unreachable", True, False, "unreachable"),
    ("unreachable", False, False, "unreachable"),
]


@pytest.mark.parametrize(("proveedor", "keyring", "umbral", "esperado"), TABLA_DE_VERDAD)
def test_health_state_tabla_completa(
    proveedor: ProviderStatus, keyring: bool, umbral: bool, esperado: CryptoState
) -> None:
    assert health_state(proveedor, keyring, threshold_ok=umbral) == esperado


def test_health_state_cubre_las_doce_combinaciones_sin_repetir() -> None:
    combinaciones = {(p, k, u) for p, k, u, _ in TABLA_DE_VERDAD}
    assert len(combinaciones) == len(TABLA_DE_VERDAD) == 3 * 2 * 2


@pytest.fixture(autouse=True)
async def _salud_limpia() -> AsyncIterator[None]:
    health.clear_health_cache()
    yield
    health.clear_health_cache()


async def test_con_local_y_keyring_cargado_responde_200_y_crypto_ok(app_http: AsyncClient) -> None:
    r = await app_http.get("/health")
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["crypto"]) == ("ok", "ok")


async def test_health_y_api_v1_health_son_iguales_con_crypto(app_http: AsyncClient) -> None:
    r1, r2 = await app_http.get("/health"), await app_http.get("/api/v1/health")
    assert r1.status_code == r2.status_code
    assert r1.json() == r2.json() and r1.json()["crypto"] == "ok"


async def test_con_el_proveedor_sellado_responde_503_degraded_y_crypto_sealed(
    app_http: AsyncClient, proveedor_ctl: ProveedorControlable
) -> None:
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    r = await app_http.get("/health")
    assert r.status_code == 503, r.text
    assert (r.json()["status"], r.json()["db"], r.json()["crypto"]) == ("degraded", "ok", "sealed")


async def test_sellado_con_el_keyring_cargado_sigue_diciendo_sealed(
    app_http: AsyncClient, proveedor_ctl: ProveedorControlable
) -> None:
    """D14: las lecturas siguen (DEK en memoria), pero `/health` refleja el sello."""
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    r = await app_http.get("/health")
    assert r.status_code == 503 and r.json()["crypto"] == "sealed"


async def test_proveedor_inalcanzable_responde_503_con_crypto_unreachable(
    app_http: AsyncClient, proveedor_ctl: ProveedorControlable
) -> None:
    proveedor_ctl.estado = "unreachable"
    configure_provider(proveedor_ctl)
    r = await app_http.get("/health")
    assert r.status_code == 503, r.text
    assert (r.json()["status"], r.json()["crypto"]) == ("degraded", "unreachable")


async def test_sin_keyring_aunque_el_proveedor_responda_no_es_ok(app_http: AsyncClient) -> None:
    configure_keyring(None)
    r = await app_http.get("/health")
    assert r.status_code == 503, r.text
    assert r.json()["crypto"] != "ok" and r.json()["status"] == "degraded"


async def test_la_cache_de_5_segundos_llama_una_sola_vez_a_status(
    app_http: AsyncClient, proveedor_ctl: ProveedorControlable, reloj: FrozenClock
) -> None:
    configure_provider(proveedor_ctl)
    primera = await app_http.get("/health")
    assert primera.json()["crypto"] == "ok"
    proveedor_ctl.estado = "sealed"
    reloj.set(T0 + timedelta(seconds=4))
    dentro = await app_http.get("/health")
    assert dentro.json()["crypto"] == "ok"  # dentro de la ventana de 5 s
    assert proveedor_ctl.status_calls == 1
    reloj.set(T0 + timedelta(seconds=6))
    vencida = await app_http.get("/health")
    assert (vencida.status_code, vencida.json()["crypto"]) == (503, "sealed")
    assert proveedor_ctl.status_calls == 2


async def test_health_nunca_llama_try_load_ni_abre_llaves(
    app_http: AsyncClient, proveedor_ctl: ProveedorControlable, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []

    async def espia(*args: object, **kwargs: object) -> CryptoState:
        llamadas.append("try_load")
        return "ok"

    monkeypatch.setattr(recovery, "try_load", espia)
    configure_keyring(None)
    configure_provider(proveedor_ctl)
    for _ in range(3):
        health.clear_health_cache()
        r = await app_http.get("/health")
        assert r.json()["crypto"] == "sealed"  # el keyring falta aunque el proveedor responde
    assert llamadas == []
    assert proveedor_ctl.unwrap_calls == 0 and proveedor_ctl.wrap_calls == 0


# M-3: la guarda del umbral de desello en ejecución ---------------------------------------------


@pytest.fixture
def token_de_openbao(tmp_path: Path) -> Path:
    ruta = tmp_path / "token"
    ruta.write_text(TOKEN_FAKE + "\n", encoding="utf-8")
    ruta.chmod(0o600)
    return ruta


def _openbao(fake: FakeTransit, token: Path) -> OpenBaoProvider:
    return OpenBaoProvider(ADDR_FAKE, token, timeout_s=2.0, client=fake.cliente())


def _app_con_env(api_prueba: FastAPI, settings: Settings, env: str) -> FastAPI:
    """Otra `create_app` con `ENV=env` (el check de `crypto` lee la guarda de sus settings)."""
    app = create_app(settings.model_copy(update={"ENV": env}), run_migrations_on_startup=False)
    app.dependency_overrides.update(api_prueba.dependency_overrides)
    return app


async def _health_con(app: FastAPI, fake: FakeTransit, token: Path) -> tuple[int, dict[str, str]]:
    configure_provider(_openbao(fake, token))
    health.clear_health_cache()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        r = await cliente.get("/health")
    return r.status_code, r.json()


async def test_en_produccion_un_umbral_menor_que_2_es_unreachable_con_una_linea_critica(
    api_prueba: FastAPI,
    settings_prueba: Settings,
    token_de_openbao: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app_con_env(api_prueba, settings_prueba, "production")
    caplog.set_level(logging.DEBUG)
    codigo, cuerpo = await _health_con(app, FakeTransit(umbral=1), token_de_openbao)
    assert codigo == 503 and cuerpo["crypto"] == "unreachable", cuerpo
    criticas = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(criticas) >= 1, "falta la línea crítica de M-3"
    for registro in criticas:
        texto = registro.getMessage()
        assert "http" not in texto and ADDR_FAKE.split("//")[1] not in texto
        assert TOKEN_FAKE not in texto


async def test_en_produccion_un_umbral_de_2_o_mas_no_dispara_la_guarda(
    api_prueba: FastAPI,
    settings_prueba: Settings,
    token_de_openbao: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app_con_env(api_prueba, settings_prueba, "production")
    caplog.set_level(logging.DEBUG)
    codigo, cuerpo = await _health_con(app, FakeTransit(umbral=2), token_de_openbao)
    assert codigo == 200 and cuerpo["crypto"] == "ok", cuerpo
    assert [r for r in caplog.records if r.levelno == logging.CRITICAL] == []


async def test_fuera_de_produccion_un_umbral_de_1_no_dispara_la_guarda(
    api_prueba: FastAPI,
    settings_prueba: Settings,
    token_de_openbao: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app_con_env(api_prueba, settings_prueba, "dev")
    caplog.set_level(logging.DEBUG)
    codigo, cuerpo = await _health_con(app, FakeTransit(umbral=1), token_de_openbao)
    assert codigo == 200 and cuerpo["crypto"] == "ok", cuerpo
    assert [r for r in caplog.records if r.levelno == logging.CRITICAL] == []


# L-7: el cuerpo no cuenta nada del clúster -------------------------------------------------------


@pytest.mark.parametrize("sellado", [False, True])
async def test_el_cuerpo_no_trae_version_ni_cluster_de_openbao(
    api_prueba: FastAPI, settings_prueba: Settings, token_de_openbao: Path, sellado: bool
) -> None:
    app = _app_con_env(api_prueba, settings_prueba, "dev")
    fake = FakeTransit()
    if sellado:
        fake.seal()
    configure_provider(_openbao(fake, token_de_openbao))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        r = await cliente.get("/health")
    assert set(r.json()) == CLAVES_DEL_CUERPO, r.json()
    assert r.json()["crypto"] == ("sealed" if sellado else "ok")
    for ajeno in ("2.4.1-fake", "apex-cluster-fake", "11111111-2222", "openbao", "vault", "raft"):
        assert ajeno not in r.text.lower(), ajeno
