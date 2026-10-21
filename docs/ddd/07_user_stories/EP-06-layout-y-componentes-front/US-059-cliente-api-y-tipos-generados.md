# US-059 · Como equipo quiero un cliente HTTP único con tipos generados desde el contrato para que el front nunca use un campo que el API no tiene

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/core/api/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin pantalla propia; la usan todas)

## Historia

Como equipo
quiero un cliente HTTP único (`client.ts`) con base `/api/v1`, manejo del envelope de error y tipos generados desde `docs/openapi.json`
para que todas las pantallas hablen con el API de la misma forma y el build falle si el front usa un campo que el contrato no tiene

## Contexto de dominio

- **Aggregate / entidades:** ninguno; consume el contrato HTTP de todos los módulos.
- **Reglas que aplica:** contrato de listas `{ items, total, limit, offset }` (regla de datos 6, S2); envelope `{ "error": { "code", "message", "field"?, "existing_id"? } }` (`04_architecture_decision.md` sección 5); fechas ISO 8601 en UTC; dinero entero.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `parseApiError(response) -> ApiError`, `toQueryString(params) -> string`

## Alcance

- **Backend:** No aplica (consume `docs/openapi.json` de US-021).
- **Front:** `web/src/core/api/client.ts` (fetch con base `/api/v1`, cabecera `Authorization: Bearer`, `credentials` según la estrategia de sesión, timeout, parseo del envelope a `ApiError` tipado, punto de enganche `onUnauthorized` para el refresh que conecta US-043), `web/src/core/api/types.ts` generado con `openapi-typescript`, script `npm run gen:api` y chequeo en CI.

## Criterios de aceptación

1. Toda llamada del front al API pasa por `client.ts`; una regla de ESLint (`no-restricted-globals` o `no-restricted-syntax`) prohíbe `fetch` directo fuera de `core/api/`.
2. La base de las rutas es `/api/v1`; ninguna feature escribe el prefijo a mano.
3. Una respuesta 4xx o 5xx con envelope se convierte en un `ApiError` con `status`, `code`, `message` y, si vienen, `field` y `existing_id`; una respuesta sin envelope (por ejemplo 502 de Nginx) produce `ApiError` con `code = "network_error"` y un mensaje genérico en español.
4. Una respuesta 401 invoca el gancho `onUnauthorized` una sola vez por petición y, si el gancho no está registrado, propaga el error.
5. `types.ts` se genera desde `docs/openapi.json` con `openapi-typescript`; el job de CI regenera el archivo y falla si difiere del versionado.
6. `npm run build` (con `tsc --noEmit` estricto) falla si una feature lee un campo que no existe en `types.ts`.
7. El cliente expone un tipo genérico `Page<T> = { items: T[]; total: number; limit: number; offset: number }` derivado del contrato y un helper `listParams({ limit, offset, ...filtros })` que nunca envía `limit` mayor que 200.
8. Las fechas llegan y se envían como cadenas ISO 8601 en UTC; el cliente no convierte zonas horarias (eso lo hace `format.ts`, US-060).
9. El cliente nunca escribe en `console` el cuerpo de una respuesta ni el token.

## Escenarios BDD

```gherkin
# language: es
Característica: Cliente HTTP del front

  Antecedentes:
    Dado que el API responde bajo "/api/v1"

  Escenario: Petición exitosa tipada
    Dado una feature que pide la lista de socios con limit 25 y offset 0
    Cuando el API responde 200 con items, total, limit y offset
    Entonces la feature recibe un Page con 25 elementos como máximo
    Y el tipo de cada elemento corresponde al esquema MemberRow del contrato

  Escenario: Error de validación con campo
    Dado una petición de creación de socio con documento repetido
    Cuando el API responde 409 con code "member_document_duplicated", field "document" y existing_id
    Entonces el cliente lanza un ApiError con status 409, field "document" y existing_id
    Y la feature puede enlazar al socio existente

  Escenario: Respuesta sin envelope
    Dado que Nginx responde 502 sin cuerpo JSON
    Cuando la feature hace cualquier petición
    Entonces el cliente lanza un ApiError con code "network_error"
    Y el mensaje está en español

  Escenario: Sesión vencida
    Dado que el access token venció
    Cuando el API responde 401
    Entonces el cliente invoca el gancho onUnauthorized una sola vez

  Escenario: Contrato desactualizado
    Dado que una feature lee el campo "cedula" que no existe en el contrato
    Cuando corre el build en CI
    Entonces el build falla con un error de tipos
```

## Endpoints

- Ninguno propio. Consume todos los de `/api/v1`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `parseApiError` con envelope completo, sin `field`, con `existing_id`, cuerpo no JSON y cuerpo vacío; `toQueryString` omite `undefined` y repite arreglos.
- **Pruebas:** Vitest con `fetch` simulado (MSW o stub) para 200, 401, 409, 422 y 502; prueba de regla ESLint; job de CI `gen:api` + `git diff --exit-code`.
- **Archivos principales:** `web/src/core/api/client.ts`, `web/src/core/api/errors.ts`, `web/src/core/api/types.ts`, `web/package.json` (script `gen:api`), `.github/workflows/ci.yml`.

## Supuestos

- Ninguno.

## Dependencias

- US-021 · Exportación de OpenAPI (fuente de `types.ts`).
- US-009 · Esqueleto del front (proyecto Vite y ESLint).

## INVEST

- **Independiente:** solo necesita el `openapi.json` exportado; no depende de ninguna pantalla.
- **Negociable:** la librería de mocks y el nombre de los helpers se pueden discutir.
- **Valiosa:** evita que cada pantalla maneje errores distinto y detecta desajustes de contrato en CI.
- **Estimable:** alcance acotado a un archivo, un generador y un chequeo.
- **Pequeña:** cabe en 2 a 3 días.
- **Testeable:** cada criterio tiene prueba unitaria o chequeo de CI.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
