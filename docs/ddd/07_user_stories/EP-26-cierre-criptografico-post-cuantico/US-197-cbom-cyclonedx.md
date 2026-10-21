# US-197 · Como administrador quiero exportar el inventario criptográfico en formato CycloneDX para entregarlo a quien audite la protección de datos

- **Épica:** EP-26 · Cierre criptográfico post-cuántico
- **Bounded context:** Crypto (`core/crypto`)
- **Versión:** v1.0
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Llaves` (`/sistema/llaves`, botón "Exportar CBOM", formato CycloneDX)

## Historia

Como administrador
quiero generar el CBOM en CycloneDX desde la terminal o desde la pantalla de llaves
para entregar a un auditor un inventario estándar de qué algoritmos y llaves protegen los datos

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (lectura).
- **Reglas que aplica:** Q26 (el CBOM básico ya existe desde v0.3, US-146; v1.0 agrega el formato CycloneDX), nunca se expone material de llave, RN-15.
- **Eventos que emite:** ninguno (la exportación se audita)
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.to_cyclonedx(keys) -> dict`

## Alcance

- **Backend:** `cli cbom --format cyclonedx [--out archivo]`; `GET /crypto/cbom?format=cyclonedx` en el router admin de US-146.
- **Front:** selector de formato (JSON interno o CycloneDX) en el botón "Exportar CBOM".

## Criterios de aceptación

1. `cli cbom --format cyclonedx` escribe un documento CycloneDX 1.6 con un componente `cryptographic-asset` por llave de `crypto_keys` (algoritmo, propósito, proveedor, versión, estado, `data_class`, fechas de rotación) y código de salida 0.
2. El documento valida contra el esquema oficial de CycloneDX en la prueba (esquema versionado en `api/tests/fixtures/`).
3. Ninguna salida contiene `wrapped_material` ni material en claro.
4. `GET /api/v1/crypto/cbom?format=cyclonedx` con rol admin descarga el mismo documento con `Content-Type: application/vnd.cyclonedx+json`; coach y member reciben 403; sin token, 401; formato desconocido, 422.
5. Cada exportación queda auditada con acción `export` y el usuario.
6. Las llaves `retired` aparecen con su estado; las de firma ML-DSA y la envoltura ML-KEM (US-198) aparecen con su algoritmo real.

## Escenarios BDD

```gherkin
# language: es
Característica: CBOM en CycloneDX

  Escenario: Exportar el CBOM para un auditor
    Dado que el sistema tiene llaves activas, en descifrado y retiradas
    Cuando el administrador exporta el CBOM en formato CycloneDX
    Entonces obtiene un documento que valida contra el esquema de CycloneDX
    Y cada llave aparece con su algoritmo, proveedor, versión y estado
    Y ningún material de llave aparece en el documento

  Escenario: Coach intenta exportar el CBOM
    Cuando un coach pide el CBOM
    Entonces el sistema responde que no tiene permiso
```

## Endpoints

- `GET /api/v1/crypto/cbom?format=json|cyclonedx` — rol(es): admin — códigos: 200, 401, 403, 422
- Comando: `cli cbom --format cyclonedx [--out archivo]`

## Pantalla

- `Llaves`: menú del botón "Exportar CBOM" con las dos opciones.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `to_cyclonedx` con llaves de cada estado y algoritmo.
- **Pruebas:** pura con validación de esquema (librería de validación JSON Schema con licencia permitida); router; CLI.
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `router.py`, `api/src/app/cli.py`.

## Supuestos

- Supuesto: se usa CycloneDX 1.6 (primera versión con `cryptographic-asset` estable); la épica no fija versión.

## Dependencias

- US-146 · Exportar CBOM (router y contenido base)

## INVEST

- **Independiente:** un serializador más sobre datos existentes.
- **Negociable:** versión de CycloneDX.
- **Valiosa:** evidencia estándar para auditoría.
- **Estimable:** una función pura y dos salidas.
- **Pequeña:** pocos días.
- **Testeable:** validación contra esquema.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] `docs/openapi.json` regenerado
- [ ] Chequeo de licencias en verde
- [ ] Revisión de PR aprobada
