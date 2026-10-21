# US-021 · Como equipo quiero que CI regenere `docs/openapi.json` y falle si el archivo versionado está desactualizado para que el front genere sus tipos siempre desde el contrato real

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (contrato HTTP)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero un comando que exporte el OpenAPI de `create_app()` a `docs/openapi.json` y un paso de CI que compare
para que el front y el API nunca diverjan en silencio

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `04_architecture_decision.md` sección 5 (OpenAPI exportado a `docs/openapi.json`; el front genera tipos desde ahí); Tarea 12 de `docs/PLAN.md`.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** script `uv run python -m app.cli export-openapi docs/openapi.json` que escribe el JSON con claves ordenadas e indentación fija (salida determinista); paso de CI que ejecuta el comando y luego `git diff --exit-code docs/openapi.json`.
- **Front:** No aplica (US-059 genera `types.ts` desde este archivo).

## Criterios de aceptación

1. Ejecutar el comando dos veces seguidas produce archivos idénticos byte a byte.
2. Si un PR cambia un schema o una ruta y no actualiza `docs/openapi.json`, CI falla con un mensaje que indica el comando a correr.
3. Si el archivo está al día, el paso de CI pasa.
4. El archivo incluye el esquema `ErrorResponse` y el prefijo `/api/v1` en las rutas de módulos.
5. El comando no necesita base de datos ni llaves para ejecutarse.

## Escenarios BDD

```gherkin
# language: es
Característica: Contrato OpenAPI versionado

  Escenario: Contrato al día
    Dado que "docs/openapi.json" coincide con la app
    Cuando corre el paso de CI de OpenAPI
    Entonces el paso termina en verde

  Escenario: Contrato desactualizado
    Dado un PR que agrega un campo a un schema de respuesta
    Y no regenera "docs/openapi.json"
    Cuando corre el paso de CI de OpenAPI
    Entonces el paso falla indicando regenerar el archivo

  Escenario: Salida determinista
    Dado la misma versión del código
    Cuando exporto el OpenAPI dos veces
    Entonces ambos archivos son idénticos
```

## Endpoints

- Ninguno nuevo (FastAPI ya expone `/openapi.json` en desarrollo).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** paso de CI; prueba de determinismo en `tests/core/test_openapi_export.py`.
- **Archivos principales:** `api/src/app/cli.py` (subcomando), `.github/workflows/ci.yml`, `docs/openapi.json`.

## Supuestos

- Supuesto: el `lifespan` de arranque (migraciones, llaves) no se ejecuta al exportar; el comando construye la app sin entrar al ciclo de vida.

## Dependencias

- US-020 · create_app, migraciones y health.
- US-003 · Pipeline CI.

## INVEST

- **Independiente:** solo requiere la app y CI.
- **Negociable:** formato exacto del archivo.
- **Valiosa:** evita roturas entre front y API.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** paso de CI en rojo y en verde.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Paso de CI verificado en rojo y en verde
- [ ] `docs/openapi.json` versionado
- [ ] Revisión de PR aprobada
