# US-102 · Como administrador quiero consultar la auditoría con filtros para responder quién hizo qué, cuándo y sobre qué registro

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`; modelos en `core/audit.py`, módulo `modules/audit` sin `models.py`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Auditoria` (`/sistema/auditoria`)

## Historia

Como administrador
quiero buscar en la auditoría por rango de fechas, usuario, tabla, registro y acción
para responder ante cualquier duda quién hizo qué, cuándo y sobre qué registro

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry` (append-only): `seq`, `at`, `user_id`, `action`, `table_name`, `record_id`, `before`, `after`, `prev_hash`, `hash`.
- **Reglas que aplica:** RN-16 (cadena de hashes; esta historia solo lee), RN-13 (los campos cifrados se guardan y muestran como blob, nunca en claro), regla de datos 6 (paginación y búsqueda), RN-15 (solo admin).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `audit.service.list(from, to, user_id, table, record_id, action, q, limit, offset)` y `GET /audit`. El nombre del usuario de cada fila se obtiene por `auth.service`.
- **Front:** pantalla `Auditoria` con `FilterBar` (rango de fechas, usuario, entidad, acción, búsqueda), `DataTable` (fecha y hora de Bogotá, usuario, acción, entidad, registro, `seq`) y `Pagination`. El detalle lo implementa US-103 y la verificación US-104.

## Criterios de aceptación

1. `GET /api/v1/audit` responde `{ items, total, limit, offset }`; `limit` 1 a 200 (25 por defecto); fuera de rango, 422.
2. Filtros: `from` y `to` (ISO 8601 con zona, sobre `at`), `user_id`, `table` (nombre de tabla auditada, por ejemplo `members`, `memberships`, `payments`, `plans`, `users`, `settings_sections`), `record_id` (UUID), `action` en `insert`, `update`, `delete`, `reveal`, `export`, `login`, `verify`; un `action` fuera de la lista devuelve 422.
3. `q` busca por coincidencia exacta de `record_id` o por correo del usuario que actuó (vía `auth.service`).
4. Orden por defecto `seq` descendente.
5. Las filas de la lista no incluyen `before` ni `after` (solo los metadatos); el detalle viene de US-103.
6. Toda acción sobre tablas auditadas de v0.1 (socios, planes, membresías, pagos, usuarios, settings) aparece en la lista con usuario y fecha (prueba de integración que crea una fila en cada tabla y la encuentra).
7. Rol: `require_role("admin")`; un coach recibe 403 y no ve "Auditoría" en el menú; sin token, 401.
8. La consulta no modifica ninguna fila de `audit.audit_log` (solo lectura).
9. Responde en menos de 500 ms con 100.000 filas y `limit=25` (índices por `at`, `table_name, record_id`, `user_id`).

## Escenarios BDD

```gherkin
# language: es
Característica: Consultar la auditoría

  Antecedentes:
    Dado que existen entradas de auditoría de socios, membresías y pagos de octubre de 2026
    Y que estoy autenticado como "admin"

  Escenario: Filtro las anulaciones de pagos del mes
    Cuando filtro por tabla "payments", acción "update" y rango del 1 al 31 de octubre de 2026
    Entonces veo solo entradas de la tabla "payments" con acción "update" de ese rango
    Y cada fila muestra fecha en hora de Bogotá, usuario, acción, entidad, registro y "seq"

  Escenario: Busco todo lo ocurrido sobre un socio
    Cuando busco por el id del socio "Laura Gómez"
    Entonces veo las entradas cuyo "record_id" es ese socio

  Escenario: Acción desconocida
    Cuando filtro por acción "borrar"
    Entonces la respuesta es 422 con "field" igual a "action"

  Escenario: El coach no accede a la auditoría global
    Dado que estoy autenticado como "coach"
    Cuando pido la auditoría
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/audit?from&to&user_id&table&record_id&action&q&limit&offset` — rol(es): admin — salida: `Page[AuditRow { seq, at, user_id, user_email, action, table_name, record_id }]` — códigos: 200, 401, 403, 422.

## Pantalla

- `Auditoria` en `/sistema/auditoria`: filtros (el diseño los llama `entity`; el API usa `table`), tabla con carga, vacío y error, paginación por `offset`.

## Notas técnicas

- **Migración:** sí, solo índices en `audit.audit_log` (`at`, `(table_name, record_id)`, `user_id`) si US-015 no los creó.
- **Trigger / restricciones:** el append-only de US-015 sigue vigente.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (cada filtro, orden, paginación); router (rol, 422); front (filtros en URL).
- **Archivos principales:** `api/src/app/modules/audit/{router,schemas,service}.py`, `web/src/features/system/pages/AuditPage.tsx`.

## Supuestos

- Supuesto: `q` en auditoría busca por `record_id` exacto o por correo del usuario que actuó.
- Supuesto: el filtro de pantalla "entidad" se mapea uno a uno a `table_name`.

## Dependencias

- US-016 · Hook de auditoría after_flush (las filas existen).
- US-034 · Dependencias current_user y require_role.
- US-063 · Tabla, paginación, filtros y chips.

## INVEST

- **Independiente:** lectura de una tabla que ya se llena sola.
- **Negociable:** filtros secundarios y columnas.
- **Valiosa:** da la respuesta a "quién hizo qué".
- **Estimable:** consulta paginada y pantalla de lista.
- **Pequeña:** tres a cuatro días.
- **Testeable:** cada filtro probado.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
