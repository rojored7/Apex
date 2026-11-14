"""`rotate-key <clase> --reason TEXTO --as <correo> [--index] [--batch-size 500]` (S4B-B3b, US-030;
S4B-D39, D40, D63).

Con `CliRunner` sobre la base de prueba, el modelo de 1.200 filas (`rotacion_lista`) y `reloj`.
Contrato de salida (stdout/stderr juntos en `resultado.output`):
- `rotate-key: total=N` ANTES de cualquier `rotate-key: hecho=X/N` (uno por lote);
- termina, con exit 0, en `rotate-key: llave anterior en decrypt_only; retirar con retire-key`;
- sin `--reason`, en blanco, con correo/`\\d{6,}`/control o de más de 200 caracteres: 2 y un texto
  con `--reason`, sin tocar llaves; sin `--as`: `--as es obligatorio`; `--as` de un coach:
  `no existe un admin activo`;
- `attachment.sensitive` (cifra, sin columnas ni puerto; S6-B1): 2 con `rotation_not_supported`,
  el error del service (ya no hay constante en el CLI);
- `--db-timeouts off` con `ENV=production`: 2 y `no se acepta con ENV=production`;
- candado tomado por otro proceso: 1 y `rotación en curso`;
- `DatabaseBusy` al iniciar: tres reintentos con espera de 1 s (cuatro intentos) y luego 1 con
  `la base está ocupada`;
- falla en un lote: 1, job `failed`, `repita el comando` para reanudar;
- la auditoría `update` sobre `crypto.crypto_keys` lleva el motivo en `after`.
El servicio se llama por módulo (`service.start_rotation`, `service.reencrypt_batch`) para que los
parches de estas pruebas lo alcancen. El stub del Rojo sale 2 con `no implementado`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from click.testing import Result
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import service
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob
from app.core.crypto.registry import DataClassSpec, override_registry
from app.core.db import DatabaseBusy
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    Fabrica,
    blobs_de_rotacion,
    filas_rotacion,
    llaves_de,
    registro_de_rotacion,
)
from tests.crypto._rotacion_flujo import todo_se_lee
from tests.factories.users import make_user

MOTIVO = "rotación trimestral de prueba"
FINAL = "llave anterior en decrypt_only; retirar con retire-key"

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


@pytest.fixture
async def admin(limpiar_demo: async_sessionmaker[AsyncSession], argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


@pytest.fixture
async def coach(limpiar_demo: async_sessionmaker[AsyncSession], argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="coach", password=CLAVE_PRUEBA)


def _rotar(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    previo: tuple[str, ...] = (),
    env: Any = "dev",
) -> Result:
    return correr(app, [*previo, "rotate-key", *args], env, base=settings, monkeypatch=monkeypatch)


def _estados(llaves: list[Any]) -> list[tuple[int, str]]:
    return [(k.version, k.state) for k in llaves]


async def _llaves(fabrica: Fabrica, purpose: str = "encrypt") -> list[tuple[int, str]]:
    async with fabrica() as sesion:
        return _estados(await llaves_de(sesion, purpose=purpose))


async def _jobs(fabrica: Fabrica) -> list[CryptoJob]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(CryptoJob).order_by(CryptoJob.created_at))).all())


async def _sin_cambios(fabrica: Fabrica) -> None:
    assert await _llaves(fabrica) == [(1, "active")]
    assert await _jobs(fabrica) == []


# Rotación de punta a punta -------------------------------------------------------------------


async def test_rotate_key_rota_y_deja_la_anterior_en_decrypt_only(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 1200)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 0, resultado.output
    assert await _llaves(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
    (job,) = await _jobs(rotacion_lista)
    assert (job.status, job.total, job.done) == ("done", 1200, 1200)
    async with rotacion_lista() as sesion:
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))


async def test_informa_el_total_antes_de_empezar_y_el_avance_por_lote(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 1200)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    salida = resultado.output
    assert resultado.exit_code == 0, salida
    assert "rotate-key: total=1200" in salida
    for avance in ("hecho=500/1200", "hecho=1000/1200", "hecho=1200/1200"):
        assert f"rotate-key: {avance}" in salida, avance
    assert salida.index("total=1200") < salida.index("hecho=500/1200")


async def test_batch_size_cambia_el_tamano_del_lote(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 300)

    resultado = _rotar(
        settings_prueba,
        monkeypatch,
        CLASE_ROTADA,
        "--reason",
        MOTIVO,
        "--as",
        admin.email,
        "--batch-size",
        "100",
    )

    assert resultado.exit_code == 0, resultado.output
    for avance in ("hecho=100/300", "hecho=200/300", "hecho=300/300"):
        assert f"rotate-key: {avance}" in resultado.output, avance


async def test_la_salida_termina_con_el_aviso_de_retire_key(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 30)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 0, resultado.output
    ultima = [linea for linea in resultado.output.splitlines() if linea.strip()][-1]
    assert ultima == f"rotate-key: {FINAL}"


async def test_audita_un_update_sobre_crypto_keys_con_el_motivo(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 30)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
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
    assert entradas, "falta la auditoría de la rotación"
    assert any(MOTIVO in str(e.after) for e in entradas)
    assert all(e.user_id == admin.id for e in entradas)


async def test_con_index_rota_la_llave_de_indice_y_no_la_de_cifrado(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 30)

    resultado = _rotar(
        settings_prueba,
        monkeypatch,
        CLASE_ROTADA,
        "--reason",
        MOTIVO,
        "--as",
        admin.email,
        "--index",
    )

    assert resultado.exit_code == 0, resultado.output
    assert await _llaves(rotacion_lista, "index") == [(1, "decrypt_only"), (2, "active")]
    assert await _llaves(rotacion_lista, "encrypt") == [(1, "active")]


async def test_la_salida_no_trae_material_de_llaves_ni_blobs(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 30)
        blobs = await blobs_de_rotacion(sesion)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 0, resultado.output
    assert "apx1." not in resultado.output
    assert not any(blob in resultado.output for blob in blobs.values())
    assert settings_prueba.CRYPTO_LOCAL_KEK_PATH is not None
    kek = settings_prueba.CRYPTO_LOCAL_KEK_PATH.read_bytes()
    assert kek.hex() not in resultado.output
    async with rotacion_lista() as sesion:
        for llave in await llaves_de(sesion):
            assert bytes(llave.wrapped_material).hex() not in resultado.output


# Entradas inválidas: salen 2 sin tocar llaves -------------------------------------------------


async def test_sin_reason_sale_2_sin_tocar_llaves(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _rotar(settings_prueba, monkeypatch, CLASE_ROTADA, "--as", admin.email)

    assert resultado.exit_code == 2
    assert "--reason" in resultado.output
    assert "no implementado" not in resultado.output
    await _sin_cambios(rotacion_lista)


REASONS_INVALIDOS = {
    "en blanco": "   ",
    "vacío": "",
    "correo": "por filtración de correo@x.y",
    "siete dígitos": "documento 1234567",
    "con salto de línea": "primera\nsegunda",
    "201 caracteres": "x" * 201,
}


@pytest.mark.parametrize("motivo", list(REASONS_INVALIDOS.values()), ids=list(REASONS_INVALIDOS))
async def test_un_reason_invalido_sale_2_sin_tocar_llaves(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
    motivo: str,
) -> None:
    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", motivo, "--as", admin.email
    )

    assert resultado.exit_code == 2, resultado.output
    assert "--reason" in resultado.output
    assert "no implementado" not in resultado.output
    assert motivo.strip() == "" or motivo not in resultado.output  # no repite el texto recibido
    await _sin_cambios(rotacion_lista)


async def test_sin_as_sale_2(
    settings_prueba: Settings, rotacion_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _rotar(settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO)

    assert resultado.exit_code == 2 and "--as es obligatorio" in resultado.output
    await _sin_cambios(rotacion_lista)


async def test_as_de_un_correo_inexistente_sale_2(
    settings_prueba: Settings, rotacion_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _rotar(
        settings_prueba,
        monkeypatch,
        CLASE_ROTADA,
        "--reason",
        MOTIVO,
        "--as",
        "nadie@test.apex",
    )

    assert resultado.exit_code == 2
    assert "no existe un admin activo" in resultado.output
    await _sin_cambios(rotacion_lista)


async def test_as_de_un_coach_sale_2(
    settings_prueba: Settings, rotacion_lista: Fabrica, coach: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", coach.email
    )

    assert resultado.exit_code == 2
    assert "no existe un admin activo" in resultado.output
    await _sin_cambios(rotacion_lista)


async def test_attachment_sensitive_sin_puerto_sale_2_con_el_error_del_service(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    proveedor_local: LocalFileProvider,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S6-B1 (S6-D14): la constante `ATTACHMENT_CLASS` desaparece del CLI. La clase ya está en el
    registro (C1 la suma; aquí se simula), cifra, no tiene columnas ni puerto: `start_rotation`
    responde `rotation_not_supported` y el CLI sale 2 con ese código, sin job ni llave nueva."""
    clase = DataClassSpec("attachment.sensitive", True, None, False, "str", ())
    # C1 registra el puerto real al arrancar `cli_runtime`; esta prueba simula la clase SIN puerto.
    monkeypatch.setattr("app.main.register_reencryptors", lambda: None)
    monkeypatch.setattr("app.core.crypto.reencryptor._registered", {})
    with override_registry({**registro_de_rotacion(), clase.name: clase}):
        async with rotacion_lista() as sesion, sesion.begin():
            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)

        resultado = _rotar(
            settings_prueba,
            monkeypatch,
            clase.name,
            "--reason",
            MOTIVO,
            "--as",
            admin.email,
        )

        assert resultado.exit_code == 2, resultado.output
        assert "rotation_not_supported" in resultado.output
        assert "EP-18" not in resultado.output and "G-09" not in resultado.output
        async with rotacion_lista() as sesion:
            llaves = await llaves_de(sesion, "encrypt", clase.name)
        assert [(k.version, k.state) for k in llaves] == [(1, "active")]
        assert await _jobs(rotacion_lista) == []
    await _sin_cambios(rotacion_lista)


async def test_db_timeouts_off_con_produccion_sale_2(
    settings_produccion: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _rotar(
        settings_produccion,
        monkeypatch,
        CLASE_ROTADA,
        "--reason",
        MOTIVO,
        "--as",
        admin.email,
        previo=("--db-timeouts", "off"),
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert "no se acepta con ENV=production" in resultado.output
    await _sin_cambios(rotacion_lista)


# Operación: candado, base ocupada y falla en un lote ------------------------------------------


async def test_con_el_candado_tomado_sale_1_rotacion_en_curso(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    candado_rotacion_tomado: None,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 1, resultado.output
    assert "rotación en curso" in resultado.output
    await _sin_cambios(rotacion_lista)


async def test_base_ocupada_reintenta_tres_veces_con_espera_de_1_s_y_sale_1(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intentos = 0
    esperas: list[float] = []

    async def ocupada(*args: object, **kwargs: object) -> None:
        nonlocal intentos
        intentos += 1
        raise DatabaseBusy

    async def sin_dormir(segundos: float, *args: object) -> None:
        esperas.append(segundos)

    monkeypatch.setattr(service, "start_rotation", ocupada)
    monkeypatch.setattr(asyncio, "sleep", sin_dormir)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 1, resultado.output
    assert "la base está ocupada" in resultado.output
    assert intentos == 4, "un intento y tres reintentos"
    assert [e for e in esperas if e == 1] == [1, 1, 1]
    await _sin_cambios(rotacion_lista)


async def test_una_falla_en_el_lote_2_deja_failed_y_repetir_reanuda_ese_job(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 1200)
    original = service.reencrypt_batch
    llamadas = 0

    async def falla_en_el_segundo(*args: Any, **kwargs: Any) -> int:
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:
            raise CryptoError("decrypt_failed", "falla inyectada")
        return await original(*args, **kwargs)

    with monkeypatch.context() as parche:
        parche.setattr(service, "reencrypt_batch", falla_en_el_segundo)
        primera = _rotar(
            settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
        )

    assert primera.exit_code == 1, primera.output
    assert "repita el comando" in primera.output
    assert "falla inyectada" not in primera.output
    (fallido,) = await _jobs(rotacion_lista)
    assert fallido.status == "failed" and fallido.done == 500
    assert await _llaves(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]
    async with rotacion_lista() as sesion:
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))

    segunda = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert segunda.exit_code == 0, segunda.output
    (job,) = await _jobs(rotacion_lista)
    assert job.id == fallido.id and (job.status, job.done) == ("done", 1200)
    assert await _llaves(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]


# S6-A2 (S6-D69): la llave de firma no se rota en sitio --------------------------------------------


async def test_rotate_key_audit_signature_sin_provider_sale_2_purpose_not_rotatable(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultado = _rotar(
        settings_prueba, monkeypatch, "audit.signature", "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 2, resultado.output
    assert "purpose_not_rotatable" in resultado.output
    assert await _jobs(rotacion_lista) == []


# S6-A2 (revisión de seguridad M1): un ValueError ajeno no se vuelve «rechazo de --provider» ------


async def test_un_value_error_ajeno_de_la_rotacion_no_sale_2_ni_imprime_su_texto(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli_ops import rotate_key

    async def explota(*_a: object, **_k: object) -> None:
        raise ValueError("texto-del-proveedor-o-de-datos")

    monkeypatch.setattr(rotate_key, "_rotate_data", explota)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code != 2, resultado.output
    assert "texto-del-proveedor-o-de-datos" not in resultado.output


async def test_un_puerto_que_nunca_vacia_agota_las_pasadas_marca_failed_y_sale_1(
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S6-B1 (revisión de seguridad): `finish_rotation` no marca `failed` en el primer intento;
    el CLI reintenta y, al agotar `EMPTY_PASSES`, deja el job `failed` con `pending_records`."""
    from app.cli_ops import rotate_key as modulo
    from app.core.crypto import reencryptor as puerto_mod
    from tests.crypto.conftest import ReencryptorDoble

    doble = ReencryptorDoble(pendientes=4, migradas_por_lote=0)
    monkeypatch.setattr(puerto_mod, "_registered", {CLASE_ROTADA: doble})
    esperas: list[float] = []

    async def sin_dormir(segundos: float, *args: object) -> None:
        esperas.append(segundos)

    monkeypatch.setattr(asyncio, "sleep", sin_dormir)

    resultado = _rotar(
        settings_prueba, monkeypatch, CLASE_ROTADA, "--reason", MOTIVO, "--as", admin.email
    )

    assert resultado.exit_code == 1, resultado.output
    assert "quedan filas con la llave anterior" in resultado.output
    assert doble.nombres().count("count_pending") >= modulo.EMPTY_PASSES
    jobs = await _jobs(rotacion_lista)
    assert [(j.status, j.error) for j in jobs] == [("failed", "pending_records")]
    assert await _llaves(rotacion_lista) == [(1, "decrypt_only"), (2, "active")]


@pytest.mark.parametrize("cantidad", [25, 60])
async def test_rotate_key_de_attachment_sensitive_sale_0_con_el_puerto_real(
    cantidad: int,
    settings_prueba: Settings,
    rotacion_lista: Fabrica,
    engine: Any,
    admin: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S6-R1 (S6-D26, E5): con el puerto `Reencryptor` real registrado por `cli_runtime`, el CLI y
    la pantalla comparten `run_rotation`; rotar `attachment.sensitive` sale 0 y recifra los
    objetos (antes de C1 salía 2 `rotation_not_supported`). Con 60 (> 50) cubre el defecto de V11:
    el CLI pedía lotes de 500, el puerto migraba 10 y cada lote contaba como pasada vacía."""
    from uuid import uuid4

    from sqlalchemy import text

    from app.modules.attachments import service as adjuntos
    from app.modules.attachments.storage.local import LocalDiskStorage
    from tests.attachments._apoyo import subir_real
    from tests.conftest import LIMPIAR_ATTACHMENTS
    from tests.factories import files

    uploads = tmp_path / "uploads"
    raiz = uploads / "attachments"
    raiz.mkdir(parents=True)
    ajustes = settings_prueba.model_copy(update={"UPLOADS_DIR": uploads})
    adjuntos.configure_storage(LocalDiskStorage(raiz))
    try:
        for _ in range(cantidad):
            await subir_real(rotacion_lista, uuid4(), "consent", files.pdf(2000))

        resultado = _rotar(
            ajustes, monkeypatch, "attachment.sensitive", "--reason", MOTIVO, "--as", admin.email
        )

        assert resultado.exit_code == 0, resultado.output
        assert f"rotate-key: total={cantidad}" in resultado.output
        assert FINAL in resultado.output
        async with rotacion_lista() as sesion:
            llaves = await llaves_de(sesion, "encrypt", "attachment.sensitive")
            nueva = llaves[-1].id
            sin_actualizar = await sesion.scalar(
                text("SELECT count(*) FROM attachments.attachments WHERE key_id <> :k"),
                {"k": nueva},
            )
        assert _estados(llaves) == [(1, "decrypt_only"), (2, "active")]
        assert sin_actualizar == 0
    finally:
        adjuntos.configure_storage(None)
        async with engine.begin() as conexion:
            await conexion.execute(text(LIMPIAR_ATTACHMENTS))
