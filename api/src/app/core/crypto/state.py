"""Estado público del custodio de llaves (S5-B3; S5-D13, S5-D70, S5-D194).

`health_state` es una función pura: de lo que responde el proveedor, de si el proceso tiene
keyring y de si el umbral de desellado es aceptable sale el valor que `/health` publica en
`crypto`. Nunca lleva versión, clúster ni URL del custodio (L-7).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from app.core.crypto.provider import ProviderStatus

CryptoState = Literal["ok", "sealed", "unreachable", "unknown"]


@runtime_checkable
class ThresholdAware(Protocol):
    """Proveedor que conoce el umbral de desello (S5-D196): `OpenBaoProvider`. El local no
    lo tiene; sin umbral conocido no se avisa (L6)."""

    unseal_threshold: int | None


@runtime_checkable
class ReasonAware(Protocol):
    """Proveedor que deja la causa de su último `status()` distinto de `ok` (S5-D200)."""

    last_reason: str | None


def health_state(
    provider_status: ProviderStatus, keyring_loaded: bool, *, threshold_ok: bool
) -> CryptoState:
    """Función pura (S5-D13, M-3; tabla de S5-D194).

    - umbral de desellado inaceptable (`threshold_ok=False`) o proveedor `unreachable` ->
      `unreachable`;
    - proveedor `sealed` -> `sealed`;
    - proveedor `ok` con keyring cargado -> `ok`; sin keyring -> `sealed` (el custodio responde
      pero este proceso aún no tiene llaves: lo recupera el sondeo, `/health` nunca abre llaves).
    """
    if not threshold_ok or provider_status == "unreachable":
        return "unreachable"
    if provider_status == "sealed":
        return "sealed"
    return "ok" if keyring_loaded else "sealed"
