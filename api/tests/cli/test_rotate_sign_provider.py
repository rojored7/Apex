"""`rotate-key audit.signature --provider <local|openbao> --reason … --as …` (S6-A2, D69, D81).

Cambiar la firma de proveedor es una llave NUEVA, no un recifrado:
- con una fila `sign` v1 `local` y dos firmas, `--provider openbao` (con `FakeTransit`) inserta la
  v2 `active` `openbao` con referencia `apex-sign-audit` y `public_key` igual a la de `key_info`,
  pasa la v1 a `decrypt_only`, no cambia ninguna fila de `audit.signatures`, deja `crypto_ops(wrap)`
  y UNA fila `update` de auditoría sin material;
- la reversa `--provider local` funciona si existe el archivo de la llave de firma local y sale 2
  si no; sin `--provider` o con el proveedor vigente: 2 `purpose_not_rotatable`; con el proveedor
  destino sin configurar: 2 nombrando `OPENBAO_TOKEN_FILE`;
- `retire-key` de la v1 mientras existan firmas con su `key_id`: 2 `signatures_reference_key`;
- `--as` obligatorio con `ENV=production`; `cli_ops/rotate_key.py` sigue bajo 260 líneas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import Result
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto.models import CryptoOp
from tests.cli._apoyo import correr
from tests.cli._apoyo_custodia import (  # noqa: F401
    SIN_MANIFIESTO,
    SIN_VERIFY,
    custodia,
    manifiesto_bueno,
    settings_custodia,
)
from tests.cli._apoyo_firma import llaves_sign
from tests.conftest import CLAVE_PRUEBA
from tests.crypto._firma_proveedor import (
    agregar_y_firmar,
    cargar_keyring,
    instantanea_firmas,
    sembrar_firmas,
)
from tests.crypto._migracion import Entorno, migracion_lista
from tests.crypto._rotacion import verify_reciente
from tests.factories.users import make_user

__all__ = ["custodia", "migracion_lista", "settings_custodia"]

MOTIVO = "cambio de proveedor de la firma"
pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


@pytest.fixture
async def admin(limpiar_demo: async_sessionmaker[AsyncSession], argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


def _rotar(
    settings: Settings,
    mp: pytest.MonkeyPatch,
    *args: str,
    env: Any = "dev",
    clase: str = "audit.signature",
) -> Result:
    return correr(app, ["rotate-key", clase, *args], env, base=settings, monkeypatch=mp)


def _a(proveedor: str, admin: Any) -> tuple[str, ...]:
    return ("--provider", proveedor, "--reason", MOTIVO, "--as", admin.email)


async def _novedades(e: Entorno, tabla: str, accion: str) -> list[AuditEntry]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(AuditEntry.action == accion, AuditEntry.table_name == tabla)
        )
        return list(filas)


async def _intacto(e: Entorno, firmas: list[tuple[Any, ...]]) -> None:
    llaves = await llaves_sign(e.fabrica)
    assert [(k.version, k.state, k.provider) for k in llaves] == [(1, "active", "local")]
    assert await instantanea_firmas(e.fabrica) == firmas


# Local -> OpenBao --------------------------------------------------------------------------------


async def test_a_openbao_crea_la_v2_activa_con_la_publica_de_key_info_y_deja_la_v1_decrypt_only(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sembrado = await sembrar_firmas(custodia)

    resultado = _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))

    assert resultado.exit_code == 0, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    v1, v2 = await llaves_sign(custodia.fabrica)
    assert (v1.version, v1.state, v1.provider) == (1, "decrypt_only", "local")
    assert (v2.version, v2.state, v2.provider, v2.algorithm) == (2, "active", "openbao", "Ed25519")
    assert bytes(v2.wrapped_material) == b"apex-sign-audit"
    assert v2.public_key == (await custodia.openbao.key_info("apex-sign-audit")).public_key
    assert v1.id == sembrado.v1
    assert resultado.output.count("\n") >= 1 and MOTIVO not in resultado.output


async def test_no_cambia_ninguna_firma_guardada(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sembrado = await sembrar_firmas(custodia)

    resultado = _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))

    assert resultado.exit_code == 0, resultado.output
    assert await instantanea_firmas(custodia.fabrica) == sembrado.firmas


async def test_deja_crypto_ops_wrap_y_una_sola_auditoria_update_sin_material(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sembrar_firmas(custodia)
    antes = len(await _novedades(custodia, "crypto.crypto_keys", "update"))

    resultado = _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))

    assert resultado.exit_code == 0, resultado.output
    async with custodia.fabrica() as sesion:
        ops = list(
            await sesion.scalars(
                select(CryptoOp).where(
                    CryptoOp.verb == "wrap", CryptoOp.data_class == "audit.signature"
                )
            )
        )
    assert len(ops) == 1 and ops[0].result == "ok"
    nuevas = (await _novedades(custodia, "crypto.crypto_keys", "update"))[antes:]
    assert len(nuevas) == 1
    assert nuevas[0].user_id == admin.id
    assert "wrapped_material" not in (nuevas[0].after or {})
    assert MOTIVO in str(nuevas[0].after)


async def test_la_siguiente_firma_usa_la_v2(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sembrar_firmas(custodia)
    _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))
    v2 = (await llaves_sign(custodia.fabrica))[-1]
    await cargar_keyring(custodia)

    salida = await agregar_y_firmar(custodia, 2)

    assert salida.kind == "signed"
    assert (await instantanea_firmas(custodia.fabrica))[-1][4] == v2.id


async def test_retire_key_de_la_v1_sale_2_mientras_existan_firmas_con_su_key_id(
    custodia: Entorno,
    settings_custodia: Settings,
    admin: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sembrado = await sembrar_firmas(custodia)
    _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))
    async with custodia.fabrica() as sesion:
        await verify_reciente(sesion, admin.id)
    manifiesto = manifiesto_bueno(tmp_path)

    resultado = correr(
        app,
        [
            "retire-key",
            str(sembrado.v1),
            "--as",
            admin.email,
            "--confirm-audit-blobs",
            "0",
            "--manifest",
            str(manifiesto),
        ],
        "dev",
        base=settings_custodia,
        monkeypatch=monkeypatch,
    )

    assert resultado.exit_code == 2 and "signatures_reference_key" in resultado.output
    assert (await llaves_sign(custodia.fabrica))[0].state == "decrypt_only"


# Reversa a local ---------------------------------------------------------------------------------


async def test_la_reversa_a_local_funciona_si_existe_el_archivo_de_la_llave_de_firma(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sembrar_firmas(custodia)
    _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))
    assert settings_custodia.CRYPTO_LOCAL_SIGNING_KEY_PATH is not None
    assert settings_custodia.CRYPTO_LOCAL_SIGNING_KEY_PATH.is_file()

    resultado = _rotar(settings_custodia, monkeypatch, *_a("local", admin))

    assert resultado.exit_code == 0, resultado.output
    v1, v2, v3 = await llaves_sign(custodia.fabrica)
    assert [(k.version, k.state, k.provider) for k in (v1, v2, v3)] == [
        (1, "decrypt_only", "local"),
        (2, "decrypt_only", "openbao"),
        (3, "active", "local"),
    ]
    assert bytes(v3.wrapped_material) == b"local:sign-ed25519"
    assert v3.public_key == await custodia.local.sign_public_key()


async def test_la_reversa_a_local_sin_el_archivo_sale_2_y_no_toca_nada(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sembrar_firmas(custodia)
    _rotar(settings_custodia, monkeypatch, *_a("openbao", admin))
    assert settings_custodia.CRYPTO_LOCAL_SIGNING_KEY_PATH is not None
    settings_custodia.CRYPTO_LOCAL_SIGNING_KEY_PATH.unlink()
    antes = [(k.version, k.state) for k in await llaves_sign(custodia.fabrica)]

    resultado = _rotar(settings_custodia, monkeypatch, *_a("local", admin))

    assert resultado.exit_code == 2, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert [(k.version, k.state) for k in await llaves_sign(custodia.fabrica)] == antes


# Rechazos ----------------------------------------------------------------------------------------


async def test_sin_provider_sale_2_purpose_not_rotatable_y_no_toca_nada(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sembrado = await sembrar_firmas(custodia)

    resultado = _rotar(settings_custodia, monkeypatch, "--reason", MOTIVO, "--as", admin.email)

    assert resultado.exit_code == 2 and "purpose_not_rotatable" in resultado.output
    await _intacto(custodia, sembrado.firmas)


async def test_con_el_proveedor_vigente_sale_2_purpose_not_rotatable(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sembrado = await sembrar_firmas(custodia)

    resultado = _rotar(settings_custodia, monkeypatch, *_a("local", admin))

    assert resultado.exit_code == 2 and "purpose_not_rotatable" in resultado.output
    await _intacto(custodia, sembrado.firmas)


async def test_con_el_proveedor_destino_sin_configurar_nombra_la_variable(
    migracion_lista: Entorno, settings_prueba: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`settings_prueba` no define `OPENBAO_TOKEN_FILE` y aquí no se parchea la fábrica."""
    custodia = migracion_lista
    sembrado = await sembrar_firmas(custodia)

    resultado = _rotar(settings_prueba, monkeypatch, *_a("openbao", admin))

    assert resultado.exit_code == 2 and "OPENBAO_TOKEN_FILE" in resultado.output
    await _intacto(custodia, sembrado.firmas)


async def test_provider_con_una_clase_de_cifrado_sale_2(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _rotar(
        settings_custodia, monkeypatch, *_a("openbao", admin), clase="member.document"
    )

    assert resultado.exit_code == 2, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)


async def test_en_produccion_sin_as_sale_2(
    custodia: Entorno, settings_custodia: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sembrar_firmas(custodia)

    resultado = _rotar(
        settings_custodia,
        monkeypatch,
        "--provider",
        "openbao",
        "--reason",
        MOTIVO,
        env="production",
    )

    assert resultado.exit_code == 2
    assert "--as <correo> es obligatorio con ENV=production" in resultado.output
    assert len(await llaves_sign(custodia.fabrica)) == 1


def test_rotate_key_py_sigue_bajo_260_lineas() -> None:
    ruta = Path(__file__).resolve().parents[2] / "src" / "app" / "cli_ops" / "rotate_key.py"
    assert len(ruta.read_text(encoding="utf-8").splitlines()) < 260


async def test_provider_local_con_openbao_sale_2_con_el_mensaje_fijo_y_no_toca_nada(
    custodia: Entorno, settings_custodia: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5-D50: con el overlay openbao el worker no monta `keys`: la firma solo va a openbao."""
    await sembrar_firmas(custodia)
    assert _rotar(settings_custodia, monkeypatch, *_a("openbao", admin)).exit_code == 0
    antes = [(k.version, k.state, k.provider) for k in await llaves_sign(custodia.fabrica)]
    firmas = await instantanea_firmas(custodia.fabrica)
    ajustes = settings_custodia.model_copy(
        update={"CRYPTO_PROVIDER": "openbao", "OPENBAO_TOKEN_FILE": Path("token-de-prueba")}
    )

    resultado = _rotar(ajustes, monkeypatch, *_a("local", admin))

    assert resultado.exit_code == 2, resultado.output
    assert "el worker no monta el volumen keys" in resultado.output
    assert "solo puede ir a openbao" in resultado.output
    assert [(k.version, k.state, k.provider) for k in await llaves_sign(custodia.fabrica)] == antes
    assert await instantanea_firmas(custodia.fabrica) == firmas
