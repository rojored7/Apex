"""`sign-audit [--as <correo>]` (S6-A2, US-141; S6-D8, D80, M-2d). Rojo A2.

Por la CLI real (`CliRunner`) con commit real. Contrato (stdout y stderr juntos en `.output`):
- 0 al firmar y 0 sin novedades (segunda corrida: sigue habiendo una sola fila);
- 1 si la firma falla (el proveedor falla o la firma no verifica); el texto nunca trae lo que dijo
  el proveedor (URL, token, mensaje);
- 2 con el custodio sellado, con el texto «desellar OpenBao»;
- `ENV=production` sin `--as`: 2; con `--as` de un admin activo firma;
- comparte el candado `4_270_004` con el job: mientras otro lo tiene, el comando espera y firma
  una sola vez.
El comando llega al bus por `cli_base.crypto_runtime` y a la cadena por `core.audit_sign`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from click.testing import Result
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli import app
from app.core.audit_sign import AUDIT_SIGN_LOCK_KEY
from app.core.config import Settings
from tests.cli._apoyo import correr
from tests.cli._apoyo_firma import Fabrica, admin, con_proveedor, firma_lista
from tests.core._cripto_apoyo import proveedor_ctl
from tests.factories.fake_provider import ProveedorControlable
from tests.factories.firma_real import cadena, candado_libre, firmas

__all__ = ["admin", "firma_lista", "proveedor_ctl"]

pytestmark = pytest.mark.usefixtures("reloj")
SELLADO = "desellar OpenBao"
SECRETO_DEL_PROVEEDOR = "https://openbao.interno:8200 token=s.NoDebeSalir"


def _firmar(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, *args: str, env: Any = "dev"
) -> Result:
    return correr(app, ["sign-audit", *args], env, base=settings, monkeypatch=monkeypatch)


async def test_firma_la_cadena_y_sale_0_sin_imprimir_firma_ni_hash(
    settings_prueba: Settings, firma_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ultimo = await cadena(firma_lista, 5)

    resultado = _firmar(settings_prueba, monkeypatch)

    (fila,) = await firmas(firma_lista)
    assert resultado.exit_code == 0, resultado.output
    assert fila["through_seq"] == ultimo
    assert "apx1." not in resultado.output and fila["hash"] not in resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)


async def test_sin_novedades_sale_0_y_no_agrega_otra_fila(
    settings_prueba: Settings, firma_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    await cadena(firma_lista, 3)
    _firmar(settings_prueba, monkeypatch)

    segunda = _firmar(settings_prueba, monkeypatch)

    assert segunda.exit_code == 0, segunda.output
    assert len(await firmas(firma_lista)) == 1


async def test_si_la_firma_falla_sale_1_sin_texto_del_proveedor_y_sin_fila(
    settings_prueba: Settings,
    firma_lista: Fabrica,
    proveedor_ctl: ProveedorControlable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def explota(key_ref: str, data: bytes) -> bytes:
        raise RuntimeError(SECRETO_DEL_PROVEEDOR)

    monkeypatch.setattr(proveedor_ctl, "sign", explota)
    con_proveedor(monkeypatch, proveedor_ctl)
    await cadena(firma_lista, 3)

    resultado = _firmar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 1, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert "sign-audit:" in resultado.output
    assert "NoDebeSalir" not in resultado.output and "openbao.interno" not in resultado.output
    assert await firmas(firma_lista) == []


async def test_una_firma_que_no_verifica_sale_1_y_no_deja_fila(
    settings_prueba: Settings,
    firma_lista: Fabrica,
    proveedor_ctl: ProveedorControlable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def mala(key_ref: str, data: bytes) -> bytes:
        return bytes(64)

    monkeypatch.setattr(proveedor_ctl, "sign", mala)
    con_proveedor(monkeypatch, proveedor_ctl)
    await cadena(firma_lista, 3)

    resultado = _firmar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 1, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert "sign-audit:" in resultado.output
    assert await firmas(firma_lista) == []


async def test_con_el_custodio_sellado_sale_2_y_dice_desellar_openbao(
    settings_prueba: Settings,
    firma_lista: Fabrica,
    proveedor_ctl: ProveedorControlable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    con_proveedor(monkeypatch, proveedor_ctl)
    await cadena(firma_lista, 3)

    resultado = _firmar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 2, resultado.output
    assert SELLADO in resultado.output
    assert await firmas(firma_lista) == []


async def test_en_produccion_sin_as_sale_2(
    settings_prueba: Settings, firma_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    await cadena(firma_lista, 3)

    resultado = _firmar(settings_prueba, monkeypatch, env="production")

    assert resultado.exit_code == 2
    assert "--as <correo> es obligatorio con ENV=production" in resultado.output
    assert await firmas(firma_lista) == []


async def test_en_produccion_con_as_de_un_admin_firma(
    settings_prueba: Settings, firma_lista: Fabrica, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await cadena(firma_lista, 3)

    resultado = _firmar(settings_prueba, monkeypatch, "--as", admin.email, env="production")

    assert resultado.exit_code == 0, resultado.output
    (fila,) = await firmas(firma_lista)
    assert fila["created_by"] == admin.id


async def test_con_as_de_alguien_que_no_es_admin_sale_2(
    settings_prueba: Settings, firma_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _firmar(settings_prueba, monkeypatch, "--as", "nadie@test.apex")

    assert resultado.exit_code == 2 and "admin activo" in resultado.output


async def test_comparte_el_candado_con_el_job_y_firma_una_sola_vez(
    settings_prueba: Settings,
    firma_lista: Fabrica,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otro firmante tiene el candado 4_270_004: el comando espera y, al soltarlo, firma una vez."""
    await cadena(firma_lista, 3)
    async with engine.connect() as ajena:
        await ajena.execute(text("SELECT pg_advisory_lock(:k)"), {"k": AUDIT_SIGN_LOCK_KEY})
        tarea = asyncio.create_task(asyncio.to_thread(_firmar, settings_prueba, monkeypatch))
        await asyncio.sleep(0.4)
        esperando = not tarea.done() and await firmas(firma_lista) == []
        await ajena.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": AUDIT_SIGN_LOCK_KEY})
    resultado = await tarea

    assert esperando, "el comando no esperó el candado 4_270_004"
    assert resultado.exit_code == 0, resultado.output
    assert len(await firmas(firma_lista)) == 1
    assert await candado_libre(engine)


async def test_un_proveedor_colgado_vence_sale_1_y_libera_el_candado(
    settings_prueba: Settings,
    firma_lista: Fabrica,
    engine: AsyncEngine,
    proveedor_ctl: ProveedorControlable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L1 (revisión de seguridad): la firma manual tiene tope; un proveedor colgado no retiene
    el candado `4_270_004`."""
    from app.cli_ops import sign_audit as cli_sign_audit

    async def colgado(key_ref: str, data: bytes) -> bytes:
        await asyncio.sleep(30)
        return b""

    monkeypatch.setattr(proveedor_ctl, "sign", colgado)
    monkeypatch.setattr(cli_sign_audit, "SIGN_TIMEOUT_S", 1.0)
    con_proveedor(monkeypatch, proveedor_ctl)
    await cadena(firma_lista, 3)

    resultado = await asyncio.wait_for(
        asyncio.to_thread(_firmar, settings_prueba, monkeypatch), timeout=20
    )

    assert resultado.exit_code == 1, resultado.output
    assert "sign-audit:" in resultado.output
    assert await firmas(firma_lista) == []
    assert await candado_libre(engine)
