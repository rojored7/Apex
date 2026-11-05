"""`OpenBaoProvider`: KEK y firma en OpenBao Transit con httpx (S5-B1; D2, D3, D9, D17).

Es el único archivo (con `core/alerts_telegram.py` desde B4) que importa `httpx`, y el único que
lee el archivo del token (S5-D123). Sin reintentos dentro del proveedor, sin redirecciones, sin
proxies del entorno. Ninguna excepción lleva URL, token, ruta ni texto del servidor (S5-D17).

- `wrap`/`unwrap`/`rewrap`: `transit/{encrypt,decrypt,rewrap}/apex-kek` con `associated_data` =
  base64(`apx-dek-wrap`); el texto cifrado `vault:v<n>:...` es el `wrapped_material` (ADR-002).
- `sign`/`verify`: `transit/{sign,verify}/<llave>`; `rotate`/`key_info`: `transit/keys`.
- `status` (S5-D151): `sys/seal-status` SIN token y luego `auth/token/renew-self` CON token, la
  única ruta con token común a las políticas de api, worker y tools (el api no puede leer
  `transit/keys/apex-kek`). Nunca lanza y nunca llama `lookup-self` (S5-D108).
"""

from __future__ import annotations

import base64
import binascii
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import httpx

from app.core.clock import get_clock
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.local_provider import WRAP_AAD
from app.core.crypto.openbao_wire import (
    a_texto,
    b64,
    comprobar_direccion,
    info,
    map_error,
    parse_version,
    ruta,
    texto_cifrado,
)
from app.core.crypto.provider import KeyInfo, ProviderStatus

KEK_KEY: Final = "apex-kek"
SIGN_KEY: Final = "apex-sign-audit"
TOKEN_MAX_BYTES: Final = 256
RENEW_EVERY: Final = timedelta(hours=12)
_WRAP_AAD_B64: Final = base64.b64encode(WRAP_AAD).decode("ascii")
__all__ = ["KEK_KEY", "SIGN_KEY", "WRAP_AAD", "OpenBaoProvider", "map_error", "parse_version"]


def _cargar_token(token_path: Path) -> tuple[str, tuple[int, int, int]]:
    """Valida y lee el archivo del token: `(token recortado, mtime_ns)`; nunca lo imprime."""
    try:
        st = token_path.stat()
    except OSError:
        raise CryptoError("kek_missing", "el archivo del token de OpenBao no existe") from None
    if not stat.S_ISREG(st.st_mode):
        raise CryptoError("kek_invalid", "el token de OpenBao no es un archivo regular")
    if os.name != "nt" and stat.S_IMODE(st.st_mode) & 0o077:
        raise CryptoError("kek_insecure_permissions", "el archivo del token debe ser 600")
    if not 0 < st.st_size <= TOKEN_MAX_BYTES:
        raise CryptoError("kek_invalid", "el archivo del token está vacío o es demasiado grande")
    try:
        crudo = token_path.read_bytes()
        token = crudo.decode("ascii").strip() if len(crudo) <= TOKEN_MAX_BYTES else ""
    except (OSError, UnicodeDecodeError):
        raise CryptoError("kek_invalid", "el archivo del token no se puede leer") from None
    if not token:
        raise CryptoError("kek_invalid", "el archivo del token está vacío")
    return token, _huella(st)


def _huella(st: os.stat_result) -> tuple[int, int, int]:
    """`(mtime_ns, tamaño, inodo)`: una reemisión por `rename` cambia el inodo (S5-D164)."""
    return (st.st_mtime_ns, st.st_size, st.st_ino)


class OpenBaoProvider:
    name = "openbao"

    def __init__(
        self,
        addr: str,
        token_path: Path,
        *,
        timeout_s: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._addr = comprobar_direccion(addr)
        self._token_path = token_path
        self._timeout_s = timeout_s
        self._client = client
        self._token: tuple[str, tuple[int, int, int]] | None = None
        self._ultimo_ok: datetime | None = None
        self._ultimo_error: datetime | None = None
        self._ultima_renovacion: datetime | None = None
        # Umbral de desello (`t` de `sys/seal-status`, S5-D196); `None` hasta la primera lectura.
        # `/health` lo usa para la guarda M-3; no es parte del puerto `KeyProvider`.
        self.unseal_threshold: int | None = None
        # Causa de la última consulta de `status()`: sealed | unreachable | forbidden | None si ok
        # (S5-D200). El Literal público de `status()` no cambia.
        self.last_reason: str | None = None

    def __repr__(self) -> str:
        return "OpenBaoProvider()"

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    # --- transporte ----------------------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._addr,
                timeout=httpx.Timeout(self._timeout_s),
                follow_redirects=False,
                trust_env=False,
            )
        return self._client

    def _token_vigente(self) -> str:
        """Valida al primer uso y relee solo si cambió el `mtime` (rotación del archivo)."""
        try:
            huella = _huella(self._token_path.stat())
        except OSError:
            raise CryptoError("kek_missing", "el archivo del token de OpenBao no existe") from None
        if self._token is None or self._token[1] != huella:
            self._token = _cargar_token(self._token_path)
        return self._token[0]

    async def _enviar(
        self, metodo: str, ruta: str, cuerpo: dict[str, Any] | None, *, con_token: bool = True
    ) -> httpx.Response:
        cabeceras = {"X-Vault-Token": self._token_vigente()} if con_token else {}
        try:
            return await self._http().request(metodo, ruta, json=cuerpo, headers=cabeceras)
        except httpx.HTTPError:
            raise CryptoUnavailable("unreachable") from None

    async def _llamar(
        self, metodo: str, ruta: str, cuerpo: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        ahora = get_clock().now_utc()
        try:
            respuesta = await self._enviar(metodo, ruta, cuerpo)
            if respuesta.status_code >= 400:
                raise map_error(respuesta.status_code, _errores(respuesta))
        except CryptoError:
            self._ultimo_error = ahora
            raise
        self._ultimo_ok = ahora
        try:
            datos = respuesta.json().get("data") or {}
        except (ValueError, AttributeError):
            raise CryptoError("unwrap_failed", "respuesta inválida del custodio") from None
        return datos if isinstance(datos, dict) else {}

    # --- envoltura de DEK ------------------------------------------------------------------

    async def wrap(self, dek: bytes | bytearray) -> bytes:
        """Un `bytearray` reduce, no elimina, la exposición: `b64` y el cuerpo JSON crean copias."""
        cuerpo = {"plaintext": b64(dek), "associated_data": _WRAP_AAD_B64}
        datos = await self._llamar("POST", ruta("encrypt", KEK_KEY), cuerpo)
        return texto_cifrado(datos)

    async def unwrap(self, wrapped: bytes) -> bytes:
        parse_version(wrapped)
        cuerpo = {"ciphertext": a_texto(wrapped), "associated_data": _WRAP_AAD_B64}
        datos = await self._llamar("POST", ruta("decrypt", KEK_KEY), cuerpo)
        try:
            return base64.b64decode(str(datos["plaintext"]), validate=True)
        except (KeyError, binascii.Error):
            raise CryptoError("unwrap_failed", "respuesta inválida del custodio") from None

    async def rewrap(self, wrapped: bytes) -> bytes:
        parse_version(wrapped)
        cuerpo = {"ciphertext": a_texto(wrapped), "associated_data": _WRAP_AAD_B64}
        datos = await self._llamar("POST", ruta("rewrap", KEK_KEY), cuerpo)
        return texto_cifrado(datos)

    # --- firma -----------------------------------------------------------------------------

    async def sign(self, key_ref: str, data: bytes) -> bytes:
        datos = await self._llamar("POST", ruta("sign", key_ref), {"input": b64(data)})
        firma = datos.get("signature")
        if not isinstance(firma, str):
            raise CryptoError("unwrap_failed", "respuesta inválida del custodio")
        return firma.encode("ascii")

    async def verify(self, key_ref: str, data: bytes, signature: bytes) -> bool:
        cuerpo = {"input": b64(data), "signature": a_texto(signature)}
        try:
            datos = await self._llamar("POST", ruta("verify", key_ref), cuerpo)
        except CryptoError as error:
            if error.code == "unwrap_failed":
                return False  # firma mal formada: no verifica
            raise
        return datos.get("valid") is True

    # --- llaves ----------------------------------------------------------------------------

    async def rotate(self, key_ref: str) -> KeyInfo:
        datos = await self._llamar("POST", ruta("keys", key_ref) + "/rotate")
        return info(key_ref, datos)

    async def key_info(self, key_ref: str) -> KeyInfo:
        return info(key_ref, await self._llamar("GET", ruta("keys", key_ref)))

    async def set_min_decryption_version(self, key_ref: str, version: int) -> None:
        """Sube `min_decryption_version` (`keys/<k>/config`); fuera del puerto (S5-D185).
        Nunca `keys/<k>/trim`: es irreversible."""
        cuerpo = {"min_decryption_version": version}
        await self._llamar("POST", ruta("keys", key_ref) + "/config", cuerpo)

    # --- estado y renovación ---------------------------------------------------------------

    async def status(self) -> ProviderStatus:
        self.last_reason = None
        try:
            sello = await self._enviar("GET", "/v1/sys/seal-status", None, con_token=False)
            if sello.status_code != 200:
                return "unreachable"
            estado = sello.json()
            umbral = estado.get("t")
            if isinstance(umbral, int) and not isinstance(umbral, bool):
                self.unseal_threshold = umbral
            if estado.get("sealed") is not False or estado.get("initialized") is not True:
                return "sealed"
            await self._confirmar_token()
        except CryptoUnavailable as error:
            self.last_reason = error.reason
            return "sealed" if error.reason == "sealed" else "unreachable"
        except (CryptoError, ValueError, AttributeError):
            self.last_reason = "unreachable"
            return "unreachable"
        return "ok"

    async def _confirmar_token(self) -> None:
        """S5-D163: sin sondear con token en cada `status()`. Vale la última operación
        autenticada con éxito de hace menos de 12 h; si no, renueva a lo sumo cada 12 h."""
        ahora = get_clock().now_utc()
        if self._ultimo_ok is not None and ahora - self._ultimo_ok < RENEW_EVERY:
            if self._ultimo_error is None or self._ultimo_error < self._ultimo_ok:
                return
            self._ultima_renovacion = None  # hubo un error después: se sondea de nuevo
        await self.maybe_renew(ahora)

    async def renew(self) -> None:
        await self._llamar("POST", "/v1/auth/token/renew-self")

    async def maybe_renew(self, now: datetime) -> None:
        """Una renovación por cada 12 h cumplidas (la primera llamada renueva)."""
        ultima = self._ultima_renovacion
        if ultima is not None and now - ultima < RENEW_EVERY:
            return
        await self.renew()
        self._ultima_renovacion = now


def _errores(respuesta: httpx.Response) -> list[str]:
    try:
        errores = respuesta.json().get("errors", [])
    except (ValueError, AttributeError):
        return []
    return [e for e in errores if isinstance(e, str)] if isinstance(errores, list) else []
