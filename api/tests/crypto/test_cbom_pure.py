"""`build_cbom` pura (S6-B3, US-146; S6-D17, S6-D57, Q26, L-5). Rojo B3.

Sin base ni HTTP: el CBOM `apex-cbom/1` se arma desde las filas del inventario. Orden estable por
`(data_class, purpose, version)`, algoritmos fijos completos, `tls` declarado por configuracion,
cada llave con nueve campos exactos (sin `records_count` ni `age_days`) y nada de material.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.crypto import cbom
from app.core.crypto.cbom import CBOM_FORMAT, FIXED_ALGORITHMS, build_cbom
from app.core.crypto.schemas import CryptoKeyOut, ProviderSummary

AHORA = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
CREADA = datetime(2026, 10, 1, 12, 30, 5, tzinfo=UTC)
ROTADA = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

CAMPOS_DE_LLAVE = {
    "id",
    "purpose",
    "data_class",
    "algorithm",
    "version",
    "state",
    "provider",
    "created_at",
    "rotated_at",
}
ALGORITMOS_FIJOS = {"Ed25519", "argon2id", "HMAC-SHA256", "SHA-256", "age"}
ALGORITMO_POR_PROPOSITO = {"encrypt": "A256GCM", "index": "HMAC-SHA256", "sign": "Ed25519"}


def llave(
    data_class: str = "member.document",
    purpose: str = "encrypt",
    version: int = 1,
    *,
    state: str = "active",
    provider: str = "local",
    rotated_at: datetime | None = None,
    key_id: UUID | None = None,
) -> CryptoKeyOut:
    return CryptoKeyOut(
        id=key_id or uuid4(),
        purpose=purpose,  # type: ignore[arg-type]
        data_class=data_class,
        algorithm=ALGORITMO_POR_PROPOSITO[purpose],
        version=version,
        state=state,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        created_at=CREADA,
        rotated_at=rotated_at,
        age_days=41,
        records_count=1234,
    )


def armar(
    llaves: list[CryptoKeyOut] | None = None,
    *,
    tls_declared: bool = False,
    app_version: str = "abc1234",
    provider: ProviderSummary | None = None,
) -> dict[str, Any]:
    return build_cbom(
        llaves if llaves is not None else [llave()],
        app_version=app_version,
        generated_at=AHORA,
        provider=provider or ProviderSummary(names=["local"], state="ok"),
        tls_declared=tls_declared,
    )


def instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def test_el_formato_es_apex_cbom_1() -> None:
    assert CBOM_FORMAT == "apex-cbom/1"
    assert armar()["format"] == "apex-cbom/1"


def test_el_cbom_lleva_exactamente_las_claves_de_primer_nivel() -> None:
    assert set(armar()) == {
        "format",
        "generated_at",
        "app_version",
        "provider",
        "keys",
        "fixed_algorithms",
        "tls",
    }


def test_generated_at_app_version_y_provider_vienen_de_los_argumentos() -> None:
    cuerpo = armar(
        app_version="9f8e7d6", provider=ProviderSummary(names=["local", "openbao"], state="sealed")
    )

    assert cuerpo["app_version"] == "9f8e7d6"
    assert cuerpo["provider"] == {"names": ["local", "openbao"], "state": "sealed"}
    assert instante(cuerpo["generated_at"]) == AHORA


def test_el_orden_es_estable_por_data_class_purpose_version() -> None:
    llaves = [
        llave("member.phone", "index", 1),
        llave("member.email", "encrypt", 2, state="decrypt_only"),
        llave("member.email", "encrypt", 1, state="retired"),
        llave("audit.signature", "sign", 1),
        llave("member.email", "index", 1),
        llave("member.document", "encrypt", 1),
    ]
    esperado = [
        ("audit.signature", "sign", 1),
        ("member.document", "encrypt", 1),
        ("member.email", "encrypt", 1),
        ("member.email", "encrypt", 2),
        ("member.email", "index", 1),
        ("member.phone", "index", 1),
    ]

    for semilla in range(5):
        barajadas = list(llaves)
        random.Random(semilla).shuffle(barajadas)  # noqa: S311
        salida = armar(barajadas)["keys"]
        assert [(k["data_class"], k["purpose"], k["version"]) for k in salida] == esperado


def test_cada_llave_lleva_exactamente_los_nueve_campos() -> None:
    rotada = llave("member.email", "encrypt", 1, state="decrypt_only", rotated_at=ROTADA)
    activa = llave("member.email", "encrypt", 2, provider="openbao")

    salida = armar([rotada, activa])["keys"]

    assert len(salida) == 2
    for item in salida:
        assert set(item) == CAMPOS_DE_LLAVE, set(item) ^ CAMPOS_DE_LLAVE


def test_los_valores_de_la_llave_se_copian_sin_cambiar() -> None:
    clave = uuid4()
    entrada = llave(
        "member.email",
        "encrypt",
        3,
        state="decrypt_only",
        provider="openbao",
        rotated_at=ROTADA,
        key_id=clave,
    )

    item = armar([entrada])["keys"][0]

    assert item["id"] == str(clave)
    assert (item["purpose"], item["data_class"], item["algorithm"]) == (
        "encrypt",
        "member.email",
        "A256GCM",
    )
    assert (item["version"], item["state"], item["provider"]) == (3, "decrypt_only", "openbao")
    assert instante(item["created_at"]) == CREADA
    assert instante(item["rotated_at"]) == ROTADA


def test_rotated_at_es_null_si_la_llave_no_roto() -> None:
    item = armar([llave()])["keys"][0]

    assert "rotated_at" in item and item["rotated_at"] is None


def test_sin_records_count_ni_age_days_en_ninguna_llave() -> None:
    cuerpo = json.dumps(armar([llave(), llave("member.phone", "index")]))

    assert "records_count" not in cuerpo
    assert "age_days" not in cuerpo


def test_un_inventario_vacio_da_keys_vacio() -> None:
    assert armar([])["keys"] == []


def test_fixed_algorithms_declara_los_seis_usos_del_sistema() -> None:
    salida = armar()["fixed_algorithms"]

    assert isinstance(salida, list) and len(salida) == 6
    for fila in salida:
        assert set(fila) == {"use", "algorithm"}
    assert {a["algorithm"] for a in salida} == ALGORITMOS_FIJOS
    usos = [a["use"] for a in salida]
    assert len(set(usos)) == 6, usos
    pares = " ".join(f"{a['use']}={a['algorithm']}" for a in salida).lower()
    for fragmento in ("jwt", "pass", "index", "chain", "sign", "backup"):
        assert fragmento in pares, (fragmento, pares)


def test_las_parejas_uso_algoritmo_son_las_del_plan() -> None:
    salida = {a["use"].lower(): a["algorithm"] for a in armar()["fixed_algorithms"]}

    def de(fragmento: str) -> str:
        halladas = [alg for uso, alg in salida.items() if fragmento in uso]
        assert len(halladas) >= 1, (fragmento, salida)
        return halladas[0]

    assert de("jwt") == "Ed25519"
    assert de("pass") == "argon2id"
    assert de("index") == "HMAC-SHA256"
    assert de("chain") == "SHA-256"
    assert de("backup") == "age"
    assert [alg for uso, alg in salida.items() if "sign" in uso and "jwt" not in uso] == ["Ed25519"]


def test_la_constante_fixed_algorithms_es_la_que_sale_en_el_cbom() -> None:
    assert len(FIXED_ALGORITHMS) == 6
    assert armar()["fixed_algorithms"] == [dict(a) for a in FIXED_ALGORITHMS]


@pytest.mark.parametrize("dominio", [True, False])
def test_tls_declared_sale_del_argumento_y_la_fuente_es_la_configuracion(dominio: bool) -> None:
    assert armar(tls_declared=dominio)["tls"] == {"declared": dominio, "source": "configuration"}


def test_el_cbom_es_serializable_a_json_y_no_depende_del_orden_de_entrada() -> None:
    llaves = [llave("member.phone", "index"), llave("member.email", "encrypt")]

    primero = json.dumps(armar(llaves), sort_keys=True)
    segundo = json.dumps(armar(list(reversed(llaves))), sort_keys=True)

    assert primero == segundo


def test_no_muta_la_lista_de_entrada() -> None:
    llaves = [llave("member.phone", "index"), llave("audit.signature", "sign")]
    copia = list(llaves)

    armar(llaves)

    assert llaves == copia


def test_el_modulo_expone_las_constantes_y_la_funcion() -> None:
    assert {"CBOM_FORMAT", "FIXED_ALGORITHMS", "build_cbom"} <= set(dir(cbom))
