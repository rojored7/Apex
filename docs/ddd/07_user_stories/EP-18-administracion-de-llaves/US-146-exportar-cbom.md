# US-146 · Como administrador quiero exportar el inventario criptográfico (CBOM) para entregárselo a quien audite la protección de datos

- **Épica:** EP-18 · Administración de llaves de cifrado
- **Bounded context:** Crypto (`core/crypto/service.py`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Llaves` (`/sistema/llaves`, botón Exportar CBOM)

## Historia

Como administrador
quiero descargar el inventario criptográfico del sistema
para entregar evidencia de qué algoritmos, llaves y proveedores protegen los datos de los socios

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey`.
- **Reglas que aplica:** Q26 (el CBOM se adelanta a v0.3 dentro de EP-18; el formato CycloneDX queda para EP-26); "el material en claro nunca se persiste" ni se exporta; RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.build_cbom(keys, generated_at) -> dict`

## Alcance

- **Backend:** `GET /api/v1/crypto/cbom` que arma un JSON con todas las llaves (cualquier estado) y lo devuelve como descarga; auditado con acción `export`.
- **Front:** botón "Exportar CBOM" habilitado en `Llaves`.

## Criterios de aceptación

1. Exige rol `admin`; coach y socio reciben 403.
2. La respuesta es `application/json` con `Content-Disposition: attachment; filename="apex-cbom-AAAA-MM-DD.json"` (fecha de Bogotá).
3. El documento incluye `generated_at` (UTC), versión de APEX y, por llave: `data_class`, `purpose`, `algorithm`, `provider`, `version`, `state`, `created_at`, `rotated_at`; incluye también los algoritmos fijos del sistema que no viven en `crypto_keys` (JWT `Ed25519`, contraseñas `argon2id`, índice `HMAC-SHA256`).
4. El documento no contiene `wrapped_material` ni ningún material de llave (prueba de contrato).
5. Cada descarga deja una fila de auditoría con acción `export`, el usuario y el número de llaves exportadas.
6. `build_cbom` es pura y produce la misma salida para la misma entrada (orden estable por `data_class`, `purpose`, `version`).

## Escenarios BDD

```gherkin
# language: es
Característica: Exportar el inventario criptográfico

  Escenario: El administrador descarga el CBOM
    Dado que inicié sesión como administrador
    Y existen 9 llaves registradas
    Cuando pulso "Exportar CBOM"
    Entonces se descarga un archivo JSON con las 9 llaves y sus algoritmos
    Y el archivo no contiene material de llave
    Y queda una fila de auditoría "export" con mi usuario

  Escenario: Un coach intenta descargar el CBOM
    Dado que inicié sesión como coach
    Cuando pido GET /api/v1/crypto/cbom
    Entonces recibo 403
```

## Endpoints

- `GET /api/v1/crypto/cbom` — rol(es): admin — entrada: ninguna — salida: archivo JSON — códigos: 200, 401, 403

## Pantalla

- `Llaves`, botón Exportar CBOM en el encabezado de la pantalla. Estado de error si la descarga falla.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `build_cbom` (orden estable, sin campos de material, algoritmos fijos incluidos).
- **Pruebas:** pura, router (rol, cabeceras, auditoría), front (botón visible solo para admin).
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `api/src/app/core/crypto/router.py`.

## Supuestos

- Supuesto: en v0.3 el CBOM es un JSON propio (no CycloneDX); EP-26 (US-197) agrega `--format cyclonedx` sin cambiar este endpoint, o lo extiende con `?format=cyclonedx`.

## Dependencias

- US-143 · Inventario de llaves (pantalla y lectura de llaves)

## INVEST

- **Independiente:** solo lee llaves.
- **Negociable:** campos del JSON.
- **Valiosa:** evidencia entregable para auditorías.
- **Estimable:** una función pura y un endpoint.
- **Pequeña:** sí.
- **Testeable:** contrato del archivo verificable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba del botón; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría de la exportación verificada
- [ ] Revisión de PR aprobada
