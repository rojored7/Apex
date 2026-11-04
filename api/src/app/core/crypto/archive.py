"""Archivos de respaldo: digest en reposo y respaldo de la KEK con `age -p`.

`digest_file` (SHA-256 de un archivo en reposo) vive en `digest.py` desde la revisión de seguridad
de B3a (S4B-D134): el worker, que no ejecuta `age` ni abre ninguna identidad (S4B-D59), no debe
cargar este módulo ni el proveedor local.

S4B-B3a (S4B-D58, S4B-D62, S4B-D89): `export_kek_file`, `restore_kek_file` y `verify_kek_backup`
son la única puerta de la KEK fuera del proveedor. Lanzan `age` con `Popen` por lista, sin shell y
con entorno vacío; la KEK viaja por el `stdin` del hijo (o sale de su `stdout`), nunca por `argv`,
entorno ni archivos temporales; la frase la pide `age` por la terminal y APEX no la ve. Los
archivos de salida se crean con `O_EXCL` y modo 0o600, y los errores nunca llevan texto del hijo.
"""

from __future__ import annotations

import contextlib
import os
import stat
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from app.core.config import get_settings as get_settings
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import check_key_file

if TYPE_CHECKING:
    from app.core.crypto.kek_backup import WrappedDek

AGE_BINARY: Final = "/usr/bin/age"
"""Ruta del binario `age` (el worker nunca lo abre)."""

AGE_TIMEOUT_S: Final = 600
"""Tiempo máximo de una llamada a `age` (la frase la teclea una persona)."""

KEK_LEN: Final = 32
"""Bytes exactos de la KEK local (`local_provider.KEK_LEN`)."""

STDERR_MAX: Final = 4096
"""Tope de lo que se lee del `stderr` del hijo; solo sirve para distinguir `NoTty`."""

KILL_WAIT_S: Final = 5
MSG_PATH: Final = "la ruta de salida no es válida"
MSG_NO_TTY: Final = "age necesita una terminal interactiva para pedir la frase"


# --- Respaldo de la KEK con `age -p` (S4B-B3a; S4B-D58, S4B-D89) ----------------------------------


@dataclass(frozen=True)
class VerifyKekResult:
    """Resultado de probar una KEK exportada contra las DEK envueltas de la base."""

    total: int
    failed_key_ids: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failed_key_ids


class NoTty(Exception):
    """`age` pidió la frase y no hay terminal interactiva (mensaje fijo, sin texto del hijo)."""


class AgeError(Exception):
    """`age` terminó con error o con una salida inaceptable; nunca lleva texto del hijo."""


class AgeMissing(AgeError):
    """El binario `age` no existe o no se puede ejecutar (el mensaje no lleva la ruta)."""


class AgeTimeout(AgeError):
    """`age` superó `timeout_s` y se mató al proceso hijo."""


class KekLengthInvalid(AgeError):
    """`age -d` entregó una cantidad de bytes distinta de `KEK_LEN`."""


class KekPathRejected(Exception):
    """Ruta de salida rechazada: bajo `BACKUP_DIR`, bajo el directorio de la KEK viva, con enlace
    simbólico o con la carpeta inexistente. El mensaje no lleva la ruta."""


def _zero(buffer: bytearray) -> None:
    buffer[:] = bytes(len(buffer))


def _read_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _check_out_path(out_path: Path) -> None:
    """Rechaza enlaces, carpetas inexistentes y destinos bajo `BACKUP_DIR` o la KEK viva."""
    ajustes = get_settings()
    if out_path.is_symlink():
        raise KekPathRejected(MSG_PATH)
    try:
        carpeta = out_path.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise KekPathRejected(MSG_PATH) from None
    if not carpeta.is_dir():
        raise KekPathRejected(MSG_PATH)
    prohibidas = [ajustes.BACKUP_DIR]
    if ajustes.CRYPTO_LOCAL_KEK_PATH is not None:
        prohibidas.append(ajustes.CRYPTO_LOCAL_KEK_PATH.parent)
    destino = carpeta / out_path.name
    if any(destino.is_relative_to(p.resolve()) for p in prohibidas):
        raise KekPathRejected(MSG_PATH)


def _read_kek(kek_path: Path) -> bytearray:
    """Los 32 bytes exactos de la KEK en un `bytearray` que quien llama pone en ceros."""
    check_key_file(kek_path, size=KEK_LEN, name="KEK")
    try:
        descriptor = os.open(kek_path, _read_flags())
    except OSError:
        raise CryptoError("kek_missing", "la KEK no está disponible") from None
    buffer = bytearray(KEK_LEN + 1)
    with os.fdopen(descriptor, "rb", buffering=0) as archivo:
        leidos = archivo.readinto(buffer)
    kek = buffer[:KEK_LEN]
    _zero(buffer)
    if leidos != KEK_LEN:
        _zero(kek)
        raise CryptoError("kek_invalid", "la KEK tiene un tamaño incorrecto")
    return kek


def _open_backup(age_path: Path) -> int:
    """Descriptor de solo lectura del respaldo `.age`: archivo regular, sin seguir enlaces."""
    descriptor = os.open(age_path, _read_flags())
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise AgeError("el respaldo no es un archivo regular")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _create_out(out_path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    return os.open(out_path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)


def _spawn(
    args: Sequence[str], *, stdin: int, stdout: int, age_binary: str
) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(  # noqa: S603
            [age_binary, *args],
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            env={},
            shell=False,
            close_fds=True,
            bufsize=0,
        )
    except OSError:
        raise AgeMissing("age no está disponible") from None


def _kill(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=KILL_WAIT_S)
    for flujo in (proc.stdin, proc.stdout, proc.stderr):
        if flujo is not None:
            with contextlib.suppress(OSError):
                flujo.close()


def _failure(stderr: bytes) -> Exception:
    """`NoTty` si `age` no pudo abrir la terminal; si no, `AgeError`. Nunca copia el texto."""
    texto = stderr[:STDERR_MAX].decode(errors="replace").lower()
    if "/dev/tty" in texto or "could not read passphrase" in texto:
        return NoTty(MSG_NO_TTY)
    return AgeError("age terminó con error")


def _feed(proc: subprocess.Popen[bytes], data: bytearray) -> None:
    """Escribe la KEK al `stdin` del hijo desde una vista del `bytearray` (sin copia inmutable) y
    lo cierra. 32 bytes caben en la tubería: no bloquea. Si el hijo ya murió, el error de la
    tubería se ignora y el motivo sale del `stderr`."""
    assert proc.stdin is not None  # noqa: S101
    try:
        with memoryview(data) as vista:
            proc.stdin.write(vista)
    except (BrokenPipeError, OSError):
        pass
    finally:
        with contextlib.suppress(OSError):
            proc.stdin.close()
        proc.stdin = None  # communicate() no debe volver a vaciar un flujo cerrado


def _wait(proc: subprocess.Popen[bytes], data: bytearray | None, timeout_s: int) -> bytes:
    if data is not None:
        _feed(proc, data)
    try:
        _, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
        raise AgeTimeout("age superó el plazo") from None
    return stderr or b""


def _run_to_file(
    args: Sequence[str],
    *,
    stdin: int,
    data: bytearray | None,
    out_path: Path,
    exact_len: int | None,
    age_binary: str,
    timeout_s: int,
) -> None:
    """Corre `age` con su `stdout` en `out_path` (nuevo, `O_EXCL`); lo borra si algo falla."""
    salida = _create_out(out_path)
    listo = False
    try:
        proc = _spawn(args, stdin=stdin, stdout=salida, age_binary=age_binary)
        stderr = _wait(proc, data, timeout_s)
        if proc.returncode != 0:
            raise _failure(stderr)
        tamano = os.fstat(salida).st_size
        if tamano == 0 or (exact_len is not None and tamano != exact_len):
            raise KekLengthInvalid("age entregó una cantidad de bytes inesperada")
        os.fsync(salida)
        listo = True
    finally:
        os.close(salida)
        if not listo:
            with contextlib.suppress(OSError):
                out_path.unlink()


def export_kek_file(
    kek_path: Path,
    out_path: Path,
    *,
    age_binary: str = AGE_BINARY,
    timeout_s: int = AGE_TIMEOUT_S,
) -> None:
    """Cifra la KEK con `age -p` hacia `out_path` (`O_EXCL`, 0o600); la KEK viaja por `stdin`."""
    _check_out_path(out_path)
    kek = _read_kek(kek_path)
    try:
        _run_to_file(
            ["-p"],
            stdin=subprocess.PIPE,
            data=kek,
            out_path=out_path,
            exact_len=None,
            age_binary=age_binary,
            timeout_s=timeout_s,
        )
    finally:
        _zero(kek)


def restore_kek_file(
    age_path: Path,
    out_path: Path,
    *,
    age_binary: str = AGE_BINARY,
    timeout_s: int = AGE_TIMEOUT_S,
) -> None:
    """`age -d` del respaldo hacia `out_path` (`O_EXCL`, 0o600), nunca bajo la KEK viva."""
    _check_out_path(out_path)
    entrada = _open_backup(age_path)
    try:
        _run_to_file(
            ["-d"],
            stdin=entrada,
            data=None,
            out_path=out_path,
            exact_len=KEK_LEN,
            age_binary=age_binary,
            timeout_s=timeout_s,
        )
    finally:
        os.close(entrada)


def _read_kek_from_child(proc: subprocess.Popen[bytes], timeout_s: int) -> bytearray:
    """Lee a lo sumo `KEK_LEN + 1` bytes del `stdout` del hijo con un plazo que lo mata."""
    vencio = threading.Event()

    def _vencer() -> None:
        vencio.set()
        with contextlib.suppress(OSError):
            proc.kill()

    reloj = threading.Timer(timeout_s, _vencer)
    reloj.daemon = True
    reloj.start()
    buffer = bytearray(KEK_LEN + 1)
    try:
        assert proc.stdout is not None and proc.stderr is not None  # noqa: S101
        vista = memoryview(buffer)
        leidos = 0
        while leidos < len(buffer) and (n := proc.stdout.readinto(vista[leidos:])):  # type: ignore[attr-defined]
            leidos += n
        if leidos > KEK_LEN:
            proc.kill()
        stderr = proc.stderr.read(STDERR_MAX)
        proc.wait()
        if vencio.is_set():
            raise AgeTimeout("age superó el plazo")
        if leidos > KEK_LEN:
            raise KekLengthInvalid("age entregó una cantidad de bytes inesperada")
        if proc.returncode != 0:
            raise _failure(stderr)
        if leidos != KEK_LEN:
            raise KekLengthInvalid("age entregó una cantidad de bytes inesperada")
        return bytearray(buffer[:KEK_LEN])
    finally:
        reloj.cancel()
        _zero(buffer)
        _kill(proc)


def verify_kek_backup(
    age_path: Path,
    wrapped: Sequence[WrappedDek],
    *,
    age_binary: str = AGE_BINARY,
    timeout_s: int = AGE_TIMEOUT_S,
) -> VerifyKekResult:
    """`age -d` a `PIPE`, 32 bytes exactos en un `bytearray` y `unwrap` de cada DEK."""
    from app.core.crypto.kek_backup import verify_wrapped

    entrada = _open_backup(age_path)
    try:
        proc = _spawn(["-d"], stdin=entrada, stdout=subprocess.PIPE, age_binary=age_binary)
    finally:
        os.close(entrada)
    kek = _read_kek_from_child(proc, timeout_s)
    try:
        return verify_wrapped(kek, wrapped)
    finally:
        _zero(kek)
