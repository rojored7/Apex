# US-070 · Como recepción quiero buscar socios por nombre, documento, teléfono o correo para encontrar a cualquiera en segundos sin descifrar la tabla

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socios_Lista` (`/socios`)

## Historia

Como administrador o coach en recepción
quiero una lista paginada de socios con una sola caja de búsqueda que acepte nombre, documento, teléfono o correo
para encontrar a un socio en menos de un segundo aunque sus datos estén cifrados

## Contexto de dominio

- **Aggregate / entidades:** `Member`.
- **Reglas que aplica:** RN-13 (búsqueda por índice ciego, sin descifrar la tabla); RN-14 (por defecto la lista excluye dados de baja); regla de datos 6 (toda lista pagina y acepta búsqueda); S2 (`limit`/`offset`, máximo 200).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.normalize_for_index(value)`; `members.classify_query(q) -> {"name": str} | {"index": str}` (decide si el término se busca por índices o por nombre)

## Alcance

- **Backend:** `members.service.list(q, status, limit, offset, sort) -> Page[MemberRow]`; `q` se normaliza y se compara por igualdad contra `document_idx`, `phone_idx` y `email_idx`, y además con `ILIKE` sobre `first_name || ' ' || last_name`; filtro `status` (`active`, `inactive`, `deleted`); `sort` por `last_name`, `first_name` o `created_at` (asc o desc); `MemberRow` con `id`, nombres, sexo, estado, teléfono enmascarado y `membership_status` (nulo hasta US-071).
- **Front:** `MembersListPage` con `PageHeader` (botón "Nuevo socio"), `FilterBar` con búsqueda, `DataTable` (nombre, documento enmascarado, teléfono enmascarado, estado, membresía), `Pagination`; clic en fila abre `/socios/:id`.

## Criterios de aceptación

1. `GET /api/v1/members` con rol `admin` o `coach` responde 200 con `{ items, total, limit, offset }`; `limit` por defecto 25, máximo 200; `limit` 0, 201 o negativo, u `offset` negativo responden 422.
2. Un usuario `member` recibe 403; sin token, 401.
3. Buscar `q = "1.020.304"` encuentra al socio guardado con documento `1020304`; buscar por teléfono `"300 123 4567"` encuentra al guardado como `3001234567`; buscar por correo ignora mayúsculas.
4. Buscar `q = "góm"` encuentra a "Laura Gómez" por `ILIKE` en nombre y apellido; la búsqueda por nombre es la única que compara texto en claro.
5. La consulta nunca descifra columnas para filtrar: el plan de ejecución de la búsqueda por documento usa el índice de `document_idx` (prueba con `EXPLAIN`), y ningún registro de `crypto_ops` con verbo `decrypt` se genera al listar.
6. Por defecto la lista excluye socios con `deleted_at` no nulo; `status=deleted` los muestra solo a `admin` (coach recibe 403 con ese filtro).
7. Los datos sensibles en `items` vienen enmascarados; nunca en claro.
8. `sort` acepta solo los campos permitidos; otro valor responde 422 con `field = "sort"`.
9. Con 1.000 socios de prueba, la búsqueda por documento responde en menos de 500 ms (prueba de rendimiento en CI con datos sembrados).
10. En el front, búsqueda, `limit`, `offset` y `sort` viven en la URL; cambiar la búsqueda reinicia `offset` a 0; la tabla muestra estados de carga, vacío ("No hay socios que coincidan con la búsqueda") y error.

## Escenarios BDD

```gherkin
# language: es
Característica: Buscar y listar socios

  Antecedentes:
    Dado un usuario autenticado con rol "coach"
    Y un socio "Laura Gómez" con documento "1020304" y teléfono "3001234567"

  Escenario: Buscar por documento con puntos
    Cuando busca "1.020.304"
    Entonces la lista muestra a "Laura Gómez"
    Y el documento aparece enmascarado
    Y no se descifró ningún campo para filtrar

  Escenario: Buscar por parte del apellido
    Cuando busca "góm"
    Entonces la lista muestra a "Laura Gómez"

  Escenario: Página fuera de rango permitido
    Cuando pide la lista con limit 500
    Entonces recibe un error 422 con el campo "limit"

  Escenario: Socios dados de baja ocultos por defecto
    Dado un socio dado de baja "Pedro Ruiz"
    Cuando abre la lista sin filtros
    Entonces "Pedro Ruiz" no aparece

  Escenario: Coach pide dados de baja
    Cuando pide la lista con estado "deleted"
    Entonces recibe un error 403

  Escenario: Rol socio denegado
    Dado un usuario autenticado con rol "member"
    Cuando pide la lista de socios
    Entonces recibe un error 403
```

## Endpoints

- `GET /api/v1/members?q&status&sort&limit&offset` — rol(es): admin, coach (`status=deleted` solo admin) — salida: `Page[MemberRow]` — códigos: 200, 401, 403, 422.

## Pantalla

- `Socios_Lista` en `/socios`: encabezado, búsqueda, tabla y paginación. Los chips de estado y el filtro por plan los completa US-071. `// DESIGN-GAP:` el diseño usa `page`/`page_size`; se implementa con `limit`/`offset` (S2).

## Notas técnicas

- **Migración:** no (usa la tabla de US-069); índice funcional opcional `lower(first_name || ' ' || last_name)` con `pg_trgm` si la prueba de 500 ms lo exige.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `classify_query` con documento con puntos, teléfono con espacios, correo, texto con tildes, cadena vacía.
- **Pruebas:** service con base real y 1.000 socios sembrados (búsqueda por cada índice, por nombre, exclusión de borrados, orden); router (rol, `limit` inválido, `sort` inválido); arquitectura (sin `decrypt` al listar); front (URL, reinicio de offset, estados).
- **Archivos principales:** `api/src/app/modules/members/{service,router,schemas}.py`, `web/src/features/members/pages/MembersListPage.tsx`.

## Supuestos

- Supuesto: el filtro `status` de la API acepta `deleted` para ver dados de baja y es solo admin, porque la baja es acción de admin; las fuentes no dicen quién ve los dados de baja.
- Supuesto: con `q` se aplican a la vez las tres igualdades de índice ciego y el `ILIKE` de nombre (unión), para no exigir al usuario elegir el tipo de búsqueda.

## Dependencias

- US-069 · Registrar socio (tabla e índices).
- US-063 · Tabla, paginación, filtros y chips.

## INVEST

- **Independiente:** no necesita membresías (el estado de membresía llega en US-071).
- **Negociable:** campos de orden y columnas visibles.
- **Valiosa:** es la operación más frecuente de recepción.
- **Estimable:** una consulta y una página.
- **Pequeña:** 3 a 5 días.
- **Testeable:** búsqueda, rendimiento y ausencia de descifrado verificables.

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
