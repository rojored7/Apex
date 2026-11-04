"""`core/crypto/archive.py`: respaldo de la KEK con `age -p` (S4B-B3a, US-116; S4B-D58, S4B-D89).

Con el `age` falso (`tests/factories/fake_age.py`; en Windows se omiten las pruebas que lo lanzan
porque `cmd.exe` no arranca con `env={}`, ver `age_falso`):
- `export_kek_file`: archivo nuevo con `O_EXCL|O_WRONLY` y modo 0o600 (se comprueban las banderas
  de `os.open` con un espía, también donde NTFS no guarda el modo), la KEK entra por `stdin` del
  hijo y nunca por `argv` ni por el entorno (`env == {}`), nada de `--passphrase*`;
- rechazos previos al hijo: ruta bajo `BACKUP_DIR`, ruta con enlace simbólico, KEK de tamaño
  incorrecto (el hijo ni se lanza);
- `restore_kek_file`: reproduce los 32 bytes, `O_EXCL`, 0o600 y nunca bajo el directorio de la KEK
  viva (`dirname(CRYPTO_LOCAL_KEK_PATH)`);
- sin terminal: `NoTty`; plazo agotado: `AgeTimeout` y el hijo muere; binario ausente:
  `AgeMissing` sin la ruta; `verify_kek_backup` exige exactamente 32 bytes (31 y 33 fallan).
`archive.get_settings` se reemplaza por un objeto con `BACKUP_DIR` y `CRYPTO_LOCAL_KEK_PATH`.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.crypto import archive
from app.core.crypto.archive import (
    AgeMissing,
    AgeTimeout,
    KekLengthInvalid,
    KekPathRejected,
    NoTty,
    VerifyKekResult,
    export_kek_file,
    restore_kek_file,
    verify_kek_backup,
)
from app.core.crypto.errors import CryptoError
from app.core.crypto.kek_backup import WrappedDek
from tests.crypto.conftest import entorno_visto
from tests.factories.fake_age import configurar, envolver_falso, latido, llamadas

SIN_AGE = "/no/hay/age"  # los rechazos previos nunca llegan a lanzarlo


@pytest.fixture
def carpetas(tmp_path: Path, kek_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """`BACKUP_DIR` (vacía) y "la KEK viva" (`kek_tmp`) como los ve `archive`."""
    respaldos = tmp_path / "backups"
    respaldos.mkdir()
    salidas = tmp_path / "salidas"
    salidas.mkdir()
    ajustes = SimpleNamespace(BACKUP_DIR=respaldos, CRYPTO_LOCAL_KEK_PATH=kek_tmp)
    monkeypatch.setattr(archive, "get_settings", lambda: ajustes)
    return SimpleNamespace(respaldos=respaldos, salidas=salidas)


@pytest.fixture
def aperturas(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, int]]:
    """Espía de `os.open`: `(ruta, banderas, modo)` de cada apertura."""
    real = os.open
    vistas: list[tuple[str, int, int]] = []

    def espia(path: Any, flags: int, mode: int = 0o777, **kw: Any) -> int:
        vistas.append((os.fspath(path), flags, mode))
        return real(path, flags, mode, **kw)

    monkeypatch.setattr(archive.os, "open", espia)
    return vistas


def _no_hay_kek_en(llamada: dict[str, Any], kek: bytes) -> None:
    visible = [*llamada["argv"], *entorno_visto(llamada).values()]
    candidatos = {kek.hex(), base64.b64encode(kek).decode(), base64.urlsafe_b64encode(kek).decode()}
    for elemento in visible:
        assert not any(c in elemento for c in candidatos)
        assert kek.decode("latin-1") not in elemento


def _respaldo(carpeta: Path, kek: bytes) -> Path:
    archivo = carpeta / "kek.age"
    archivo.write_bytes(envolver_falso(kek))
    return archivo


# export_kek_file -----------------------------------------------------------------------------


def test_export_cifra_la_kek_por_stdin_y_deja_el_archivo(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    salida = carpetas.salidas / "kek.age"

    export_kek_file(kek_tmp, salida)

    assert salida.read_bytes() == envolver_falso(kek_tmp.read_bytes())
    (llamada,) = llamadas(age_falso)
    assert "-p" in llamada["argv"]


def test_export_no_pasa_la_kek_por_argv_ni_por_el_entorno(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    export_kek_file(kek_tmp, carpetas.salidas / "kek.age")

    (llamada,) = llamadas(age_falso)
    assert entorno_visto(llamada) == {}
    _no_hay_kek_en(llamada, kek_tmp.read_bytes())
    assert not any(a.startswith("--passphrase") for a in llamada["argv"])
    assert str(kek_tmp) not in llamada["argv"]


def test_export_no_sobrescribe_un_archivo_existente(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    salida = carpetas.salidas / "kek.age"
    export_kek_file(kek_tmp, salida)
    primero = salida.read_bytes()

    with pytest.raises(FileExistsError):
        export_kek_file(kek_tmp, salida)

    assert salida.read_bytes() == primero


def test_export_crea_con_o_excl_o_wronly_y_modo_600(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    aperturas: list[tuple[str, int, int]],
) -> None:
    salida = carpetas.salidas / "kek.age"

    export_kek_file(kek_tmp, salida)

    propias = [(f, m) for ruta, f, m in aperturas if Path(ruta) == salida]
    assert len(propias) == 1
    banderas, modo = propias[0]
    assert banderas & os.O_EXCL and banderas & os.O_WRONLY and modo == 0o600
    if os.name != "nt":
        assert (salida.stat().st_mode & 0o777) == 0o600


def test_export_rechaza_una_salida_bajo_backup_dir_sin_lanzar_age(
    kek_tmp: Path, carpetas: SimpleNamespace
) -> None:
    destino = carpetas.respaldos / "kek.age"

    with pytest.raises(KekPathRejected) as excinfo:
        export_kek_file(kek_tmp, destino, age_binary=SIN_AGE)

    assert not destino.exists()
    assert str(carpetas.respaldos) not in str(excinfo.value)


def test_export_rechaza_una_salida_bajo_backup_dir_en_una_subcarpeta(
    kek_tmp: Path, carpetas: SimpleNamespace
) -> None:
    sub = carpetas.respaldos / "a" / "b"
    sub.mkdir(parents=True)

    with pytest.raises(KekPathRejected):
        export_kek_file(kek_tmp, sub / "kek.age", age_binary=SIN_AGE)


def test_export_rechaza_una_salida_que_es_un_enlace_simbolico(
    kek_tmp: Path, carpetas: SimpleNamespace
) -> None:
    objetivo = carpetas.salidas / "objetivo.bin"
    enlace = carpetas.salidas / "enlace.age"
    try:
        enlace.symlink_to(objetivo)
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    with pytest.raises((KekPathRejected, OSError)):
        export_kek_file(kek_tmp, enlace, age_binary=SIN_AGE)

    assert not objetivo.exists()


@pytest.mark.parametrize("tamano", [0, 31, 33])
def test_export_rechaza_una_kek_de_tamano_incorrecto_sin_lanzar_age(
    tmp_path: Path, carpetas: SimpleNamespace, tamano: int
) -> None:
    mala = tmp_path / "mala.bin"
    mala.write_bytes(os.urandom(tamano))
    mala.chmod(0o600)
    salida = carpetas.salidas / "kek.age"

    with pytest.raises(CryptoError) as excinfo:
        export_kek_file(mala, salida, age_binary=SIN_AGE)

    assert excinfo.value.code == "kek_invalid" and not salida.exists()


def test_export_con_la_kek_ausente_falla_sin_crear_la_salida(
    tmp_path: Path, carpetas: SimpleNamespace
) -> None:
    salida = carpetas.salidas / "kek.age"

    with pytest.raises(CryptoError) as excinfo:
        export_kek_file(tmp_path / "no-hay.bin", salida, age_binary=SIN_AGE)

    assert excinfo.value.code == "kek_missing" and not salida.exists()


def test_export_sin_terminal_lanza_notty(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    configurar(age_falso, no_tty=True)

    with pytest.raises(NoTty) as excinfo:
        export_kek_file(kek_tmp, carpetas.salidas / "kek.age")

    assert "/dev/tty" not in str(excinfo.value)  # mensaje fijo, sin texto del hijo


def test_export_con_plazo_agotado_mata_al_hijo(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    configurar(age_falso, dormir_s=30)
    inicio = time.monotonic()

    with pytest.raises(AgeTimeout):
        export_kek_file(kek_tmp, carpetas.salidas / "kek.age", timeout_s=1)

    assert time.monotonic() - inicio < 15
    if os.name != "nt":  # en Windows el `.cmd` deja huérfano al intérprete
        ultimo = latido(age_falso)
        time.sleep(0.6)
        assert latido(age_falso) == ultimo, "el hijo siguió vivo tras el plazo"


def test_export_con_binario_ausente_lanza_agemissing_sin_la_ruta(
    kek_tmp: Path, carpetas: SimpleNamespace, tmp_path: Path
) -> None:
    ausente = str(tmp_path / "secreto-de-ruta" / "age")

    with pytest.raises(AgeMissing) as excinfo:
        export_kek_file(kek_tmp, carpetas.salidas / "kek.age", age_binary=ausente)

    assert "secreto-de-ruta" not in str(excinfo.value)


# restore_kek_file ----------------------------------------------------------------------------


def test_restore_reproduce_los_32_bytes_de_la_kek(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    kek = kek_tmp.read_bytes()
    archivo = _respaldo(carpetas.salidas, kek)
    destino = carpetas.salidas / "restaurada" / "kek.bin"
    destino.parent.mkdir()

    restore_kek_file(archivo, destino)

    assert destino.read_bytes() == kek and len(kek) == 32
    (llamada,) = llamadas(age_falso)
    assert "-d" in llamada["argv"]
    assert entorno_visto(llamada) == {}
    _no_hay_kek_en(llamada, kek)
    assert not any(a.startswith("--passphrase") for a in llamada["argv"])


def test_restore_no_sobrescribe_y_crea_con_o_excl_y_modo_600(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    aperturas: list[tuple[str, int, int]],
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    destino = carpetas.salidas / "kek-restaurada.bin"

    restore_kek_file(archivo, destino)

    propias = [(f, m) for ruta, f, m in aperturas if Path(ruta) == destino]
    assert len(propias) == 1
    banderas, modo = propias[0]
    assert banderas & os.O_EXCL and banderas & os.O_WRONLY and modo == 0o600
    with pytest.raises(FileExistsError):
        restore_kek_file(archivo, destino)


def test_restore_rechaza_una_salida_bajo_el_directorio_de_la_kek_viva(
    kek_tmp: Path, carpetas: SimpleNamespace
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    original = kek_tmp.read_bytes()
    vecino = kek_tmp.parent / "otra.bin"

    with pytest.raises(KekPathRejected):
        restore_kek_file(archivo, vecino, age_binary=SIN_AGE)
    with pytest.raises(KekPathRejected):
        restore_kek_file(archivo, kek_tmp, age_binary=SIN_AGE)

    assert not vecino.exists() and kek_tmp.read_bytes() == original


def test_restore_rechaza_una_salida_bajo_backup_dir(
    kek_tmp: Path, carpetas: SimpleNamespace
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())

    with pytest.raises(KekPathRejected):
        restore_kek_file(archivo, carpetas.respaldos / "kek.bin", age_binary=SIN_AGE)


def test_restore_sin_terminal_lanza_notty_y_no_deja_archivo(
    kek_tmp: Path, age_falso: Path, carpetas: SimpleNamespace
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    destino = carpetas.salidas / "kek-restaurada.bin"
    configurar(age_falso, no_tty=True)

    with pytest.raises(NoTty):
        restore_kek_file(archivo, destino)

    assert not destino.exists() or destino.stat().st_size == 0


def test_restore_con_un_archivo_que_no_es_de_age_falla_con_ageerror(
    age_falso: Path, carpetas: SimpleNamespace
) -> None:
    ajeno = carpetas.salidas / "ajeno.age"
    ajeno.write_bytes(b"esto no es un archivo age")

    with pytest.raises(archive.AgeError) as excinfo:
        restore_kek_file(ajeno, carpetas.salidas / "kek-restaurada.bin")

    assert not isinstance(excinfo.value, NoTty)
    assert "unknown version" not in str(excinfo.value)  # nada del texto del hijo


# verify_kek_backup ---------------------------------------------------------------------------


def test_verify_con_la_misma_kek_es_ok(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    wrapped_de_prueba: list[WrappedDek],
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    antes = sorted(p.name for p in carpetas.salidas.iterdir())

    resultado = verify_kek_backup(archivo, wrapped_de_prueba)

    assert resultado == VerifyKekResult(total=3, failed_key_ids=())
    assert sorted(p.name for p in carpetas.salidas.iterdir()) == antes  # no escribe la KEK
    (llamada,) = llamadas(age_falso)
    assert entorno_visto(llamada) == {}
    _no_hay_kek_en(llamada, kek_tmp.read_bytes())


def test_verify_con_otra_kek_lista_las_dek_que_no_abre(
    age_falso: Path, carpetas: SimpleNamespace, wrapped_de_prueba: list[WrappedDek]
) -> None:
    archivo = _respaldo(carpetas.salidas, os.urandom(32))

    resultado = verify_kek_backup(archivo, wrapped_de_prueba)

    assert resultado.ok is False and resultado.total == 3
    assert len(resultado.failed_key_ids) == 3


@pytest.mark.parametrize("largo", [31, 33, 0, 64])
def test_verify_exige_exactamente_32_bytes(
    age_falso: Path,
    carpetas: SimpleNamespace,
    wrapped_de_prueba: list[WrappedDek],
    largo: int,
) -> None:
    archivo = _respaldo(carpetas.salidas, os.urandom(largo))

    with pytest.raises(KekLengthInvalid):
        verify_kek_backup(archivo, wrapped_de_prueba)


def test_verify_sin_terminal_lanza_notty(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    wrapped_de_prueba: list[WrappedDek],
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    configurar(age_falso, no_tty=True)

    with pytest.raises(NoTty):
        verify_kek_backup(archivo, wrapped_de_prueba)


def test_verify_con_plazo_agotado_lanza_agetimeout(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    wrapped_de_prueba: list[WrappedDek],
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())
    configurar(age_falso, dormir_s=30)

    with pytest.raises(AgeTimeout):
        verify_kek_backup(archivo, wrapped_de_prueba, timeout_s=1)


def test_verify_con_binario_ausente_lanza_agemissing(
    kek_tmp: Path, carpetas: SimpleNamespace, wrapped_de_prueba: list[WrappedDek], tmp_path: Path
) -> None:
    archivo = _respaldo(carpetas.salidas, kek_tmp.read_bytes())

    with pytest.raises(AgeMissing):
        verify_kek_backup(archivo, wrapped_de_prueba, age_binary=str(tmp_path / "nada" / "age"))


# Ninguna salida de registro lleva la KEK -------------------------------------------------------


def test_los_registros_no_llevan_la_kek_ni_su_base64(
    kek_tmp: Path,
    age_falso: Path,
    carpetas: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    kek = kek_tmp.read_bytes()
    export_kek_file(kek_tmp, carpetas.salidas / "kek.age")
    restore_kek_file(carpetas.salidas / "kek.age", carpetas.salidas / "kek-restaurada.bin")

    texto = caplog.text
    assert kek.hex() not in texto
    assert base64.b64encode(kek).decode() not in texto
    assert base64.urlsafe_b64encode(kek).decode() not in texto
