"""Contrato del puerto `StorageProvider` (S6-C1, US-147; S6-D21, S6-D26, S6-D60, M-9).

La misma suite corre contra `LocalDiskStorage` y contra `S3CompatibleStorage`. El segundo usa
`botocore.stub.Stubber` sobre un cliente real con credenciales falsas (sin red); `botocore.stub`
viene del extra `s3` de `pyproject`: si no está instalado, las pruebas de S3 se saltan con motivo.

Contrato que el Rojo asume (el Verde puede discutirlo):
- la clave es siempre `^[0-9a-f]{32}$` con `fullmatch` (un `\\n` final también se rechaza) y toda
  operación con una clave inválida lanza `ValueError` ANTES de tocar disco o red;
- `get` de una clave ausente lanza `FileNotFoundError` (local y S3 `NoSuchKey`);
- `stream` entrega trozos de `chunk_size` (64 KiB por omisión) y el último más corto;
- `list_keys()` (iterador asíncrono) devuelve las claves guardadas sin temporales ni ajenas: lo
  necesita `attachments-check` para hallar objetos sin fila;
- S3: el cliente sale de `boto3.client(...)` con credenciales explícitas (`aws_access_key_id`,
  `aws_secret_access_key`), `endpoint_url`, `region_name`, `verify=True` y
  `config=Config(proxies={}, retries={"max_attempts": 3})`; la `Key` del objeto es la clave tal
  cual (sin prefijo) y el bucket es `S3_BUCKET`.
- local: raíz `UPLOADS_DIR/attachments`; temporal en la MISMA carpeta, `fsync`, `os.replace`, modo
  600; todo I/O dentro de `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import io
import os
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.attachments.storage.base import CHUNK_SIZE
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo_s3 import ACCESO, BUCKET, SECRETO, settings_s3

CLAVE = "0123456789abcdef0123456789abcdef"
OTRA = "fedcba9876543210fedcba9876543210"

INVALIDAS = [
    "../x",
    "../../etc/passwd",
    "ABCDEF0123456789ABCDEF0123456789",
    "0123456789abcdef0123456789abcde",  # 31 hex
    "0123456789abcdef0123456789abcdef0",  # 33 hex
    "0123456789abcdef/123456789abcdef",
    "0123456789abcdef0123456789abcde/",
    "0123456789abcdef0123456789abcdef\n",
    "",
    "g123456789abcdef0123456789abcdef",
    "a/../../../../etc/passwd",
]


class Motor:
    """Un almacenamiento bajo prueba y cómo se prepara el mundo de cada operación."""

    nombre: str
    almacen: Any

    def espera_put(self, clave: str, datos: bytes) -> None: ...

    def espera_get(self, clave: str, datos: bytes) -> None: ...

    def espera_get_ausente(self, clave: str) -> None: ...

    def espera_exists(self, clave: str, existe: bool) -> None: ...

    def espera_delete(self, clave: str) -> None: ...

    def espera_list(self, claves: list[str]) -> None: ...

    def sembrar(self, clave: str, datos: bytes) -> None: ...

    def verificar(self) -> None: ...


class MotorLocal(Motor):
    nombre = "local"

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.almacen = LocalDiskStorage(raiz)

    def espera_put(self, clave: str, datos: bytes) -> None:
        return None

    espera_get = espera_put  # type: ignore[assignment]

    def espera_get_ausente(self, clave: str) -> None:
        return None

    def espera_exists(self, clave: str, existe: bool) -> None:
        return None

    def espera_delete(self, clave: str) -> None:
        return None

    def espera_list(self, claves: list[str]) -> None:
        return None

    def sembrar(self, clave: str, datos: bytes) -> None:
        (self.raiz / clave).write_bytes(datos)

    def verificar(self) -> None:
        return None


class MotorS3(Motor):
    nombre = "s3"

    def __init__(self, cliente: Any, almacen: Any, stubber: Any) -> None:
        self.cliente, self.almacen, self.stubber = cliente, almacen, stubber

    def espera_put(self, clave: str, datos: bytes) -> None:
        self.stubber.add_response("put_object", {}, {"Bucket": BUCKET, "Key": clave, "Body": datos})

    def _cuerpo(self, datos: bytes) -> dict[str, Any]:
        from botocore.response import StreamingBody

        return {"Body": StreamingBody(io.BytesIO(datos), len(datos)), "ContentLength": len(datos)}

    def espera_get(self, clave: str, datos: bytes) -> None:
        self.stubber.add_response(
            "get_object", self._cuerpo(datos), {"Bucket": BUCKET, "Key": clave}
        )

    def espera_get_ausente(self, clave: str) -> None:
        self.stubber.add_client_error(
            "get_object", service_error_code="NoSuchKey", http_status_code=404
        )

    def espera_exists(self, clave: str, existe: bool) -> None:
        if existe:
            self.stubber.add_response("head_object", {}, {"Bucket": BUCKET, "Key": clave})
        else:
            self.stubber.add_client_error(
                "head_object", service_error_code="404", http_status_code=404
            )

    def espera_delete(self, clave: str) -> None:
        self.stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": clave})

    def espera_list(self, claves: list[str]) -> None:
        self.stubber.add_response(
            "list_objects_v2",
            {
                "Contents": [{"Key": k} for k in claves],
                "IsTruncated": False,
                "KeyCount": len(claves),
            },
            {"Bucket": BUCKET},
        )

    def sembrar(self, clave: str, datos: bytes) -> None:
        return None  # en S3 el mundo lo fija cada `espera_*`

    def verificar(self) -> None:
        self.stubber.assert_no_pending_responses()


@pytest.fixture(params=["local", "s3"])
def motor(
    request: pytest.FixtureRequest, tmp_path: Path, settings_prueba: Settings, monkeypatch: Any
) -> Motor:
    if request.param == "local":
        raiz = tmp_path / "attachments"
        raiz.mkdir()
        return MotorLocal(raiz)
    espiado = request.getfixturevalue("cliente_s3_espiado")
    from app.modules.attachments.storage.s3 import S3CompatibleStorage

    almacen = S3CompatibleStorage(settings_s3(settings_prueba))
    return MotorS3(espiado["cliente"], almacen, espiado["stubber"])


async def _todo(iterador: Any) -> list[Any]:
    return [x async for x in iterador]


# Contrato común ----------------------------------------------------------------------------------


async def test_put_y_get_devuelven_los_mismos_bytes(motor: Motor) -> None:
    datos = os.urandom(5000)
    motor.espera_put(CLAVE, datos)
    motor.espera_get(CLAVE, datos)

    await motor.almacen.put(CLAVE, datos)

    assert await motor.almacen.get(CLAVE) == datos
    motor.verificar()


async def test_put_dos_veces_con_la_misma_clave_reemplaza_el_contenido(motor: Motor) -> None:
    """Lo usa el recifrado (`reencrypt_batch` reemplaza el objeto con la misma clave)."""
    motor.espera_put(CLAVE, b"uno")
    motor.espera_put(CLAVE, b"dos")
    motor.espera_get(CLAVE, b"dos")

    await motor.almacen.put(CLAVE, b"uno")
    await motor.almacen.put(CLAVE, b"dos")

    assert await motor.almacen.get(CLAVE) == b"dos"
    motor.verificar()


async def test_get_de_una_clave_ausente_lanza_file_not_found(motor: Motor) -> None:
    motor.espera_get_ausente(OTRA)

    with pytest.raises(FileNotFoundError):
        await motor.almacen.get(OTRA)
    motor.verificar()


@pytest.mark.parametrize("existe", [True, False])
async def test_exists(motor: Motor, existe: bool) -> None:
    if existe:
        motor.espera_put(CLAVE, b"x")
        await motor.almacen.put(CLAVE, b"x")
    motor.espera_exists(CLAVE, existe)

    assert await motor.almacen.exists(CLAVE) is existe
    motor.verificar()


async def test_stream_entrega_trozos_de_64_kib_y_el_ultimo_mas_corto(motor: Motor) -> None:
    datos = os.urandom(CHUNK_SIZE * 2 + 1234)
    motor.espera_put(CLAVE, datos)
    motor.espera_get(CLAVE, datos)

    await motor.almacen.put(CLAVE, datos)
    trozos = await _todo(motor.almacen.stream(CLAVE))

    assert CHUNK_SIZE == 65536
    assert [len(t) for t in trozos] == [CHUNK_SIZE, CHUNK_SIZE, 1234]
    assert b"".join(trozos) == datos
    motor.verificar()


async def test_stream_acepta_otro_tamano_de_trozo(motor: Motor) -> None:
    datos = os.urandom(10_000)
    motor.espera_put(CLAVE, datos)
    motor.espera_get(CLAVE, datos)
    await motor.almacen.put(CLAVE, datos)

    trozos = await _todo(motor.almacen.stream(CLAVE, chunk_size=4096))

    assert [len(t) for t in trozos] == [4096, 4096, 1808]
    motor.verificar()


async def test_stream_de_una_clave_ausente_lanza_file_not_found(motor: Motor) -> None:
    motor.espera_get_ausente(OTRA)

    with pytest.raises(FileNotFoundError):
        await _todo(motor.almacen.stream(OTRA))
    motor.verificar()


async def test_delete_object_quita_el_objeto(motor: Motor) -> None:
    motor.espera_put(CLAVE, b"x")
    motor.espera_delete(CLAVE)
    motor.espera_exists(CLAVE, False)
    await motor.almacen.put(CLAVE, b"x")

    await motor.almacen.delete_object(CLAVE)

    assert await motor.almacen.exists(CLAVE) is False
    motor.verificar()


async def test_list_keys_devuelve_solo_las_claves_guardadas(motor: Motor) -> None:
    motor.espera_put(CLAVE, b"1")
    motor.espera_put(OTRA, b"2")
    motor.espera_list([CLAVE, OTRA])
    await motor.almacen.put(CLAVE, b"1")
    await motor.almacen.put(OTRA, b"2")

    claves = await _todo(motor.almacen.list_keys())

    assert sorted(claves) == sorted([CLAVE, OTRA])
    motor.verificar()


@pytest.mark.parametrize("clave", INVALIDAS)
@pytest.mark.parametrize("operacion", ["put", "get", "exists", "delete_object", "stream"])
async def test_una_clave_invalida_lanza_value_error_sin_tocar_disco_ni_red(
    motor: Motor, tmp_path: Path, operacion: str, clave: str
) -> None:
    antes = _arbol(tmp_path)

    with pytest.raises(ValueError):
        if operacion == "put":
            await motor.almacen.put(clave, b"x")
        elif operacion == "stream":
            await _todo(motor.almacen.stream(clave))
        else:
            await getattr(motor.almacen, operacion)(clave)

    despues = _arbol(tmp_path)
    assert despues == antes
    motor.verificar()  # sin respuestas pendientes ni llamadas inesperadas al Stubber


# Específico de local -----------------------------------------------------------------------------


@pytest.fixture
def local(tmp_path: Path) -> LocalDiskStorage:
    raiz = tmp_path / "attachments"
    raiz.mkdir()
    return LocalDiskStorage(raiz)


async def test_local_put_deja_un_solo_archivo_sin_temporales(local: LocalDiskStorage) -> None:
    await local.put(CLAVE, b"contenido")

    assert sorted(p.name for p in local.root.iterdir()) == [CLAVE]
    assert (local.root / CLAVE).read_bytes() == b"contenido"


@pytest.mark.skipif(sys.platform == "win32", reason="los modos POSIX no existen en NTFS")
async def test_local_put_crea_el_archivo_con_modo_600(local: LocalDiskStorage) -> None:
    await local.put(CLAVE, b"contenido")

    assert stat.S_IMODE((local.root / CLAVE).stat().st_mode) == 0o600


async def test_local_escribe_un_temporal_en_la_misma_carpeta_hace_fsync_y_os_replace(
    local: LocalDiskStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    reemplazos: list[tuple[str, str]] = []
    sincronizados: list[int] = []
    original_replace, original_fsync = os.replace, os.fsync

    def replace(origen: Any, destino: Any, *a: Any, **k: Any) -> None:
        reemplazos.append((os.fspath(origen), os.fspath(destino)))
        original_replace(origen, destino, *a, **k)

    def fsync(fd: int) -> None:
        sincronizados.append(fd)
        original_fsync(fd)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "fsync", fsync)

    await local.put(CLAVE, b"contenido")

    assert len(reemplazos) == 1
    origen, destino = map(Path, reemplazos[0])
    assert destino == local.root / CLAVE
    assert origen.parent == destino.parent == local.root  # misma carpeta: rename atómico
    assert origen.name != CLAVE
    assert sincronizados, "el contenido debe llegar a disco (fsync) antes del os.replace"


async def test_local_si_falla_el_reemplazo_no_queda_ni_el_objeto_ni_el_temporal(
    local: LocalDiskStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falla(*_a: Any, **_k: Any) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", falla)

    with pytest.raises(OSError):
        await local.put(CLAVE, b"contenido")

    assert list(local.root.iterdir()) == []


async def test_local_si_falla_un_reemplazo_el_objeto_anterior_queda_intacto(
    local: LocalDiskStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    await local.put(CLAVE, b"version-uno")

    def falla(*_a: Any, **_k: Any) -> None:
        raise OSError("corte")

    monkeypatch.setattr(os, "replace", falla)
    with pytest.raises(OSError):
        await local.put(CLAVE, b"version-dos")

    assert (local.root / CLAVE).read_bytes() == b"version-uno"
    assert [p.name for p in local.root.iterdir()] == [CLAVE]


async def test_local_todo_el_io_va_por_asyncio_to_thread(
    local: LocalDiskStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []
    original: Callable[..., Any] = asyncio.to_thread

    async def espia(funcion: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        llamadas.append(getattr(funcion, "__name__", repr(funcion)))
        return await original(funcion, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", espia)

    await local.put(CLAVE, b"x" * 100)
    n_put = len(llamadas)
    await local.get(CLAVE)
    n_get = len(llamadas)
    await local.exists(CLAVE)
    n_exists = len(llamadas)
    await _todo(local.stream(CLAVE))
    n_stream = len(llamadas)
    await local.delete_object(CLAVE)
    n_delete = len(llamadas)

    assert 0 < n_put < n_get < n_exists < n_stream < n_delete, llamadas


async def test_local_list_keys_ignora_temporales_y_archivos_ajenos(
    local: LocalDiskStorage,
) -> None:
    await local.put(CLAVE, b"x")
    (local.root / ".tmp-parcial").write_bytes(b"x")
    (local.root / "README.txt").write_bytes(b"x")

    assert await _todo(local.list_keys()) == [CLAVE]


# Específico de S3 --------------------------------------------------------------------------------


def test_s3_construye_el_cliente_con_credenciales_explicitas_https_config_y_verify(
    cliente_s3_espiado: dict[str, Any],
    settings_prueba: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nunca la cadena de credenciales por defecto: las variables `AWS_*` y `~/.aws/credentials`
    falsos NO se usan (la clave y el secreto salen de `Settings`)."""
    from botocore.config import Config

    from app.modules.attachments.storage.s3 import S3CompatibleStorage

    casa = tmp_path / "casa"
    (casa / ".aws").mkdir(parents=True)
    (casa / ".aws" / "credentials").write_text(
        "[default]\naws_access_key_id = DEL_ARCHIVO_NO\naws_secret_access_key = DEL_ARCHIVO_NO\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "DEL_ENTORNO_NO")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "DEL_ENTORNO_NO")
    monkeypatch.setenv("AWS_PROFILE", "otro")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(casa / ".aws" / "credentials"))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalido:3128")

    S3CompatibleStorage(settings_s3(settings_prueba))

    ((servicio, _args, kw),) = cliente_s3_espiado["llamadas"]
    assert servicio == "s3"
    assert kw["aws_access_key_id"] == ACCESO
    assert kw["aws_secret_access_key"] == SECRETO
    assert str(kw["endpoint_url"]).startswith("https://")
    assert kw["region_name"] == "us-east-1"
    assert kw.get("verify", True) is True
    config = kw["config"]
    assert isinstance(config, Config)
    assert config.proxies == {}
    assert config.retries == {"max_attempts": 3}
    assert "DEL_" not in repr(kw)


def test_s3_no_registra_el_secreto_en_su_repr(
    cliente_s3_espiado: dict[str, Any], settings_prueba: Settings
) -> None:
    from app.modules.attachments.storage.s3 import S3CompatibleStorage

    almacen = S3CompatibleStorage(settings_s3(settings_prueba))

    assert SECRETO not in repr(almacen) and SECRETO not in str(almacen)


@pytest.fixture(autouse=True)
def _sin_estado_de_boto(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Las pruebas de S3 no deben heredar `AWS_*` reales de la máquina."""
    for nombre in list(os.environ):
        if nombre.startswith("AWS_"):
            monkeypatch.delenv(nombre, raising=False)
    yield


def _arbol(raiz: Path) -> list[str]:
    return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*"))
