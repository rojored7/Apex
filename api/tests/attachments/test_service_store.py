"""`attachments.service.store` (S6-C1, US-147; S6-D22, S6-D25, S6-D59, S6-D75, S6-D84, E1, L-1, M-3,
M-4, M-9).

Cubre: cifrado de los sensibles por el bus (objeto `apx1.`, `key_id` del blob, `crypto_ops(encrypt)`
con `record_id = id`, `aad = aad_for(id)`), la foto en claro, el rechazo por bytes mágicos, el
tope exacto de 5 MiB leyendo (el iterador contado y el infinito no cuelgan), el tiempo máximo de
subida (408), nada en `tempfile`, pico de memoria, `put` fallido sin fila, borrado compensatorio
con log sin el nombre del archivo, semáforo global de 4 y la auditoría `insert` sin
`filename_random` ni `key_id`.

Contratos que el Rojo asume (el Verde puede discutirlos):
- `service.configure_storage(storage)` fija el almacén del proceso (fixture `almacen`);
- el tiempo máximo de lectura se lee de `rules.ATTACHMENT_UPLOAD_TIMEOUT_S` en cada llamada;
- `put` fallido → `StorageUnavailable` (503); `put` ocurre ANTES del `flush` (D22 paso 6);
- el semáforo se retiene desde antes de cifrar hasta que el objeto está guardado; el excedente
  lanza `DatabaseBusy` (503 `busy`, `Retry-After: 1`) sin esperar; la foto no lo usa.
"""

from __future__ import annotations

import asyncio
import logging
import time
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.crypto import bus
from app.core.crypto.blob import parse_blob
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy
from app.modules.attachments import rules, service
from app.modules.attachments.exceptions import (
    FileTooLarge,
    StorageUnavailable,
    UnsupportedType,
    UploadTimeout,
)
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, filas_de_auditoria, ops_de, subir, subir_real
from tests.attachments.conftest import Fabrica
from tests.factories import files

DATA_CLASS = "attachment.sensitive"


def _objeto(almacen: LocalDiskStorage, row: dict[str, Any]) -> bytes:
    return (almacen.root / row["filename_random"]).read_bytes()


def _archivos(almacen: LocalDiskStorage) -> list[str]:
    return sorted(p.name for p in almacen.root.iterdir())


async def _conteo(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM attachments.attachments")) or 0)


class Espia(LocalDiskStorage):
    """Un almacén local que anota sus operaciones y puede fallar o bloquear."""

    def __init__(self, raiz: Path) -> None:
        super().__init__(raiz)
        self.operaciones: list[tuple[str, str]] = []
        self.falla_en_put: Exception | None = None
        self.bloqueo: asyncio.Event | None = None
        self.dentro = 0

    async def put(self, key: str, data: bytes) -> None:
        self.operaciones.append(("put", key))
        if self.falla_en_put is not None:
            raise self.falla_en_put
        if self.bloqueo is not None and data.startswith(b"apx1."):
            self.dentro += 1
            await self.bloqueo.wait()
        await super().put(key, data)

    async def delete_object(self, key: str) -> None:
        self.operaciones.append(("delete_object", key))
        await super().delete_object(key)


@pytest.fixture
def espia(tmp_path: Path) -> Iterator[Espia]:
    raiz = tmp_path / "espia"
    raiz.mkdir()
    almacen = Espia(raiz)
    service.configure_storage(almacen)
    try:
        yield almacen
    finally:
        service.configure_storage(None)


# Sensible ----------------------------------------------------------------------------------------


async def test_un_sensible_se_guarda_cifrado_y_sin_los_bytes_originales(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    pdf = files.pdf(8192)

    adjunto = await subir(listo, por, "consent", pdf)

    row = await fila(listo, adjunto.id)
    objeto = _objeto(almacen, row)
    assert objeto.startswith(b"apx1.")
    assert files.MARCA_PDF not in objeto and pdf[:64] not in objeto
    assert (row["kind"], row["sensitive"], row["mime"]) == ("consent", True, "application/pdf")
    assert (row["size_bytes"], row["storage_provider"]) == (len(pdf), "local")
    assert (row["uploaded_by"], row["created_by"]) == (por, por)
    assert len(row["filename_random"]) == 32 and set(row["filename_random"]) <= set(
        "0123456789abcdef"
    )


async def test_el_key_id_sale_del_blob_y_es_el_de_la_llave_activa(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID, bus_listo: Keyring
) -> None:
    adjunto = await subir(listo, por, "other", files.png(4096))

    row = await fila(listo, adjunto.id)
    del_blob = parse_blob(_objeto(almacen, row).decode("ascii")).key_id
    assert row["key_id"] == del_blob
    assert row["key_id"] == bus_listo.active_for("encrypt", DATA_CLASS).key_id


async def test_el_aad_del_cifrado_es_el_id_de_la_fila(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    pdf = files.pdf(4096)
    adjunto = await subir(listo, por, "consent", pdf)
    blob = _objeto(almacen, await fila(listo, adjunto.id)).decode("ascii")

    assert bus.decrypt(blob, bus.aad_for(adjunto.id)) == pdf
    with pytest.raises(CryptoError):
        bus.decrypt(blob, bus.aad_for(uuid4()))  # el objeto no sirve para otro registro


async def test_el_sensible_deja_un_crypto_ops_encrypt_con_record_id_igual_al_id(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "consent", files.pdf(2048))

    async with real() as sesion:
        ops = await ops_de(sesion, "encrypt", adjunto.id)
        key_id = (await fila(sesion, adjunto.id))["key_id"]
    assert len(ops) == 1
    assert (ops[0]["result"], ops[0]["key_id"], ops[0]["user_id"]) == ("ok", key_id, por)


# Foto --------------------------------------------------------------------------------------------


async def test_la_foto_se_guarda_en_claro_sin_key_id_y_sin_crypto_ops(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    jpg = files.jpeg(3000)

    adjunto = await subir_real(real, por, "photo", jpg)

    async with real() as sesion:
        row = await fila(sesion, adjunto.id)
        assert await ops_de(sesion, "encrypt", adjunto.id) == []
    assert _objeto(almacen, row) == jpg
    assert (row["sensitive"], row["key_id"], row["mime"]) == (False, None, "image/jpeg")


async def test_el_tipo_lo_deciden_los_bytes_no_el_nombre(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    """Un ELF presentado como foto (`.jpg`) no es imagen: 422 `unsupported_type`, nada escrito."""
    antes = await _conteo(listo)

    with pytest.raises(UnsupportedType) as error:
        await subir(listo, por, "photo", files.elf())

    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "unsupported_type",
        "file",
    )
    assert _archivos(almacen) == []
    assert await _conteo(listo) == antes


@pytest.mark.parametrize(
    ("kind", "datos"),
    [pytest.param("photo", files.pdf(), id="pdf"), pytest.param("photo", files.pe(), id="pe")],
)
async def test_la_foto_rechaza_pdf_y_ejecutables(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID, kind: str, datos: bytes
) -> None:
    with pytest.raises(UnsupportedType):
        await subir(listo, por, kind, datos)
    assert _archivos(almacen) == []


# Tope de 5 MiB leyendo ---------------------------------------------------------------------------


async def test_el_tope_exacto_se_acepta(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir(listo, por, "photo", files.jpeg(files.TOPE))

    assert (await fila(listo, adjunto.id))["size_bytes"] == 5_242_880


async def test_un_byte_mas_es_file_too_large_413_y_no_se_escribe_nada(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    antes = await _conteo(listo)

    with pytest.raises(FileTooLarge) as error:
        await subir(listo, por, "photo", files.jpeg(files.TOPE_MAS_UNO))

    assert (error.value.status, error.value.code, error.value.field) == (
        413,
        "file_too_large",
        "file",
    )
    assert _archivos(almacen) == []
    assert await _conteo(listo) == antes


@pytest.mark.parametrize("trozo", [65536, 1024, 5_242_880])
async def test_el_lector_corta_en_el_primer_trozo_que_cruza_el_limite(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID, trozo: int
) -> None:
    """Un iterador contado de 10 MiB: nunca se consume más allá del trozo que pasa de 5.242.881."""
    cuerpo = files.Contado(files.jpeg(10 * 1024 * 1024), tam=trozo)

    with actor_scope(por), pytest.raises(FileTooLarge):
        await service.store(
            listo, owner_table="members", owner_id=uuid4(), kind="photo", chunks=cuerpo, by=por
        )

    esperados = -(-rules.ATTACHMENT_READ_LIMIT // trozo)  # ceil
    assert cuerpo.trozos == esperados, (cuerpo.trozos, esperados)
    assert cuerpo.bytes_entregados < rules.ATTACHMENT_READ_LIMIT + trozo
    assert _archivos(almacen) == []


async def test_un_iterador_infinito_no_cuelga_y_corta_con_413(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    cuerpo = files.Infinito(files.jpeg(64))

    with actor_scope(por), pytest.raises(FileTooLarge):
        await asyncio.wait_for(
            service.store(
                listo, owner_table="members", owner_id=uuid4(), kind="photo", chunks=cuerpo, by=por
            ),
            timeout=20,
        )

    assert cuerpo.bytes_entregados <= rules.ATTACHMENT_READ_LIMIT + 65536
    assert _archivos(almacen) == []


# Tiempo máximo de subida (S6-D84) ----------------------------------------------------------------


async def test_un_cliente_que_manda_un_trozo_y_calla_da_408_upload_timeout_sin_escribir(
    listo: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rules, "ATTACHMENT_UPLOAD_TIMEOUT_S", 0.3)
    cuerpo = files.Lento(files.jpeg(512), espera_s=60)
    antes = await _conteo(listo)

    inicio = time.monotonic()
    with actor_scope(por), pytest.raises(UploadTimeout) as error:
        await service.store(
            listo, owner_table="members", owner_id=uuid4(), kind="photo", chunks=cuerpo, by=por
        )

    assert time.monotonic() - inicio < 10, "la espera no respetó el tiempo máximo"
    assert (error.value.status, error.value.code) == (408, "upload_timeout")
    assert cuerpo.espero_de_mas is False  # se canceló la lectura, no se esperó el segundo trozo
    assert _archivos(almacen) == []
    assert await _conteo(listo) == antes
    assert await filas_de_auditoria(listo, "insert") == []


async def test_el_tiempo_maximo_es_total_no_por_trozo(
    listo: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un goteo (un byte cada 50 ms) no esquiva el límite aunque cada trozo llegue a tiempo."""
    monkeypatch.setattr(rules, "ATTACHMENT_UPLOAD_TIMEOUT_S", 0.4)

    async def goteo() -> Any:
        yield files.jpeg(32)
        while True:
            await asyncio.sleep(0.05)
            yield b"\x00"

    with actor_scope(por), pytest.raises(UploadTimeout):
        await asyncio.wait_for(
            service.store(
                listo,
                owner_table="members",
                owner_id=uuid4(),
                kind="photo",
                chunks=goteo(),
                by=por,
            ),
            timeout=20,
        )
    assert _archivos(almacen) == []


async def test_una_subida_normal_no_se_ve_afectada_por_el_tiempo_maximo(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    assert rules.ATTACHMENT_UPLOAD_TIMEOUT_S == 30
    adjunto = await subir(listo, por, "photo", files.png(4096))
    assert (await fila(listo, adjunto.id))["size_bytes"] == 4096


# Nada de tempfile ni de memoria de más -----------------------------------------------------------


@pytest.mark.usefixtures("sin_tempfile")
@pytest.mark.parametrize(
    ("kind", "datos"),
    [
        pytest.param("photo", files.jpeg(300_000), id="foto"),
        pytest.param("consent", files.pdf(300_000), id="sensible"),
    ],
)
async def test_la_subida_no_usa_tempfile(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID, kind: str, datos: bytes
) -> None:
    adjunto = await subir(listo, por, kind, datos)
    assert (await fila(listo, adjunto.id))["size_bytes"] == len(datos)


async def test_el_pico_de_memoria_de_una_subida_sensible_de_5_mib_queda_bajo_26_mib(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    datos = files.pdf(files.TOPE)
    tracemalloc.start()
    try:
        base, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        await subir(listo, por, "consent", datos)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Medido 23,3 MiB (decisión del slice, orquestador 5): el piso lo fija `core/crypto` (contenido,
    # texto cifrado y las copias base64url del blob de 7 MiB); `files.py` no puede acortarlo.
    assert pico - base < 26 * 1024 * 1024, f"pico {(pico - base) / 1024 / 1024:.1f} MiB"


# Fallas del almacén ------------------------------------------------------------------------------


async def test_si_put_falla_no_queda_fila_ni_auditoria_ni_objeto(
    listo: AsyncSession, espia: Espia, por: UUID
) -> None:
    espia.falla_en_put = OSError("disco lleno")
    antes, auditorias = await _conteo(listo), len(await filas_de_auditoria(listo, "insert"))

    with pytest.raises(StorageUnavailable) as error:
        await subir(listo, por, "photo", files.jpeg())

    assert error.value.status == 503
    assert await _conteo(listo) == antes
    assert len(await filas_de_auditoria(listo, "insert")) == auditorias
    assert [op for op, _ in espia.operaciones] == ["put"]  # nada que compensar


async def test_si_el_flush_falla_despues_de_put_se_borra_el_objeto_y_el_log_no_trae_el_nombre(
    listo: AsyncSession,
    espia: Espia,
    por: UUID,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def flush_roto(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("flush roto")

    monkeypatch.setattr(listo, "flush", flush_roto)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(RuntimeError, match="flush roto"):
        await subir(listo, por, "photo", files.jpeg())

    puestos = [k for op, k in espia.operaciones if op == "put"]
    borrados = [k for op, k in espia.operaciones if op == "delete_object"]
    assert len(puestos) == 1 and borrados == puestos  # compensación del mismo objeto
    assert [p.name for p in espia.root.iterdir()] == []
    assert caplog.records, "la compensación debe dejar un log"
    for registro in caplog.records:
        assert puestos[0] not in registro.getMessage(), "el log no puede nombrar el archivo"
        assert puestos[0] not in str(registro.__dict__.get("args", ""))


# Semáforo global de 4 operaciones sensibles (S6-D59, M-3) --------------------------------


async def test_la_quinta_operacion_sensible_concurrente_da_503_busy_con_retry_after_1(
    real: Fabrica, espia: Espia, por: UUID
) -> None:
    assert service.SENSITIVE_SLOTS == 4
    espia.bloqueo = asyncio.Event()

    async def subir_sensible() -> UUID:
        return (await subir_real(real, por, "consent", files.pdf(2048))).id

    tareas = [asyncio.create_task(subir_sensible()) for _ in range(service.SENSITIVE_SLOTS)]
    try:
        for _ in range(200):  # hasta ~10 s; cada una queda dentro de `put` con el cupo tomado
            if espia.dentro == service.SENSITIVE_SLOTS:
                break
            await asyncio.sleep(0.05)
        assert espia.dentro == service.SENSITIVE_SLOTS

        inicio = time.monotonic()
        with pytest.raises(DatabaseBusy) as error:
            await subir_real(real, por, "consent", files.pdf(2048))
        assert time.monotonic() - inicio < 2, "el excedente no debe esperar"
        assert (error.value.status, error.value.code) == (503, "busy")
        assert error.value.headers["Retry-After"] == "1"

        foto = await asyncio.wait_for(subir_real(real, por, "photo", files.jpeg()), timeout=10)
        assert foto.sensitive is False  # la foto no usa el semáforo
    finally:
        espia.bloqueo.set()
    ids = await asyncio.wait_for(asyncio.gather(*tareas), timeout=20)
    assert len(set(ids)) == 4
    otra = await subir_real(real, por, "consent", files.pdf(2048))  # el cupo se liberó
    assert otra.sensitive is True


async def test_el_cupo_se_libera_aunque_la_subida_falle(
    listo: AsyncSession, espia: Espia, por: UUID
) -> None:
    espia.falla_en_put = OSError("x")
    for _ in range(service.SENSITIVE_SLOTS + 2):
        with pytest.raises(StorageUnavailable):
            await subir(listo, por, "consent", files.pdf(1024))
    espia.falla_en_put = None
    assert (await subir(listo, por, "consent", files.pdf(1024))).sensitive is True


# Auditoría (L-1, S6-D75) -------------------------------------------------------------------------


async def test_la_auditoria_insert_lleva_uploaded_by_y_no_filename_random_ni_key_id(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    dueno = uuid4()
    adjunto = await subir_real(real, por, "consent", files.pdf(2048), dueno=dueno)

    async with real() as sesion:
        (insertar,) = await filas_de_auditoria(sesion, "insert")
        row = await fila(sesion, adjunto.id)
    despues = insertar["after"]
    assert insertar["record_id"] == adjunto.id and insertar["user_id"] == por
    assert insertar["subject_member_id"] == dueno
    assert despues["uploaded_by"] == str(por)
    assert (despues["kind"], despues["sensitive"], despues["mime"]) == (
        "consent",
        True,
        "application/pdf",
    )
    assert despues["owner_id"] == str(dueno) and despues["size_bytes"] == 2048
    assert "filename_random" not in despues and "key_id" not in despues
    assert row["filename_random"] not in str(insertar) and str(row["key_id"]) not in str(insertar)


async def test_la_foto_se_audita_con_insert_pero_no_deja_fila_download(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    await subir_real(real, por, "photo", files.jpeg())
    async with real() as sesion:
        assert len(await filas_de_auditoria(sesion, "insert")) == 1
        assert await filas_de_auditoria(sesion, "download") == []


async def test_store_sin_filas_extra_una_fila_por_subida(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    await subir_real(real, por, "photo", files.jpeg())
    await subir_real(real, por, "other", files.png())
    async with real() as sesion:
        total = await sesion.scalar(
            select(func.count()).select_from(text("attachments.attachments"))
        )
        assert total == 2
        assert len(await filas_de_auditoria(sesion, "insert")) == 2
