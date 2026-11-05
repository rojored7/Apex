"""`retire-key <key_id> --as <correo> --confirm-audit-blobs N [--manifest RUTA]` (S4B-B3b;
S4B-D38, D63, D86).

`retired` es irreversible. El comando cuenta en vivo las filas de negocio con ese `key_id` (deben
ser 0, bajo `FOR UPDATE`) y los blobs en `audit.audit_log` (que el operador confirma tecleando
`N`), e imprime ambos. Exige, antes de cambiar nada:
- un `verify-kek-backup` `ok` de una persona de menos de 24 h (`crypto_ops`);
- un `latest.json` con `.minisig` cuya firma `minisign` VERIFICA con `BACKUP_SIGN_PUBKEY`
  (S5-B13, S5-D72: ya no basta con que el archivo exista), `verify == "ok"` y menos de 24 h.
Contrato de salida (stdout/stderr juntos en `resultado.output`):
- `retire-key: filas_negocio=F` y `retire-key: audit_blobs=A` antes de decidir;
- sin `--as`: `--as es obligatorio`; sin `--confirm-audit-blobs`: 2 con esa opción en el texto;
- `N` distinto de `A`: 2 y los dos conteos impresos;
- sin verify reciente: `no hay un verify-kek-backup ok de una persona en las últimas 24 h`;
- manifiesto ausente, viejo, sin firma o con `verify != ok`: el mismo texto fijo
  `no hay un latest.json reciente con firma adjunta en /data/backups (verify: ok)`;
- todo en orden: 0, `retire-key: llave retirada`, auditoría `update` sobre `crypto.crypto_keys` con
  `after = {"event": "retire", "business_rows": 0, "audit_blobs": N}` y `crypto_ops` `rotate`.
El stub del Rojo sale 2 con `no implementado`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from click.testing import Result
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.models import CryptoKey
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.crypto._rotacion import (
    LLAVE_RETIRO,
    Fabrica,
    blobs_de_rotacion,
    cuenta_de_ops,
    escribir_manifiesto,
    filas_rotacion,
    llaves_de,
    verify_reciente,
)
from tests.crypto._rotacion_flujo import registrar_blob, rotar
from tests.factories.users import make_user

SIN_VERIFY = "no hay un verify-kek-backup ok de una persona en las últimas 24 h"
SIN_MANIFIESTO = "no hay un latest.json reciente con firma adjunta en /data/backups (verify: ok)"

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


@pytest.fixture
def settings_prueba(settings_prueba: Settings, tmp_path: Path) -> Settings:
    """`BACKUP_DIR` es la carpeta de la prueba: `--manifest` solo vale bajo ella (S4B-D149)."""
    return settings_prueba.model_copy(
        update={"BACKUP_DIR": tmp_path, "BACKUP_SIGN_PUBKEY": LLAVE_RETIRO.pubkey}
    )


@pytest.fixture
async def admin(limpiar_demo: async_sessionmaker[AsyncSession], argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


@pytest.fixture
async def rotada(rotacion_lista: Fabrica) -> dict[str, Any]:
    """30 filas rotadas (v1 `decrypt_only`, v2 `active`) y un blob de v1 en la auditoría."""
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 30)
        viejos = await blobs_de_rotacion(sesion)
    await rotar(rotacion_lista)
    await registrar_blob(rotacion_lista, viejos[ids[0]])
    async with rotacion_lista() as sesion:
        v1, _ = await llaves_de(sesion)
    return {"v1": v1.id, "viejo": viejos[ids[0]]}


def _retirar(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    previo: tuple[str, ...] = (),
    env: Any = "dev",
) -> Result:
    return correr(app, [*previo, "retire-key", *args], env, base=settings, monkeypatch=monkeypatch)


def _todo_en_orden(llave: UUID, admin: Any, manifiesto: Path, blobs: int = 1) -> tuple[str, ...]:
    return (
        str(llave),
        "--as",
        admin.email,
        "--confirm-audit-blobs",
        str(blobs),
        "--manifest",
        str(manifiesto),
    )


async def _estado(fabrica: Fabrica) -> list[tuple[int, str]]:
    async with fabrica() as sesion:
        return [(k.version, k.state) for k in await llaves_de(sesion)]


async def _sin_retirar(fabrica: Fabrica) -> None:
    assert await _estado(fabrica) == [(1, "decrypt_only"), (2, "active")]


async def _con_verify(fabrica: Fabrica, admin: Any, **cambios: Any) -> None:
    async with fabrica() as sesion:
        await verify_reciente(sesion, cambios.pop("actor", admin.id), **cambios)


# Todo en orden -------------------------------------------------------------------------------


async def test_retire_key_en_orden_sale_0_y_deja_retired(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 0, resultado.output
    assert "retire-key: filas_negocio=0" in resultado.output
    assert "retire-key: audit_blobs=1" in resultado.output
    assert "retire-key: llave retirada" in resultado.output
    assert await _estado(rotacion_lista) == [(1, "retired"), (2, "active")]


async def test_retire_key_audita_ambos_conteos_y_deja_una_fila_rotate(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)
    async with rotacion_lista() as sesion:
        antes = await cuenta_de_ops(sesion, "rotate")

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 0, resultado.output
    async with rotacion_lista() as sesion:
        entradas = (
            await sesion.scalars(
                select(AuditEntry).where(
                    AuditEntry.action == "update", AuditEntry.table_name == "crypto.crypto_keys"
                )
            )
        ).all()
        retiros = [e for e in entradas if (e.after or {}).get("event") == "retire"]
        assert len(retiros) == 1
        assert retiros[0].after == {"event": "retire", "business_rows": 0, "audit_blobs": 1}
        assert retiros[0].user_id == admin.id
        assert await cuenta_de_ops(sesion, "rotate") == antes + 1


async def test_la_salida_de_retire_key_no_trae_material_ni_blobs(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 0, resultado.output
    assert "apx1." not in resultado.output
    assert rotada["viejo"] not in resultado.output
    async with rotacion_lista() as sesion:
        for llave in (await sesion.scalars(select(CryptoKey))).all():
            assert bytes(llave.wrapped_material).hex() not in resultado.output
    assert settings_prueba.CRYPTO_LOCAL_KEK_PATH is not None
    assert settings_prueba.CRYPTO_LOCAL_KEK_PATH.read_bytes().hex() not in resultado.output


# Argumentos ----------------------------------------------------------------------------------


async def test_sin_as_sale_2(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _retirar(
        settings_prueba,
        monkeypatch,
        str(rotada["v1"]),
        "--confirm-audit-blobs",
        "1",
        "--manifest",
        str(manifiesto_reciente),
    )

    assert resultado.exit_code == 2 and "--as es obligatorio" in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_sin_confirm_audit_blobs_sale_2(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_prueba,
        monkeypatch,
        str(rotada["v1"]),
        "--as",
        admin.email,
        "--manifest",
        str(manifiesto_reciente),
    )

    assert resultado.exit_code == 2
    assert "--confirm-audit-blobs" in resultado.output
    assert "no implementado" not in resultado.output
    await _sin_retirar(rotacion_lista)


@pytest.mark.parametrize("equivocado", [0, 2, 99])
async def test_un_n_incorrecto_sale_2_e_imprime_los_dos_conteos(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
    equivocado: int,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_prueba,
        monkeypatch,
        *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente, blobs=equivocado),
    )

    assert resultado.exit_code == 2, resultado.output
    assert "retire-key: filas_negocio=0" in resultado.output
    assert "retire-key: audit_blobs=1" in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_una_llave_active_o_inexistente_sale_2(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)
    async with rotacion_lista() as sesion:
        _, activa = await llaves_de(sesion)
    for llave in (activa.id, UUID(int=777)):
        resultado = _retirar(
            settings_prueba, monkeypatch, *_todo_en_orden(llave, admin, manifiesto_reciente, 0)
        )
        assert resultado.exit_code == 2, resultado.output
        assert "no implementado" not in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_un_key_id_mal_formado_sale_2(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _retirar(
        settings_prueba,
        monkeypatch,
        "no-es-un-uuid",
        "--as",
        admin.email,
        "--confirm-audit-blobs",
        "1",
        "--manifest",
        str(manifiesto_reciente),
    )

    assert resultado.exit_code == 2, resultado.output
    assert "key_id" in resultado.output
    assert "no implementado" not in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_con_filas_de_negocio_pendientes_sale_2_con_el_conteo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.crypto._rotacion_flujo import iniciar, un_lote

    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 60)
    job_id = await iniciar(rotacion_lista)
    await un_lote(rotacion_lista, job_id, 20)  # quedan 40 con la llave vieja
    await _con_verify(rotacion_lista, admin)
    async with rotacion_lista() as sesion:
        v1, _ = await llaves_de(sesion)

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(v1.id, admin, manifiesto_reciente, 0)
    )

    assert resultado.exit_code == 2, resultado.output
    assert "retire-key: filas_negocio=40" in resultado.output
    await _sin_retirar(rotacion_lista)


# Exigencias previas --------------------------------------------------------------------------

VERIFY_MALOS = {
    "sin ninguna fila": None,
    "de hace 25 horas": {"edad": timedelta(hours=25)},
    "del usuario técnico": {"actor": SYSTEM_USER_ID},
    "con resultado error": {"resultado": "error"},
}


@pytest.mark.parametrize("caso", list(VERIFY_MALOS.values()), ids=list(VERIFY_MALOS))
async def test_sin_un_verify_kek_backup_reciente_de_una_persona_sale_2(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any] | None,
) -> None:
    if caso is not None:
        await _con_verify(rotacion_lista, admin, **caso)

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_VERIFY in resultado.output
    await _sin_retirar(rotacion_lista)


MANIFIESTOS_MALOS = {
    "sin firma": {"con_firma": False},
    "con verify distinto de ok": {"verify": "failed"},
    "con verify omitido": {"verify": "skipped"},
    "de hace 25 horas": {"antiguedad": timedelta(hours=25)},
    # S5-B13 (S5-D72): la firma debe verificar, no solo existir.
    "con firma que no es una firma": {"firma": "basura"},
    "con firma de otra llave": {"firma": "otra_llave"},
    "con un bit de la firma cambiado": {"firma": "bit"},
    "alterado despues de firmar": {"firma": "manifiesto_alterado"},
}


@pytest.mark.parametrize("caso", list(MANIFIESTOS_MALOS.values()), ids=list(MANIFIESTOS_MALOS))
async def test_un_latest_json_que_no_sirve_sale_2_con_el_mensaje_fijo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any],
) -> None:
    await _con_verify(rotacion_lista, admin)
    manifiesto = escribir_manifiesto(tmp_path / "malo", **caso)

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto)
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_sin_backup_sign_pubkey_configurada_no_se_confia_en_ningun_manifiesto(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cierra en falso: sin llave pública no hay con qué verificar (S5-D72)."""
    await _con_verify(rotacion_lista, admin)
    sin_llave = settings_prueba.model_copy(update={"BACKUP_SIGN_PUBKEY": None})

    resultado = _retirar(
        sin_llave, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_sin_latest_json_sale_2_con_el_mensaje_fijo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_prueba,
        monkeypatch,
        *_todo_en_orden(rotada["v1"], admin, tmp_path / "no-existe" / "latest.json"),
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_un_latest_json_que_no_es_json_sale_2_con_el_mensaje_fijo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)
    await asyncio.to_thread(manifiesto_reciente.write_text, "{ esto no es json", "utf-8")

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_las_exigencias_se_revisan_antes_de_contar_o_cambiar_nada(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin verify reciente el comando se detiene: no hay `rotate` nuevo en `crypto_ops`."""
    async with rotacion_lista() as sesion:
        antes = await cuenta_de_ops(sesion, "rotate")

    resultado = _retirar(
        settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente)
    )

    assert resultado.exit_code == 2, resultado.output
    async with rotacion_lista() as sesion:
        assert await cuenta_de_ops(sesion, "rotate") == antes
        retiros = await sesion.scalar(
            text("SELECT count(*) FROM audit.audit_log WHERE after::text LIKE :p"),
            {"p": '%"retire"%'},
        )
        assert retiros == 0


async def test_db_timeouts_off_con_produccion_sale_2(
    settings_produccion: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)

    resultado = _retirar(
        settings_produccion,
        monkeypatch,
        *_todo_en_orden(rotada["v1"], admin, manifiesto_reciente),
        previo=("--db-timeouts", "off"),
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert "no se acepta con ENV=production" in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_un_manifiesto_fuera_de_backup_dir_sale_2_con_el_mensaje_fijo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)
    ajeno = escribir_manifiesto(tmp_path_factory.mktemp("ajeno"))

    resultado = _retirar(settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, ajeno))

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)


async def test_un_enlace_simbolico_como_manifiesto_sale_2_con_el_mensaje_fijo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    rotada: dict[str, Any],
    admin: Any,
    manifiesto_reciente: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _con_verify(rotacion_lista, admin)
    enlace = tmp_path / "enlace.json"
    try:
        enlace.symlink_to(manifiesto_reciente)
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")
    (tmp_path / "enlace.json.minisig").write_text("firma", encoding="utf-8")

    resultado = _retirar(settings_prueba, monkeypatch, *_todo_en_orden(rotada["v1"], admin, enlace))

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _sin_retirar(rotacion_lista)
