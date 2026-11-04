"""`export-kek`, `verify-kek-backup` y `restore-kek` (S4B-B3a, US-116; S4B-D58, D62, D74, D85, D89).

Con `CliRunner`, el `age` falso (en Windows se omiten las pruebas que lo lanzan, ver `age_falso`)
y `kek_de_prueba`. Contrato de textos (stderr/stdout, `resultado.output`):
- sin `--as`: `--as es obligatorio`; `--as` de un coach: `no existe un admin activo`;
- `--out` bajo `BACKUP_DIR` o bajo la KEK viva: `la ruta de salida no es válida` (sin la ruta);
- `--out` existente: `el archivo de salida ya existe`;
- proveedor distinto de `local`: `solo con CRYPTO_PROVIDER=local`;
- KEK ausente en `export-kek`: `la KEK no está disponible` (en `restore-kek` no hace falta);
- sin terminal: `se requiere una terminal interactiva`;
- `restore-kek` con la base caída: `sin bitácora` y sale 0;
- `verify-kek-backup`: línea `verify-kek-backup: total=N failed=M`; 0 todo ok, 1 alguna DEK sin
  desenvolver, 2 archivo inválido (`no se pudo abrir el respaldo`);
- `--db-timeouts off` con `ENV=production`: `no se acepta con ENV=production`, sale 2.
Cada salida 2 afirma además su texto: el stub del Rojo sale 2 con `no implementado`.
La bitácora: `crypto_ops` con `kek.backup`, `key_id` y `key_version` nulos, actor de `--as`;
`restore-kek` con `purpose = restore` y `after = {"op": "restore"}` (S4B-D74).
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from click.testing import Result
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli_base
from app.cli import app
from app.cli_ops.keys import KeyPaths
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto import archive, bootstrap, provider
from app.core.crypto.models import CryptoOp
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.fake_age import configurar, desenvolver_falso, envolver_falso, llamadas
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


# Apoyo ---------------------------------------------------------------------------------------


@pytest.fixture
async def admin(limpiar_demo: Fabrica, argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


@pytest.fixture
async def coach(limpiar_demo: Fabrica, argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="coach", password=CLAVE_PRUEBA)


def _kek(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    previo: Sequence[str] = (),
    env: Any = "dev",
) -> Result:
    return correr(app, [*previo, *args], env, base=settings, monkeypatch=monkeypatch)


def _kek_bytes(rutas: KeyPaths) -> bytes:
    return rutas.kek.read_bytes()


def _sin_kek(texto: str, kek: bytes) -> None:
    assert kek.hex() not in texto
    assert base64.b64encode(kek).decode() not in texto
    assert base64.urlsafe_b64encode(kek).decode() not in texto


async def _ops(fabrica: Fabrica, verbo: str) -> list[CryptoOp]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoOp)
            .where(CryptoOp.verb == verbo, CryptoOp.data_class == "kek.backup")
            .order_by(CryptoOp.at)
        )
        return list(filas)


async def _auditoria(fabrica: Fabrica) -> list[AuditEntry]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry)
            .where(AuditEntry.action == "export", AuditEntry.table_name == "crypto.crypto_keys")
            .order_by(AuditEntry.seq)
        )
        return list(filas)


def _con_puerto_cerrado(settings: Settings) -> Settings:
    partes = urlsplit(settings.DATABASE_URL.get_secret_value())
    cerrado = partes._replace(netloc=f"{partes.username}:{partes.password}@127.0.0.1:1")
    return settings.model_copy(update={"DATABASE_URL": SecretStr(urlunsplit(cerrado))})


def _respaldo(carpeta: Path, kek: bytes, nombre: str = "kek.age") -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(envolver_falso(kek))
    return ruta


@pytest.fixture
def salidas(tmp_path: Path) -> Path:
    carpeta = tmp_path / "salidas"
    carpeta.mkdir()
    return carpeta


# export-kek ----------------------------------------------------------------------------------


def test_export_kek_escribe_el_archivo_con_la_kek_envuelta(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = salidas / "kek.age"

    resultado = _kek(
        entorno_kek, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email
    )

    assert resultado.exit_code == 0, resultado.output
    assert desenvolver_falso(destino.read_bytes()) == _kek_bytes(kek_de_prueba)
    if os.name != "nt":
        assert (destino.stat().st_mode & 0o777) == 0o600


def test_export_kek_no_sobrescribe(
    ajustes_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = salidas / "kek.age"
    destino.write_bytes(b"previo")

    resultado = _kek(
        ajustes_kek, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email
    )

    assert resultado.exit_code == 2 and "el archivo de salida ya existe" in resultado.output
    assert destino.read_bytes() == b"previo"
    assert "no implementado" not in resultado.output


def test_export_kek_rechaza_out_bajo_backup_dir(
    ajustes_kek: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = ajustes_kek.BACKUP_DIR / "kek.age"

    resultado = _kek(
        ajustes_kek, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email
    )

    assert resultado.exit_code == 2 and "la ruta de salida no es válida" in resultado.output
    assert not destino.exists()
    assert str(ajustes_kek.BACKUP_DIR) not in resultado.output


def test_export_kek_rechaza_un_proveedor_distinto_de_local(
    ajustes_kek: Settings, admin: Any, salidas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    otro = ajustes_kek.model_copy(update={"CRYPTO_PROVIDER": "openbao"})
    destino = salidas / "kek.age"

    resultado = _kek(otro, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email)

    assert resultado.exit_code == 2 and "solo con CRYPTO_PROVIDER=local" in resultado.output
    assert not destino.exists()


async def test_export_kek_deja_una_fila_de_crypto_ops_y_una_entrada_de_auditoria(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    limpiar_demo: Fabrica,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _kek(
        entorno_kek,
        monkeypatch,
        "export-kek",
        "--out",
        str(salidas / "kek.age"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    (op,) = await _ops(limpiar_demo, "export")
    assert (op.data_class, op.key_id, op.key_version, op.result) == ("kek.backup", None, None, "ok")
    assert op.user_id == admin.id and op.purpose != "restore"
    (entrada,) = await _auditoria(limpiar_demo)
    assert entrada.user_id == admin.id
    volcado = json.dumps([entrada.before, entrada.after])
    _sin_kek(volcado, _kek_bytes(kek_de_prueba))
    assert "apxw1" not in volcado


def test_no_existe_passphrase_ni_passphrase_file(
    ajustes_kek: Settings, admin: Any, salidas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for comando in ("export-kek", "restore-kek"):
        ayuda = _kek(ajustes_kek, monkeypatch, comando, "--help")
        assert "passphrase" not in ayuda.output.lower()
    resultado = _kek(
        ajustes_kek,
        monkeypatch,
        "export-kek",
        "--out",
        str(salidas / "kek.age"),
        "--as",
        admin.email,
        "--passphrase-file",
        "frase.txt",
    )
    assert resultado.exit_code == 2 and "No such option" in resultado.output


def test_la_salida_y_el_log_no_contienen_la_kek_ni_su_base64(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    destino = salidas / "kek.age"

    exportar = _kek(
        entorno_kek, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email
    )
    verificar = _kek(
        entorno_kek, monkeypatch, "verify-kek-backup", str(destino), "--as", admin.email
    )
    restaurar = _kek(
        entorno_kek,
        monkeypatch,
        "restore-kek",
        str(destino),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert exportar.exit_code == 0 and restaurar.exit_code == 0, (exportar.output, restaurar.output)
    kek = _kek_bytes(kek_de_prueba)
    for texto in (exportar.output, verificar.output, restaurar.output, caplog.text):
        _sin_kek(texto, kek)


def test_export_kek_sin_as_sale_2(
    ajustes_kek: Settings, salidas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _kek(ajustes_kek, monkeypatch, "export-kek", "--out", str(salidas / "kek.age"))

    assert resultado.exit_code == 2 and "--as es obligatorio" in resultado.output
    assert not (salidas / "kek.age").exists()


def test_export_kek_con_un_coach_sale_2(
    ajustes_kek: Settings, coach: Any, salidas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _kek(
        ajustes_kek,
        monkeypatch,
        "export-kek",
        "--out",
        str(salidas / "kek.age"),
        "--as",
        coach.email,
    )

    assert resultado.exit_code == 2 and "no existe un admin activo" in resultado.output
    assert not (salidas / "kek.age").exists()


def test_export_kek_no_llama_ensure_keys_ni_configure_provider(
    entorno_kek: Settings, admin: Any, salidas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4B-D62: los comandos de la KEK usan `cli_runtime`, nunca `crypto_runtime`."""
    llamadas_espiadas: list[str] = []

    def espia(nombre: str) -> Any:
        async def _asincrona(*_a: Any, **_k: Any) -> None:
            llamadas_espiadas.append(nombre)

        def _sincrona(*_a: Any, **_k: Any) -> None:
            llamadas_espiadas.append(nombre)

        return _asincrona if nombre == "ensure_keys" else _sincrona

    monkeypatch.setattr(bootstrap, "ensure_keys", espia("ensure_keys"))
    monkeypatch.setattr(provider, "configure_provider", espia("configure_provider"))
    monkeypatch.setattr(cli_base, "crypto_runtime", espia("crypto_runtime"))
    destino = salidas / "kek.age"

    exportar = _kek(
        entorno_kek, monkeypatch, "export-kek", "--out", str(destino), "--as", admin.email
    )
    verificar = _kek(
        entorno_kek, monkeypatch, "verify-kek-backup", str(destino), "--as", admin.email
    )
    restaurar = _kek(
        entorno_kek,
        monkeypatch,
        "restore-kek",
        str(destino),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert exportar.exit_code == 0 and restaurar.exit_code == 0, (exportar.output, restaurar.output)
    assert verificar.exit_code in (0, 1), verificar.output
    assert llamadas_espiadas == []


def test_export_kek_con_la_kek_ausente_sale_2_y_restore_kek_si_corre(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kek = _kek_bytes(kek_de_prueba)
    respaldo = _respaldo(salidas, kek)
    sin_kek = entorno_kek.model_copy(
        update={"CRYPTO_LOCAL_KEK_PATH": tmp_path / "otra-carpeta" / "kek.bin"}
    )
    monkeypatch.setattr(archive, "get_settings", lambda: sin_kek)

    exportar = _kek(
        sin_kek, monkeypatch, "export-kek", "--out", str(salidas / "n.age"), "--as", admin.email
    )
    restaurar = _kek(
        sin_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert exportar.exit_code == 2 and "la KEK no está disponible" in exportar.output
    assert restaurar.exit_code == 0, restaurar.output
    assert (salidas / "restaurada.bin").read_bytes() == kek


# restore-kek ---------------------------------------------------------------------------------


def test_restore_kek_con_la_base_caida_avisa_sin_bitacora_y_sale_0(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kek = _kek_bytes(kek_de_prueba)
    respaldo = _respaldo(salidas, kek)
    caida = _con_puerto_cerrado(entorno_kek)
    monkeypatch.setattr(archive, "get_settings", lambda: caida)

    resultado = _kek(
        caida,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    assert "sin bitácora" in resultado.output
    assert (salidas / "restaurada.bin").read_bytes() == kek
    _sin_kek(resultado.output, kek)


async def test_restore_kek_registra_export_con_proposito_restore(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    limpiar_demo: Fabrica,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))

    resultado = _kek(
        entorno_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    (op,) = await _ops(limpiar_demo, "export")
    assert op.purpose == "restore" and op.key_id is None and op.key_version is None
    assert op.user_id == admin.id
    (entrada,) = await _auditoria(limpiar_demo)
    assert entrada.after == {"op": "restore"}


def test_restore_kek_no_sobrescribe_ni_escribe_bajo_la_kek_viva(
    ajustes_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kek = _kek_bytes(kek_de_prueba)
    respaldo = _respaldo(salidas, kek)
    existente = salidas / "ya.bin"
    existente.write_bytes(b"previo")

    sobre = _kek(
        ajustes_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(existente),
        "--as",
        admin.email,
    )
    viva = _kek(
        ajustes_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(kek_de_prueba.kek.parent / "nueva.bin"),
        "--as",
        admin.email,
    )

    assert sobre.exit_code == 2 and "el archivo de salida ya existe" in sobre.output
    assert existente.read_bytes() == b"previo"
    assert viva.exit_code == 2 and "la ruta de salida no es válida" in viva.output
    assert not (kek_de_prueba.kek.parent / "nueva.bin").exists()
    assert _kek_bytes(kek_de_prueba) == kek


# verify-kek-backup ---------------------------------------------------------------------------


async def test_verify_kek_backup_sale_0_cuando_abre_todas_las_dek(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    llaves_en_base: Fabrica,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))

    resultado = _kek(
        entorno_kek, monkeypatch, "verify-kek-backup", str(respaldo), "--as", admin.email
    )

    assert resultado.exit_code == 0, resultado.output
    assert "verify-kek-backup: total=8 failed=0" in resultado.output
    (op,) = await _ops(llaves_en_base, "verify")
    assert (op.result, op.key_id, op.key_version, op.user_id) == ("ok", None, None, admin.id)


async def test_verify_kek_backup_sale_1_si_alguna_dek_no_se_abre(
    entorno_kek: Settings,
    llaves_en_base: Fabrica,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respaldo = _respaldo(salidas, os.urandom(32))  # otra KEK

    resultado = _kek(
        entorno_kek, monkeypatch, "verify-kek-backup", str(respaldo), "--as", admin.email
    )

    assert resultado.exit_code == 1, resultado.output
    assert "verify-kek-backup: total=8 failed=8" in resultado.output
    (op,) = await _ops(llaves_en_base, "verify")
    assert op.result == "error" and op.key_id is None


async def test_verify_kek_backup_con_un_archivo_invalido_sale_2(
    entorno_kek: Settings,
    llaves_en_base: Fabrica,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ajeno = salidas / "ajeno.age"
    ajeno.write_bytes(b"esto no es age")

    resultado = _kek(entorno_kek, monkeypatch, "verify-kek-backup", str(ajeno), "--as", admin.email)

    assert resultado.exit_code == 2 and "no se pudo abrir el respaldo" in resultado.output
    assert "unknown version" not in resultado.output  # nada del texto del hijo


# Sin terminal y producción ---------------------------------------------------------------------


@pytest.mark.parametrize("comando", ["export-kek", "restore-kek", "verify-kek-backup"])
def test_sin_terminal_sale_2_con_el_mensaje_fijo(
    comando: str,
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    age_falso: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))
    configurar(age_falso, no_tty=True)
    args = {
        "export-kek": ["export-kek", "--out", str(salidas / "n.age")],
        "restore-kek": ["restore-kek", str(respaldo), "--out", str(salidas / "r.bin")],
        "verify-kek-backup": ["verify-kek-backup", str(respaldo)],
    }[comando]

    resultado = _kek(entorno_kek, monkeypatch, *args, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert "se requiere una terminal interactiva" in resultado.output
    assert "/dev/tty" not in resultado.output  # nada del texto del hijo
    assert len(llamadas(age_falso)) == 1


@pytest.mark.parametrize("comando", ["export-kek", "restore-kek", "verify-kek-backup"])
def test_db_timeouts_off_con_produccion_sale_2(
    comando: str,
    settings_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    produccion = settings_kek.model_copy(update={"ENV": "production"})
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))
    args = {
        "export-kek": ["export-kek", "--out", str(salidas / "n.age")],
        "restore-kek": ["restore-kek", str(respaldo), "--out", str(salidas / "r.bin")],
        "verify-kek-backup": ["verify-kek-backup", str(respaldo)],
    }[comando]

    resultado = _kek(
        produccion,
        monkeypatch,
        *args,
        "--as",
        admin.email,
        previo=("--db-timeouts", "off"),
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert "no se acepta con ENV=production" in resultado.output
    assert not (salidas / "n.age").exists() and not (salidas / "r.bin").exists()


# restore-kek: solo los errores de conexión degradan a "sin bitácora" (S4B-D130, L1) -------------


def _linea_json(texto: str) -> dict[str, Any]:
    for linea in texto.splitlines():
        if linea.startswith("{") and "restore_sin_bitacora" in linea:
            return dict(json.loads(linea))
    raise AssertionError("no hay la línea JSON restore_sin_bitacora")


def test_restore_kek_con_la_base_caida_escribe_una_linea_json_sin_material(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kek = _kek_bytes(kek_de_prueba)
    respaldo = _respaldo(salidas, kek)
    caida = _con_puerto_cerrado(entorno_kek)
    monkeypatch.setattr(archive, "get_settings", lambda: caida)

    resultado = _kek(
        caida,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    linea = _linea_json(resultado.output)
    assert linea["event"] == "restore_sin_bitacora" and linea["actor"] == admin.email
    assert "ts" in linea and set(linea) == {"event", "actor", "ts"}
    _sin_kek(resultado.output, kek)
    assert str(salidas) not in json.dumps(linea)


def test_restore_kek_con_operationalerror_degrada_a_sin_bitacora(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import OperationalError

    from app.cli_ops import kek as kek_ops

    async def _sin_conexion(*_a: Any, **_k: Any) -> None:
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    monkeypatch.setattr(kek_ops, "resolve_admin_actor", _sin_conexion)
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))

    resultado = _kek(
        entorno_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    assert "sin bitácora" in resultado.output and _linea_json(resultado.output)
    assert (salidas / "restaurada.bin").exists()


def test_restore_kek_deja_subir_un_error_que_no_es_de_conexion(
    ajustes_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli_ops import kek as kek_ops

    async def _roto(*_a: Any, **_k: Any) -> None:
        raise AttributeError("bug del programa")

    monkeypatch.setattr(kek_ops, "resolve_admin_actor", _roto)
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))

    resultado = _kek(
        ajustes_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert isinstance(resultado.exception, AttributeError)
    assert "sin bitácora" not in resultado.output
    assert not (salidas / "restaurada.bin").exists()


def test_restore_kek_con_la_base_arriba_y_la_bitacora_rota_sale_0_sin_bitacora(
    entorno_kek: Settings,
    kek_de_prueba: KeyPaths,
    admin: Any,
    salidas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli_ops import kek as kek_ops

    async def _roto(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("fallo al escribir la bitácora")

    monkeypatch.setattr(kek_ops, "_record", _roto)
    respaldo = _respaldo(salidas, _kek_bytes(kek_de_prueba))

    resultado = _kek(
        entorno_kek,
        monkeypatch,
        "restore-kek",
        str(respaldo),
        "--out",
        str(salidas / "restaurada.bin"),
        "--as",
        admin.email,
    )

    assert resultado.exit_code == 0, resultado.output
    assert "sin bitácora" in resultado.output and _linea_json(resultado.output)
