"""`init-keys --data-class <clase> [--as]` (S6-A2, US-140/141; S6-D72, D80, D81, D99). Rojo A2.

Crea (o completa) la fila `sign` de la clase con la referencia y la clave pública del proveedor
vigente; no toca archivos (`--dir` no interviene). Contrato (stdout y stderr juntos en `.output`):
- `audit.signature`: fila `sign` `active`, versión 1, `algorithm = Ed25519`, `wrapped_material` =
  `local:sign-ed25519` (local) o `apex-sign-audit` (OpenBao) y `public_key` = la del proveedor;
- idempotente: la segunda corrida dice «ya existe» y sale 0 sin escribir;
- fila sin `public_key` (S6-D99, base de desarrollo): la completa una vez, auditada (`update`), y
  una clave pública ya puesta no se cambia;
- clase desconocida (o que ni se firma ni es de adjuntos): 2 `unknown_data_class`;
- `attachment.sensitive` (S6-C1, S6-D72): crea la fila `encrypt` `A256GCM` activa, versión 1, con la
  DEK envuelta por el proveedor (sin clave pública); idempotente («ya existe»), auditada sin
  material y nunca deja dos filas activas;
- auditado: `audit_log` `insert` sobre `crypto.crypto_keys` sin material; sin `crypto_ops` de la
  clase (crear la fila no firma ni cifra nada);
- `ENV=production` sin `--as`: 2.
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import Result
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from tests.cli._apoyo import correr
from tests.cli._apoyo_custodia import (
    custodia,
    settings_custodia,
)
from tests.cli._apoyo_firma import Fabrica, admin, llaves_sign, sin_fila_sign
from tests.crypto._migracion import Entorno
from tests.factories.triggers import disable_user_sql, rearm_always_sql

__all__ = ["admin", "custodia", "settings_custodia", "sin_fila_sign"]

pytestmark = pytest.mark.usefixtures("reloj")
CK = "ck_crypto_keys_sign_iff_public_key"
OTRA_PUBLICA = "A" * 43 + "="  # 32 bytes en base64; no es la del proveedor


def _crear(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, *args: str, env: Any = "dev"
) -> Result:
    return correr(
        app, ["init-keys", "--data-class", *args], env, base=settings, monkeypatch=monkeypatch
    )


async def _auditoria(fabrica: Fabrica, accion: str) -> list[AuditEntry]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(
                AuditEntry.action == accion, AuditEntry.table_name == "crypto.crypto_keys"
            )
        )
        return list(filas)


async def _ops_de_la_clase(fabrica: Fabrica) -> int:
    async with fabrica() as sesion:
        return int(
            await sesion.scalar(
                text("SELECT count(*) FROM crypto.crypto_ops WHERE data_class = 'audit.signature'")
            )
            or 0
        )


# Creación ----------------------------------------------------------------------------------------


async def test_crea_la_fila_sign_con_la_referencia_local_y_la_publica_del_proveedor(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    proveedor_local: LocalFileProvider,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    (llave,) = await llaves_sign(sin_fila_sign)
    assert (llave.data_class, llave.version, llave.state) == ("audit.signature", 1, "active")
    assert (llave.algorithm, llave.provider) == ("Ed25519", "local")
    assert bytes(llave.wrapped_material) == b"local:sign-ed25519"
    assert llave.public_key == await proveedor_local.sign_public_key()
    assert "local" in resultado.output and "Ed25519" in resultado.output


async def test_con_openbao_la_referencia_es_apex_sign_audit_y_la_publica_sale_de_key_info(
    settings_custodia: Settings,
    custodia: Entorno,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ajustes = settings_custodia.model_copy(update={"CRYPTO_PROVIDER": "openbao"})

    resultado = _crear(ajustes, monkeypatch, "audit.signature", "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    (llave,) = await llaves_sign(custodia.fabrica)
    assert (llave.provider, llave.algorithm) == ("openbao", "Ed25519")
    assert bytes(llave.wrapped_material) == b"apex-sign-audit"
    assert llave.public_key == await custodia.openbao.sign_public_key()
    assert "openbao" in resultado.output


# Idempotencia y auditoría ------------------------------------------------------------------------


async def test_la_segunda_corrida_dice_ya_existe_y_no_escribe(
    settings_prueba: Settings, sin_fila_sign: Fabrica, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)
    antes = len(await _auditoria(sin_fila_sign, "insert")) + len(
        await _auditoria(sin_fila_sign, "update")
    )

    segunda = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)

    assert segunda.exit_code == 0, segunda.output
    assert "ya existe" in segunda.output
    assert len(await llaves_sign(sin_fila_sign)) == 1
    despues = len(await _auditoria(sin_fila_sign, "insert")) + len(
        await _auditoria(sin_fila_sign, "update")
    )
    assert despues == antes


async def test_audita_un_insert_sobre_crypto_keys_sin_material_y_sin_crypto_ops(
    settings_prueba: Settings, sin_fila_sign: Fabrica, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    previos = {f.id for f in await _auditoria(sin_fila_sign, "insert")}

    resultado = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    (nueva,) = [f for f in await _auditoria(sin_fila_sign, "insert") if f.id not in previos]
    (llave,) = await llaves_sign(sin_fila_sign)
    assert nueva.user_id == admin.id and nueva.record_id == llave.id
    assert "wrapped_material" not in (nueva.after or {})
    assert await _ops_de_la_clase(sin_fila_sign) == 0


# Fila preexistente sin clave pública (S6-D99) ---


async def _fila_sin_publica(engine: AsyncEngine, fabrica: Fabrica, publica: str | None) -> None:
    """Reproduce la base de desarrollo: una fila `sign` anterior al CHECK, sin `public_key`."""
    async with engine.begin() as conexion:
        await conexion.execute(text(f"ALTER TABLE crypto.crypto_keys DROP CONSTRAINT {CK}"))
        await conexion.execute(
            text(
                "INSERT INTO crypto.crypto_keys (id, purpose, data_class, algorithm, provider, "
                "version, state, wrapped_material, public_key, created_by, created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'sign', 'audit.signature', 'Ed25519', 'local', 1, "
                "'active', convert_to('local:sign-ed25519', 'UTF8'), :pk, "
                "'00000000-0000-0000-0000-000000000001', now(), now())"
            ),
            {"pk": publica},
        )
        await conexion.execute(
            text(
                f"ALTER TABLE crypto.crypto_keys ADD CONSTRAINT {CK} "
                "CHECK ((purpose = 'sign') = (public_key IS NOT NULL)) NOT VALID"
            )
        )


async def test_completa_la_clave_publica_de_una_fila_sign_huerfana_y_lo_audita(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    proveedor_local: LocalFileProvider,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fila_sin_publica(engine, sin_fila_sign, None)
    (huerfana,) = await llaves_sign(sin_fila_sign)
    assert huerfana.public_key is None

    resultado = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    (llave,) = await llaves_sign(sin_fila_sign)
    assert llave.id == huerfana.id
    assert llave.public_key == await proveedor_local.sign_public_key()
    (cambio,) = [f for f in await _auditoria(sin_fila_sign, "update") if f.record_id == llave.id]
    assert cambio.user_id == admin.id and "wrapped_material" not in (cambio.after or {})
    segunda = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)
    assert segunda.exit_code == 0 and "ya existe" in segunda.output


async def test_una_clave_publica_ya_puesta_no_se_cambia(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fila_sin_publica(engine, sin_fila_sign, OTRA_PUBLICA)

    resultado = _crear(settings_prueba, monkeypatch, "audit.signature", "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert "ya existe" in resultado.output
    (llave,) = await llaves_sign(sin_fila_sign)
    assert llave.public_key == OTRA_PUBLICA
    assert await _auditoria(sin_fila_sign, "update") == []


# Rechazos ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("clase", ["member.x", "member.document"])
async def test_una_clase_desconocida_o_de_columnas_sale_2_con_unknown_data_class_y_no_crea_filas(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
    clase: str,
) -> None:
    resultado = _crear(settings_prueba, monkeypatch, clase, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert "unknown_data_class" in resultado.output
    assert await llaves_sign(sin_fila_sign) == []


async def test_en_produccion_sin_as_sale_2(
    settings_prueba: Settings, sin_fila_sign: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _crear(settings_prueba, monkeypatch, "audit.signature", env="production")

    assert resultado.exit_code == 2
    assert "--as <correo> es obligatorio con ENV=production" in resultado.output
    assert await llaves_sign(sin_fila_sign) == []


async def test_sin_as_en_dev_atribuye_al_usuario_tecnico(
    settings_prueba: Settings, sin_fila_sign: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _crear(settings_prueba, monkeypatch, "audit.signature")

    assert resultado.exit_code == 0, resultado.output
    (llave,) = await llaves_sign(sin_fila_sign)
    assert str(llave.created_by) == "00000000-0000-0000-0000-000000000001"
    assert isinstance(llave, CryptoKey)


# attachment.sensitive (S6-C1: el caso de A2 pasa a verde) ----------------------------------------

ADJUNTOS = "attachment.sensitive"


async def _filas_de(fabrica: Fabrica, clase: str) -> list[CryptoKey]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoKey).where(CryptoKey.data_class == clase).order_by(CryptoKey.version)
        )
        return list(filas)


async def _quitar_clase(engine: AsyncEngine, clase: str) -> None:
    """Deja la base sin la llave de adjuntos (como una instalación anterior a C1)."""
    async with engine.begin() as conexion:
        await conexion.execute(text(disable_user_sql("crypto.crypto_keys")))
        await conexion.execute(
            text("DELETE FROM crypto.crypto_keys WHERE data_class = :c"), {"c": clase}
        )
        await conexion.execute(text(rearm_always_sql("crypto.crypto_keys")))


async def test_attachment_sensitive_crea_la_fila_encrypt_a256gcm_envuelta_y_sin_clave_publica(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _quitar_clase(engine, ADJUNTOS)
    assert await _filas_de(sin_fila_sign, ADJUNTOS) == []

    resultado = _crear(settings_prueba, monkeypatch, ADJUNTOS, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    (llave,) = await _filas_de(sin_fila_sign, ADJUNTOS)
    assert (llave.purpose, llave.algorithm, llave.state, llave.version) == (
        "encrypt",
        "A256GCM",
        "active",
        1,
    )
    assert llave.provider == "local" and llave.public_key is None
    assert len(bytes(llave.wrapped_material)) > 32  # la DEK envuelta, no una referencia
    assert not bytes(llave.wrapped_material).startswith(b"local:")
    assert ADJUNTOS in resultado.output and "A256GCM" in resultado.output


async def test_attachment_sensitive_segunda_corrida_dice_ya_existe_y_no_agrega_otra_fila(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _quitar_clase(engine, ADJUNTOS)
    _crear(settings_prueba, monkeypatch, ADJUNTOS, "--as", admin.email)
    (primera,) = await _filas_de(sin_fila_sign, ADJUNTOS)

    segunda = _crear(settings_prueba, monkeypatch, ADJUNTOS, "--as", admin.email)

    assert segunda.exit_code == 0, segunda.output
    assert "ya existe" in segunda.output
    (misma,) = await _filas_de(sin_fila_sign, ADJUNTOS)
    assert misma.id == primera.id


async def test_attachment_sensitive_con_la_fila_ya_creada_por_ensure_keys_no_hay_dos(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En desarrollo `ensure_keys` la crea al arrancar (el registro ya la nombra): el comando lo
    reconoce y sale 0 sin duplicar."""
    assert len(await _filas_de(sin_fila_sign, ADJUNTOS)) == 1

    resultado = _crear(settings_prueba, monkeypatch, ADJUNTOS, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert "ya existe" in resultado.output
    assert len(await _filas_de(sin_fila_sign, ADJUNTOS)) == 1


async def test_attachment_sensitive_se_audita_sin_material_y_con_el_actor(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _quitar_clase(engine, ADJUNTOS)
    previos = {f.id for f in await _auditoria(sin_fila_sign, "insert")}

    resultado = _crear(settings_prueba, monkeypatch, ADJUNTOS, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    (llave,) = await _filas_de(sin_fila_sign, ADJUNTOS)
    (nueva,) = [f for f in await _auditoria(sin_fila_sign, "insert") if f.id not in previos]
    assert nueva.user_id == admin.id and nueva.record_id == llave.id
    assert "wrapped_material" not in (nueva.after or {})
    assert bytes(llave.wrapped_material).hex() not in str(nueva.after)


async def test_attachment_sensitive_en_produccion_sin_as_sale_2_y_no_crea_filas(
    settings_prueba: Settings,
    sin_fila_sign: Fabrica,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _quitar_clase(engine, ADJUNTOS)

    resultado = _crear(settings_prueba, monkeypatch, ADJUNTOS, env="production")

    assert resultado.exit_code == 2
    assert "--as <correo> es obligatorio con ENV=production" in resultado.output
    assert await _filas_de(sin_fila_sign, ADJUNTOS) == []
