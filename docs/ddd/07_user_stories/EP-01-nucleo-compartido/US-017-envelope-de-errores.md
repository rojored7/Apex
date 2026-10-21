# US-017 · Como equipo quiero que todo error del API salga con el mismo envelope `{ error: { code, message, field?, existing_id? } }` para que el front muestre siempre el mensaje correcto en el campo correcto

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/errors.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero una jerarquía de errores de dominio y handlers de FastAPI que conviertan toda excepción en el envelope de error
para que el front tenga un solo contrato de errores y ningún detalle interno se filtre al cliente

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `04_architecture_decision.md` sección 5 (envelope `{ "error": { "code", "message", "field"? } }`); `05_service_design.md` sección 4 (`existing_id` en duplicados); "Seguridad" (errores sin datos sensibles).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `DomainError(code, message, field=None, existing_id=None, status=400)` y subclases `NotFoundError` (404), `ConflictError` (409), `ValidationFailed` (422), `ForbiddenError` (403), `UnauthorizedError` (401); handler para `RequestValidationError` de Pydantic que toma el primer error y llena `field` con la ruta (`first_payment.amount_cop`); handler para `HTTPException`; handler genérico de `Exception` que responde 500 con `code = "internal_error"` y un mensaje genérico, y loguea el detalle con un `request_id`; esquema `ErrorResponse` publicado en OpenAPI para todas las rutas.
- **Front:** No aplica (lo consume US-059).

## Criterios de aceptación

1. Un `ConflictError("member_duplicate", "Ya existe un socio con este documento", field="document", existing_id=<uuid>)` produce 409 con exactamente ese envelope.
2. Un cuerpo inválido produce 422 con `code = "validation_error"` y `field` con la ruta del primer campo inválido.
3. Una excepción no controlada produce 500 con `code = "internal_error"`, sin traza, sin SQL y sin valores de la petición en la respuesta.
4. Todas las respuestas de error tienen `Content-Type: application/json` y el campo raíz `error`.
5. El esquema `ErrorResponse` aparece en `docs/openapi.json` para las respuestas 4xx y 5xx.
6. Los mensajes al usuario están en español.

## Escenarios BDD

```gherkin
# language: es
Característica: Errores con un solo formato

  Escenario: Error de dominio con campo y registro existente
    Dado un service que lanza un conflicto por documento duplicado
    Cuando el router responde
    Entonces el código HTTP es 409
    Y el cuerpo tiene "error.code", "error.message", "error.field" y "error.existing_id"

  Escenario: Validación de entrada
    Dado una petición con "amount_cop" igual a "12.5"
    Cuando la valida Pydantic
    Entonces el código HTTP es 422
    Y "error.field" es "amount_cop"

  Escenario: Error inesperado sin filtrar detalles
    Dado un handler que lanza una excepción no controlada
    Cuando el cliente recibe la respuesta
    Entonces el código HTTP es 500
    Y el cuerpo no contiene la traza ni el SQL
```

## Endpoints

- Ninguno propio; aplica a todos.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** conversión de `RequestValidationError` a `field` (rutas anidadas y listas).
- **Pruebas:** router con `httpx.AsyncClient` sobre una app de prueba con rutas que lanzan cada tipo.
- **Archivos principales:** `api/src/app/core/errors.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest.

## INVEST

- **Independiente:** no depende de base de datos.
- **Negociable:** catálogo inicial de códigos.
- **Valiosa:** contrato único de errores para todo el front.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** respuestas verificables por tipo.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router en verde
- [ ] Revisión de PR aprobada
