# US-054 · Como administrador quiero que la configuración del gimnasio se guarde por secciones validadas y auditadas para cambiarla sin romper el sistema y con rastro de quién la cambió

- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context:** Settings (esquema `settings`, módulo `settings`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (la pantalla `Config` la construye US-055)

## Historia

Como administrador
quiero que cada sección de la configuración tenga su propio esquema, versión y auditoría
para cambiar un valor sin dañar otra sección y saber siempre quién lo cambió

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection` (`key`, `value` JSON, `version`) (`02_domain_model.md` 2.14).
- **Reglas que aplica:** cada sección tiene esquema propio; auditado; `tv.device_token` se genera, no se escribe; RN-15 (solo admin); Q12 (nunca se guarda un secreto en la base); Q11 (contenido de `memberships` y `classes`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section(key, value) -> None | SettingsError`.

## Alcance

- **Backend:** modelo `settings_sections` y migración; registro de esquemas Pydantic por sección; `settings.service.get_section(key)`, `update_section(key, value, by)`; `GET /settings/{section}` y `PATCH /settings/{section}`; API interna `settings.service.get(key)` para los módulos consumidores.
- **Front:** No aplica

## Criterios de aceptación

1. Existe la migración que crea `settings.settings_sections` con `id` UUID, `key` único, `value` JSONB, `version` entero, `created_at`, `updated_at` y `created_by`, y la tabla tiene `__audited__ = True`.
2. `key` solo admite `gym`, `hours`, `payment_methods`, `channels`, `classes`, `memberships`, `tv` y `privacy` (`CHECK` en la base y enum en el código).
3. En v0.1 las secciones habilitadas son `gym`, `payment_methods`, `privacy` y `memberships`; `GET` o `PATCH` de `hours`, `channels`, `classes` o `tv` responde 404 `section_not_available` hasta que su épica la habilite (EP-21, EP-14, EP-23).
4. `GET /api/v1/settings/{section}` (admin) responde 200 con `{ key, value, version, updated_at, updated_by }`; si la sección nunca se guardó, devuelve los valores por defecto de su esquema con `version: 0`.
5. `PATCH /api/v1/settings/{section}` (admin) con `{ value, version }` valida con `validate_section`; si es válido guarda, incrementa `version` en 1 y responde 200.
6. Un `value` que no cumple el esquema responde 422 con `field` apuntando al campo (por ejemplo `value.name`); la sección no cambia.
7. Un `version` distinto del guardado responde 409 `version_conflict` (dos admins editando a la vez no se pisan).
8. Cada cambio deja auditoría `update` con `before` y `after` completos de la sección; ningún esquema admite campos de secretos (contraseñas, tokens de API, llaves), y un campo desconocido responde 422 (`extra = "forbid"`).
9. Un coach recibe 403 y un request sin token 401 en ambos endpoints.
10. Los demás módulos leen la configuración solo por `settings.service.get(key)`, nunca importando `settings.models` (prueba de arquitectura de US-022).

## Escenarios BDD

```gherkin
# language: es
Característica: Secciones de configuración validadas

  Antecedentes:
    Dado un admin con sesión
    Y la sección "gym" guardada con versión 3

  Escenario: Guardar una sección válida
    Cuando envía "PATCH /settings/gym" con un nombre válido y versión 3
    Entonces recibe 200 con versión 4
    Y hay una auditoría "update" de "settings_sections" con antes y después

  Escenario: Valor que no cumple el esquema
    Cuando envía "PATCH /settings/gym" con el nombre vacío
    Entonces recibe 422 con field "value.name"
    Y la sección sigue en versión 3

  Escenario: Edición simultánea
    Cuando envía "PATCH /settings/gym" con versión 2
    Entonces recibe 409 con código "version_conflict"

  Escenario: Sección aún no habilitada
    Cuando pide "GET /settings/tv" en v0.1
    Entonces recibe 404 con código "section_not_available"

  Escenario: El coach no puede ver la configuración
    Dado un coach con sesión
    Cuando pide "GET /settings/gym"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/settings/{section}` — rol(es): admin — salida: `{ key, value, version, updated_at, updated_by }` — códigos: 200, 401, 403, 404.
- `PATCH /api/v1/settings/{section}` — rol(es): admin — entrada: `{ value, version }` — salida: igual a GET — códigos: 200, 401, 403, 404, 409, 422.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; esquema `settings`, tabla `settings_sections` con índice único en `key`.
- **Trigger / restricciones:** `CHECK (key IN (...))`; `CHECK (version >= 0)`.
- **Funciones puras a probar:** `validate_section` por cada sección habilitada, con un caso válido y uno inválido, y con un campo desconocido.
- **Pruebas:** service con base real (versión, auditoría), router (403, 404, 409, 422 con `field`), arquitectura (nadie importa `settings.models`).
- **Archivos principales:** `api/src/app/modules/settings/models.py`, `schemas.py`, `service.py`, `router.py`; `api/migrations/versions/<rev>_settings_sections.py`.

## Supuestos

- Supuesto: el control de concurrencia usa `version` como bloqueo optimista con 409; el modelo tiene `version` pero no dice para qué.
- Supuesto: una sección de una versión futura responde 404 `section_not_available` en lugar de existir vacía.

## Dependencias

- US-016 · Hook de auditoría after_flush
- US-034 · Dependencias current_user y require_role

## INVEST

- **Independiente:** no depende de ninguna pantalla.
- **Negociable:** qué secciones se habilitan en cada versión es ajustable.
- **Valiosa:** base de todo lo configurable sin tocar archivos.
- **Estimable:** una tabla, dos endpoints y un registro de esquemas.
- **Pequeña:** dos o tres días.
- **Testeable:** cada respuesta tiene código fijo.

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
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `settings.settings_sections`
- [ ] Revisión de PR aprobada
