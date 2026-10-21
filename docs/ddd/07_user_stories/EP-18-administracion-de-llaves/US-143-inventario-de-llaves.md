# US-143 · Como administrador quiero ver el inventario de llaves de cifrado para saber qué llave protege cada clase de dato y cuándo se rotó

- **Épica:** EP-18 · Administración de llaves de cifrado
- **Bounded context:** Crypto (`core/crypto/router.py`, `core/crypto/service.py`, esquema `crypto`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Llaves` (`/sistema/llaves`)

## Historia

Como administrador
quiero ver el inventario de llaves de cifrado por clase de dato
para saber qué llave protege cada dato, con qué algoritmo y proveedor, y cuándo se rotó por última vez

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (`purpose`, `data_class`, `algorithm`, `provider`, `version`, `state`, `rotated_at`, `rotate_by`).
- **Reglas que aplica:** invariante "una sola llave `active` por (`purpose`, `data_class`)"; "el material en claro nunca se persiste"; RN-15 (rol por endpoint); RN-13 (los datos sensibles se cifran por clase de dato).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `crypto.service.list_keys(filters, limit, offset)` y `GET /api/v1/crypto/keys` solo admin; respuesta sin `wrapped_material` ni ningún material de llave.
- **Front:** pestaña "Inventario" de la pantalla `Llaves` con `DataTable`, filtros por `purpose`, `state` y `provider`, y `StatusTag` del estado.

## Criterios de aceptación

1. `GET /api/v1/crypto/keys` exige rol `admin`; un coach recibe 403 y un socio recibe 403; sin token, 401.
2. Cada fila incluye `id`, `data_class`, `purpose`, `algorithm`, `provider`, `version`, `state`, `rotated_at`, `rotate_by` y `created_at`; las fechas van en ISO 8601 UTC.
3. La respuesta nunca contiene `wrapped_material` ni ningún campo con material de llave, envuelto o en claro (prueba de contrato que inspecciona el JSON y el esquema de OpenAPI).
4. La lista pagina con `limit` (1 a 200, por defecto 25) y `offset` y responde `{ items, total, limit, offset }`; `limit=201` devuelve 422.
5. Los filtros `purpose`, `state`, `provider` y `data_class` se combinan con AND.
6. Por cada par (`purpose`, `data_class`) aparece exactamente una llave `active`; las `decrypt_only` y `retired` se muestran con su estado.
7. La pantalla muestra las fechas en hora de Bogotá y el estado con texto (el color no es el único portador).
8. Consultar el inventario no escribe en `crypto_ops` (es lectura de metadatos, no una operación criptográfica).

## Escenarios BDD

```gherkin
# language: es
Característica: Inventario de llaves de cifrado

  Antecedentes:
    Dado que existen llaves para "member.document", "member.phone" y "audit.signature"
    Y la llave de "member.document" versión 1 está "decrypt_only" y la versión 2 está "active"

  Escenario: El administrador consulta el inventario
    Dado que inicié sesión como administrador
    Cuando abro la pantalla de llaves
    Entonces veo una fila por cada llave con su clase de dato, algoritmo, proveedor, versión y estado
    Y la llave versión 2 de "member.document" aparece como "Activa"
    Y ninguna fila muestra material de llave

  Escenario: Un coach intenta ver las llaves
    Dado que inicié sesión como coach
    Cuando pido GET /api/v1/crypto/keys
    Entonces recibo 403 con el envelope de error
```

## Endpoints

- `GET /api/v1/crypto/keys` — rol(es): admin — entrada: `purpose?`, `state?`, `provider?`, `data_class?`, `limit`, `offset` — salida: `{ items: CryptoKeyOut[], total, limit, offset }` — códigos: 200, 401, 403, 422

## Pantalla

- `Llaves` en `/sistema/llaves`, pestaña de inventario. Estados de carga, vacío ("no hay llaves registradas", solo posible antes de `init-keys`) y error. La entrada de menú solo existe para admin.

## Notas técnicas

- **Migración:** no (las tablas existen desde US-024).
- **Trigger / restricciones:** ninguna nueva.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** router (rol, paginación, ausencia de material), service con base real (filtros), front (tabla y filtros).
- **Archivos principales:** `api/src/app/core/crypto/router.py`, `api/src/app/core/crypto/service.py`, `web/src/features/system/pages/KeysPage.tsx`.

## Supuestos

- Supuesto: cada fila incluye `records_count` (número de registros cifrados con esa llave) para advertir el tamaño antes de rotar, como pide el riesgo de EP-18; si el conteo es caro se calcula por `data_class` y no por versión.

## Dependencias

- US-024 · Tablas crypto_keys, ops y jobs (fuente de datos)
- US-034 · Dependencias current_user y require_role (rol admin)
- US-061 · PanelLayout (pantalla)
- US-063 · DataTable y paginación (tabla)

## INVEST

- **Independiente:** solo lee `crypto_keys`; no depende de la rotación ni de la bitácora.
- **Negociable:** los filtros y columnas visibles se pueden ajustar.
- **Valiosa:** hace gobernable y demostrable el cifrado sin terminal.
- **Estimable:** un endpoint de lectura y una tabla.
- **Pequeña:** cabe en pocos días.
- **Testeable:** contrato sin material y 403 para coach son binarios.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
