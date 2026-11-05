"""`FakeTransit` se comporta como Transit en lo que usa el proveedor (S5-B1)."""

from __future__ import annotations

import base64

import httpx

from tests.factories.fake_transit import TOKEN_FAKE, FakeTransit


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


async def _post(
    fake: FakeTransit, ruta: str, cuerpo: dict[str, object], token: str | None = TOKEN_FAKE
):
    cabeceras = {"X-Vault-Token": token} if token else {}
    async with fake.cliente() as cliente:
        return await cliente.post(ruta, json=cuerpo, headers=cabeceras)


async def test_encrypt_decrypt_ida_y_vuelta_con_aad() -> None:
    fake = FakeTransit()
    pedido = {"plaintext": _b64(b"dek"), "associated_data": _b64(b"apx-dek-wrap")}
    cifrado = (await _post(fake, "/v1/transit/encrypt/apex-kek", pedido)).json()["data"][
        "ciphertext"
    ]
    assert cifrado.startswith("vault:v1:")
    ok = await _post(fake, "/v1/transit/decrypt/apex-kek", {"ciphertext": cifrado, **pedido})
    assert base64.b64decode(ok.json()["data"]["plaintext"]) == b"dek"
    sin_aad = await _post(fake, "/v1/transit/decrypt/apex-kek", {"ciphertext": cifrado})
    assert sin_aad.status_code == 400


async def test_rotate_y_rewrap_suben_la_version_y_conservan_el_texto() -> None:
    fake = FakeTransit()
    pedido = {"plaintext": _b64(b"dek"), "associated_data": _b64(b"apx-dek-wrap")}
    v1 = (await _post(fake, "/v1/transit/encrypt/apex-kek", pedido)).json()["data"]["ciphertext"]
    await _post(fake, "/v1/transit/keys/apex-kek/rotate", {})
    v2 = (
        await _post(
            fake,
            "/v1/transit/rewrap/apex-kek",
            {"ciphertext": v1, **{"associated_data": pedido["associated_data"]}},
        )
    ).json()["data"]["ciphertext"]
    assert v2.startswith("vault:v2:")


async def test_estados_sellado_sin_token_y_lookup_self() -> None:
    fake = FakeTransit()
    assert (
        await _post(fake, "/v1/transit/encrypt/apex-kek", {"plaintext": ""}, token=None)
    ).status_code == 403
    fake.seal()
    sellado = await _post(fake, "/v1/transit/encrypt/apex-kek", {"plaintext": ""})
    assert sellado.status_code == 503 and "sealed" in sellado.json()["errors"][0]
    async with fake.cliente() as cliente:
        estado = await cliente.get("/v1/sys/seal-status")
    # S5-B3: seal-status trae además `t`, `n`, versión y clúster (para probar L-7 y M-3).
    assert estado.json()["initialized"] is True and estado.json()["sealed"] is True
    assert estado.json()["t"] == fake.umbral
    assert isinstance(estado, httpx.Response)
    fake.unseal()
    assert (await _post(fake, "/v1/auth/token/lookup-self", {})).status_code == 403
    assert fake.llamadas("lookup-self")


async def test_firma_ed25519() -> None:
    fake = FakeTransit()
    firma = (await _post(fake, "/v1/transit/sign/apex-sign-audit", {"input": _b64(b"x")})).json()[
        "data"
    ]["signature"]
    valida = await _post(
        fake, "/v1/transit/verify/apex-sign-audit", {"input": _b64(b"x"), "signature": firma}
    )
    falsa = await _post(
        fake, "/v1/transit/verify/apex-sign-audit", {"input": _b64(b"y"), "signature": firma}
    )
    assert valida.json()["data"]["valid"] is True and falsa.json()["data"]["valid"] is False
