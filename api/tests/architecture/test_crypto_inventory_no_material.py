"""El inventario de llaves nunca expone material ni referencias (S6-B1, US-143; S6-D13, L-5).

Dos recorridos: el contrato OpenAPI (ninguna propiedad `wrapped_material`, `key_ref`, `material`
ni `reference` alcanzable desde la respuesta de `GET /crypto/keys`) y una respuesta real con una
fila `sign` y otra `decrypt_only` (ninguna clave con esos nombres y ningún valor con prefijo
`vault:`, `apxw1`, `local:` ni `apex-sign-audit`). Los controles prueban el recorrido con
estructuras que sí deben fallar.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario
from tests.crypto.conftest import KEYS_URL, llaves_mixtas

CLAVES_PROHIBIDAS = frozenset({"wrapped_material", "key_ref", "material", "reference"})
PREFIJOS_PROHIBIDOS = ("vault:", "apxw1", "local:", "apex-sign-audit")
SCHEMA_REF = "#/components/schemas/"


def claves_prohibidas_en_esquema(esquema: dict[str, Any], raiz: Any) -> list[str]:
    """Propiedades prohibidas alcanzables desde `raiz` siguiendo `$ref`, `items`, `anyOf`..."""
    vistos: set[str] = set()
    halladas: list[str] = []

    def visitar(nodo: Any) -> None:
        if isinstance(nodo, list):
            for hijo in nodo:
                visitar(hijo)
        elif isinstance(nodo, dict):
            ref = nodo.get("$ref")
            if isinstance(ref, str) and ref.startswith(SCHEMA_REF):
                nombre = ref.removeprefix(SCHEMA_REF)
                if nombre not in vistos:
                    vistos.add(nombre)
                    visitar(esquema["components"]["schemas"][nombre])
            for propiedad, hijo in nodo.get("properties", {}).items():
                if propiedad in CLAVES_PROHIBIDAS:
                    halladas.append(propiedad)
                visitar(hijo)
            for clave, hijo in nodo.items():
                if clave != "properties":
                    visitar(hijo)

    visitar(raiz)
    return halladas


def problemas_en_json(valor: Any, ruta: str = "$") -> list[str]:
    """Claves y valores prohibidos en una respuesta JSON ya decodificada."""
    problemas: list[str] = []
    if isinstance(valor, dict):
        for clave, hijo in valor.items():
            if clave in CLAVES_PROHIBIDAS:
                problemas.append(f"{ruta}.{clave}: clave prohibida")
            problemas += problemas_en_json(hijo, f"{ruta}.{clave}")
    elif isinstance(valor, list):
        for n, hijo in enumerate(valor):
            problemas += problemas_en_json(hijo, f"{ruta}[{n}]")
    elif isinstance(valor, str) and valor.startswith(PREFIJOS_PROHIBIDOS):
        problemas.append(f"{ruta}: valor con prefijo prohibido")
    return problemas


def test_el_contrato_openapi_del_inventario_no_declara_material(settings_prueba: Settings) -> None:
    esquema = create_app(settings_prueba, run_migrations_on_startup=False).openapi()
    operacion = esquema["paths"][KEYS_URL]["get"]

    assert claves_prohibidas_en_esquema(esquema, operacion["responses"]) == []
    assert "KeysPage" in esquema["components"]["schemas"] or any(
        "Keys" in nombre for nombre in esquema["components"]["schemas"]
    )


async def test_una_respuesta_real_no_trae_claves_ni_valores_de_material(
    app_http: AsyncClient,
    session: AsyncSession,
    bus_listo: object,
    proveedor_local: object,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    await llaves_mixtas(session, proveedor_local)  # type: ignore[arg-type]
    admin = await usuario_real("admin")

    r = await app_http.get(KEYS_URL, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert any(i["purpose"] == "sign" for i in cuerpo["items"]), "la fila sign debe estar"
    assert problemas_en_json(cuerpo) == []


def test_control_el_recorrido_detecta_claves_y_valores_prohibidos() -> None:
    sucio = {"items": [{"wrapped_material": "x"}, {"a": "vault:transit/keys/k"}, {"b": "apxw1.x"}]}
    assert len(problemas_en_json(sucio)) == 3
    assert problemas_en_json({"items": [{"a": "local:/x"}, {"a": "apex-sign-audit"}]}) != []
    assert problemas_en_json({"items": [{"data_class": "member.document", "version": 1}]}) == []
    esquema = {
        "components": {
            "schemas": {
                "A": {"properties": {"hijo": {"$ref": f"{SCHEMA_REF}B"}}},
                "B": {"properties": {"key_ref": {"type": "string"}}},
            }
        }
    }
    assert claves_prohibidas_en_esquema(esquema, {"$ref": f"{SCHEMA_REF}A"}) == ["key_ref"]
