# US-037 · Como equipo quiero CORS limitado a los orígenes de CORS_ORIGINS para que ninguna página ajena pueda llamar al API con la sesión de un usuario

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core` (`main.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 1
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero el middleware CORS configurado solo con los orígenes listados en `CORS_ORIGINS`
para que un sitio externo no pueda leer respuestas del API desde el navegador del personal

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `CLAUDE.md` Seguridad (CORS solo para el dominio del front).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `config.parse_origins(value) -> list[str]`

## Alcance

- **Backend:** `CORSMiddleware` con `allow_origins` desde `CORS_ORIGINS` (lista separada por comas, `list[str]` de US-011), métodos `GET, POST, PATCH, PUT, DELETE`, cabeceras `Authorization, Content-Type`, sin comodín `*`. Si `CORS_ORIGINS` contiene `*`, el arranque falla.
- **Front:** No aplica

## Criterios de aceptación

1. Un preflight `OPTIONS` desde un origen listado recibe `Access-Control-Allow-Origin` con ese origen.
2. Un preflight desde `https://evil.example` no recibe `Access-Control-Allow-Origin`.
3. `CORS_ORIGINS="*"` hace fallar el arranque con mensaje explícito.
4. `CORS_ORIGINS` vacío deshabilita CORS (el front se sirve por el mismo origen vía Nginx).

## Escenarios BDD

```gherkin
# language: es
Característica: CORS cerrado

  Escenario: Origen permitido
    Dado CORS_ORIGINS igual a "http://apex.local"
    Cuando llega un preflight desde "http://apex.local"
    Entonces la respuesta permite ese origen

  Escenario: Origen no listado
    Cuando llega un preflight desde "https://evil.example"
    Entonces la respuesta no incluye Access-Control-Allow-Origin

  Escenario: Comodín prohibido
    Dado CORS_ORIGINS igual a "*"
    Cuando arranca el API
    Entonces el arranque falla
```

## Endpoints

- Todos (middleware).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `parse_origins`.
- **Pruebas:** router con preflight.
- **Archivos principales:** `api/src/app/main.py`, `api/src/app/core/config.py`, `api/tests/core/test_cors.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-020 · create_app, migraciones y health

## INVEST

- **Independiente:** solo la app.
- **Negociable:** lista de cabeceras.
- **Valiosa:** cierra un vector de abuso de sesión.
- **Estimable:** configuración.
- **Pequeña:** horas.
- **Testeable:** preflight permitido o no.

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
