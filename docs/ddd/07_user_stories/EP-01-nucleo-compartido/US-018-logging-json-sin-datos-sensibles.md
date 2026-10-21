# US-018 · Como equipo quiero logs en JSON a stdout que nunca impriman campos cifrados ni tokens para que diagnosticar un problema no exponga datos personales

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/logging.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero logs estructurados en JSON a stdout con un filtro que reemplace valores sensibles
para que los logs del contenedor sirvan para depurar sin convertirse en una fuga de cédulas, teléfonos o tokens

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** "Calidad y Git" de `CLAUDE.md` (logs en JSON a stdout); `04_architecture_decision.md` sección 6 (nunca se loguea un campo cifrado ni un token); RN-13.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `logging.redact(record_dict) -> dict`

## Alcance

- **Backend:** formateador JSON (`timestamp` UTC ISO 8601, `level`, `logger`, `message`, `request_id`, `path`, `status`, `duration_ms`); middleware que asigna `request_id` y loguea una línea por petición sin cuerpo ni query string completa; filtro `redact` que reemplaza por `"[redacted]"` cualquier clave de una lista (`password`, `token`, `refresh_token`, `access_token`, `authorization`, `document`, `phone`, `email`, `birth_date`, `emergency_contact`, `kek`, `dek`, `secret`) y cualquier valor que empiece por `apx1.` o parezca JWT (`eyJ...`); nivel desde `Settings.LOG_LEVEL`; Uvicorn y SQLAlchemy configurados para no loguear parámetros de consultas.
- **Front:** No aplica.

## Criterios de aceptación

1. Cada línea de log es un objeto JSON válido en una sola línea.
2. Loguear `{"password": "x", "document": "1020304"}` produce `[redacted]` en ambos valores.
3. Un valor que empieza por `apx1.` o por `eyJ` se reemplaza por `[redacted]` aunque la clave no esté en la lista.
4. El log de acceso por petición no incluye el cuerpo, ni la cabecera `Authorization`, ni parámetros `q` de búsqueda (podrían ser un documento).
5. Los parámetros de SQL no aparecen en logs (`echo` desactivado y `hide_parameters=True` en el engine).
6. Una prueba de arquitectura ejecuta un login, una creación de socio y un `reveal` con captura de logs y verifica que ni el token ni el documento aparecen en la salida (activa cuando existan esas historias).

## Escenarios BDD

```gherkin
# language: es
Característica: Logs sin datos sensibles

  Escenario: Clave sensible redactada
    Dado un log con el campo "document" igual a "1020304"
    Cuando se escribe a stdout
    Entonces la línea es JSON válido
    Y el valor de "document" es "[redacted]"

  Escenario: Token por su forma
    Dado un mensaje que contiene un JWT "eyJhbGciOi..."
    Cuando se escribe el log
    Entonces el JWT no aparece en la salida

  Escenario: Búsqueda por documento no queda en el log de acceso
    Dado una petición "GET /api/v1/members?q=1020304"
    Cuando se registra el log de acceso
    Entonces la línea contiene la ruta "/api/v1/members"
    Y no contiene "1020304"
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `redact` (anidado, listas, claves en mayúscula, valores `apx1.` y `eyJ`).
- **Pruebas:** puras y de router con `caplog`.
- **Archivos principales:** `api/src/app/core/logging.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-011 · Configuración desde .env (`LOG_LEVEL`).

## INVEST

- **Independiente:** no depende de módulos de negocio.
- **Negociable:** lista de claves redactadas.
- **Valiosa:** reduce el riesgo legal de los logs.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** captura de logs.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de router en verde
- [ ] Revisión de PR aprobada
