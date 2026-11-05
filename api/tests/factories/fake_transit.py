"""OpenBao Transit falso para las pruebas del proveedor (S5-B1; S5-D21).

`FakeTransit` es un manejador de `httpx.MockTransport` que imita lo que usa `OpenBaoProvider`:

- `POST /v1/transit/encrypt|decrypt|rewrap/<llave>` con AES-256-GCM real y texto cifrado
  `vault:v<n>:<base64(nonce + cifrado)>`; `associated_data` (base64) entra como AAD en encrypt y
  decrypt. `rewrap` descifra con la versión indicada y cifra con la última; el modo
  `rewrap_acepta_aad` (por defecto True) NO está probado contra el OpenBao real (M-5a): solo la
  prueba `openbao_real` lo demuestra.
- `POST /v1/transit/sign|verify/<llave>` con Ed25519 real por versión (`vault:v<n>:<b64>`).
- `POST /v1/transit/keys/<llave>/rotate`, `GET /v1/transit/keys/<llave>`.
- `GET /v1/sys/seal-status` (sin token), `GET /v1/sys/health`, `POST /v1/auth/token/renew-self`.
  `lookup-self` responde 403 siempre (los tokens son `-no-default-policy`, S5-D108) y queda
  registrado para que las pruebas afirmen que nadie lo llama.
- Estados: `seal()`, `unseal()`, `uninitialize()`, `revoke_token()`, `responder(...)`,
  `timeout_en(...)`, `conexion_rota_en(...)`, `min_decryption_version`.
- Registro: `calls` (método, ruta, cabeceras en minúsculas, cuerpo JSON) para afirmar que el token
  viaja solo en `X-Vault-Token`.

`cliente()` devuelve un `httpx.AsyncClient` listo para inyectar; `fabrica_de_cliente()` devuelve una
función con la firma de `httpx.AsyncClient(**kwargs)` que registra los kwargs recibidos (para
afirmar `follow_redirects=False` y `trust_env=False`).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature, InvalidTag  # noqa: TID251
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: TID251
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: TID251

_CLIENTE_REAL = httpx.AsyncClient  # la clase original, aunque una prueba parchee httpx.AsyncClient
ADDR_FAKE = "http://openbao:8200"
TOKEN_FAKE = "s.apex-token-de-prueba-0123456789abcdef"  # noqa: S105
LLAVES_POR_DEFECTO = {"apex-kek": "aes256-gcm96", "apex-sign-audit": "ed25519"}


@dataclass
class Call:
    method: str
    path: str
    headers: dict[str, str]
    body: Any
    url: str


@dataclass
class _Forzada:
    fragmento: str
    status: int
    errors: list[str]
    veces: int | None


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.b64decode(texto.encode("ascii"), validate=True)


@dataclass
class FakeTransit:
    token: str = TOKEN_FAKE
    llaves: dict[str, str] = field(default_factory=lambda: dict(LLAVES_POR_DEFECTO))
    rewrap_acepta_aad: bool = True
    sellado: bool = False
    inicializado: bool = True
    min_decryption_version: dict[str, int] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    _material: dict[str, list[Any]] = field(default_factory=dict)
    _token_valido: bool = True
    _forzadas: list[_Forzada] = field(default_factory=list)
    _timeouts: list[str] = field(default_factory=list)
    _rotas: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for nombre, tipo in self.llaves.items():
            self._material[nombre] = [self._nueva(tipo)]

    # --- control de la prueba -------------------------------------------------------------

    @staticmethod
    def _nueva(tipo: str) -> Any:
        return Ed25519PrivateKey.generate() if tipo == "ed25519" else os.urandom(32)

    def seal(self) -> None:
        self.sellado = True

    def unseal(self) -> None:
        self.sellado = False

    def uninitialize(self) -> None:
        self.inicializado, self.sellado = False, True

    def revoke_token(self) -> None:
        """El token deja de valer: Transit responde 403 (seal-status sigue abierto)."""
        self._token_valido = False

    def aceptar_token(self, token: str) -> None:
        self.token, self._token_valido = token, True

    def responder(
        self, fragmento: str, status: int, errors: list[str] | None = None, veces: int | None = None
    ) -> None:
        """Las rutas que contienen `fragmento` responden `status` (`veces` veces o siempre)."""
        self._forzadas.append(_Forzada(fragmento, status, errors or [], veces))

    def timeout_en(self, fragmento: str) -> None:
        self._timeouts.append(fragmento)

    def conexion_rota_en(self, fragmento: str) -> None:
        self._rotas.append(fragmento)

    def latest_version(self, llave: str) -> int:
        return len(self._material[llave])

    def llamadas(self, fragmento: str) -> list[Call]:
        return [c for c in self.calls if fragmento in c.path]

    # --- transporte -----------------------------------------------------------------------

    def cliente(self, **kwargs: Any) -> httpx.AsyncClient:
        return _CLIENTE_REAL(
            transport=httpx.MockTransport(self.handler), base_url=ADDR_FAKE, **kwargs
        )

    def fabrica_de_cliente(self, recibidos: list[dict[str, Any]]) -> Any:
        def fabrica(**kwargs: Any) -> httpx.AsyncClient:
            recibidos.append(dict(kwargs))
            propios = {k: v for k, v in kwargs.items() if k in ("base_url", "timeout")}
            propios.setdefault("base_url", ADDR_FAKE)
            return _CLIENTE_REAL(transport=httpx.MockTransport(self.handler), **propios)

        return fabrica

    def handler(self, request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        cuerpo: Any = json.loads(request.content) if request.content else None
        self.calls.append(
            Call(
                request.method,
                ruta,
                {k.lower(): v for k, v in request.headers.items()},
                cuerpo,
                str(request.url),
            )
        )
        if any(f in ruta for f in self._timeouts):
            raise httpx.ReadTimeout("tiempo agotado", request=request)
        if any(f in ruta for f in self._rotas):
            raise httpx.ConnectError("conexion rechazada", request=request)
        for forzada in list(self._forzadas):
            if forzada.fragmento in ruta:
                if forzada.veces is not None:
                    forzada.veces -= 1
                    if forzada.veces <= 0:
                        self._forzadas.remove(forzada)
                return self._error(forzada.status, forzada.errors)
        if ruta == "/v1/sys/seal-status":
            return httpx.Response(
                200, json={"initialized": self.inicializado, "sealed": self.sellado}
            )
        if ruta == "/v1/sys/health":
            codigo = 200 if self.inicializado and not self.sellado else 503
            return httpx.Response(
                codigo, json={"initialized": self.inicializado, "sealed": self.sellado}
            )
        if self.sellado:
            msg = "Vault is sealed" if self.inicializado else "Vault is not initialized"
            return self._error(503, [msg])
        if request.headers.get("x-vault-token") != self.token or not self._token_valido:
            return self._error(403, ["permission denied"])
        return self._ruta(request.method, ruta, cuerpo)

    @staticmethod
    def _error(status: int, errors: list[str]) -> httpx.Response:
        return httpx.Response(status, json={"errors": errors})

    def _ruta(self, metodo: str, ruta: str, cuerpo: Any) -> httpx.Response:
        if ruta == "/v1/auth/token/renew-self":
            return httpx.Response(
                200, json={"auth": {"lease_duration": 2764800, "renewable": True}}
            )
        if ruta == "/v1/auth/token/lookup-self":
            return self._error(403, ["permission denied"])
        partes = ruta.strip("/").split("/")
        if len(partes) < 4 or partes[:2] != ["v1", "transit"]:
            return self._error(404, [])
        accion, nombre = partes[2], partes[3]
        if accion == "keys":
            return self._clave(metodo, nombre, partes[4:] == ["rotate"])
        if nombre not in self._material:
            return self._error(404, ["no existe la llave"])
        if accion == "encrypt":
            return self._cifrar(nombre, cuerpo)
        if accion == "decrypt":
            return self._descifrar(nombre, cuerpo)
        if accion == "rewrap":
            return self._reenvolver(nombre, cuerpo)
        if accion == "sign":
            return self._firmar(nombre, cuerpo)
        if accion == "verify":
            return self._verificar(nombre, cuerpo)
        return self._error(404, [])

    def _clave(self, metodo: str, nombre: str, rotar: bool) -> httpx.Response:
        if nombre not in self._material:
            return self._error(404, [])
        if rotar and metodo == "POST":
            self._material[nombre].append(self._nueva(self.llaves[nombre]))
        n = self.latest_version(nombre)
        datos = {
            "name": nombre,
            "type": self.llaves[nombre],
            "latest_version": n,
            "min_decryption_version": self.min_decryption_version.get(nombre, 1),
            "keys": {str(v): 1_760_000_000 + v for v in range(1, n + 1)},
        }
        return httpx.Response(200, json={"data": datos})

    def _cifrar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        n = self.latest_version(nombre)
        return httpx.Response(200, json={"data": {"ciphertext": self._sellar(nombre, n, cuerpo)}})

    def _sellar(self, nombre: str, version: int, cuerpo: Any) -> str:
        aad = _de_b64(cuerpo["associated_data"]) if cuerpo.get("associated_data") else None
        nonce = os.urandom(12)
        cifrado = AESGCM(self._material[nombre][version - 1]).encrypt(
            nonce, _de_b64(cuerpo["plaintext"]), aad
        )
        return f"vault:v{version}:{_b64(nonce + cifrado)}"

    def _abrir(self, nombre: str, texto: str, aad_b64: str | None) -> bytes | httpx.Response:
        partes = texto.split(":")
        if len(partes) != 3 or partes[0] != "vault" or not partes[1].startswith("v"):
            return self._error(400, ["invalid ciphertext: no prefix"])
        try:
            version = int(partes[1][1:])
            crudo = _de_b64(partes[2])
        except ValueError:
            return self._error(400, ["invalid ciphertext"])
        if version < self.min_decryption_version.get(nombre, 1) or version > self.latest_version(
            nombre
        ):
            return self._error(400, ["ciphertext version is disallowed by policy"])
        aad = _de_b64(aad_b64) if aad_b64 else None
        try:
            return AESGCM(self._material[nombre][version - 1]).decrypt(crudo[:12], crudo[12:], aad)
        except (InvalidTag, ValueError):
            return self._error(400, ["cipher: message authentication failed"])

    def _descifrar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        abierto = self._abrir(nombre, cuerpo["ciphertext"], cuerpo.get("associated_data"))
        if isinstance(abierto, httpx.Response):
            return abierto
        return httpx.Response(200, json={"data": {"plaintext": _b64(abierto)}})

    def _reenvolver(self, nombre: str, cuerpo: Any) -> httpx.Response:
        aad = cuerpo.get("associated_data") if self.rewrap_acepta_aad else None
        abierto = self._abrir(nombre, cuerpo["ciphertext"], aad)
        if isinstance(abierto, httpx.Response):
            return abierto
        nuevo = self._sellar(
            nombre,
            self.latest_version(nombre),
            {"plaintext": _b64(abierto), "associated_data": aad},
        )
        return httpx.Response(200, json={"data": {"ciphertext": nuevo}})

    def _firmar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        n = self.latest_version(nombre)
        firma = self._material[nombre][n - 1].sign(_de_b64(cuerpo["input"]))
        return httpx.Response(200, json={"data": {"signature": f"vault:v{n}:{_b64(firma)}"}})

    def _verificar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        partes = str(cuerpo["signature"]).split(":")
        try:
            version = int(partes[1][1:])
            firma = _de_b64(partes[2])
            self._material[nombre][version - 1].public_key().verify(firma, _de_b64(cuerpo["input"]))
            valida = True
        except InvalidSignature:
            valida = False
        except (ValueError, IndexError):
            return self._error(400, ["invalid signature"])
        return httpx.Response(200, json={"data": {"valid": valida}})
