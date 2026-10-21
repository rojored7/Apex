# US-165 · Como coach quiero mantener el catálogo de movimientos para armar los WODs con ejercicios estandarizados

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (esquema `wods`, módulo `wods`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Movimientos` (`/movimientos`)

## Historia

Como coach
quiero crear, editar, buscar y desactivar movimientos del catálogo
para armar los WODs con ejercicios estandarizados y no escribir el mismo movimiento de diez formas distintas

## Contexto de dominio

- **Aggregate / entidades:** `Movement` (raíz): `name` (único), `category` (`weightlifting` | `gymnastics` | `monostructural` | `other`), `unit` (`kg` | `reps` | `m` | `cal` | `s`), `is_active`.
- **Reglas que aplica:** invariante de `Movement`: nombre único; no se borra, se desactiva (RN-14 por analogía con catálogos); RN-15 (rol por endpoint).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `wods.normalize_movement_name(name)` (recorta espacios y compara sin distinguir mayúsculas)

## Alcance

- **Backend:** modelo `Movement` en el esquema `wods`, auditado; `wods.service` con `list`, `create`, `update`, `set_active`; router `/movements`.
- **Front:** pantalla `Movimientos` con `FilterBar` (búsqueda y categoría, activos/inactivos), `DataTable`, `Pagination` y `SidePanel` de crear y editar.

## Criterios de aceptación

1. `POST /api/v1/movements` con nombre, categoría y unidad válidos crea el movimiento activo y responde 201 con su `id`.
2. Un nombre ya existente (comparado sin mayúsculas ni espacios extremos) devuelve 409 con `field = "name"`.
3. Una categoría o unidad fuera del enum devuelve 422 con `field`.
4. `GET /api/v1/movements` pagina con `limit` (1 a 200, por defecto 25) y `offset`, responde `{ items, total, limit, offset }` y acepta `q`, `category` y `active`.
5. `PATCH /api/v1/movements/{id}` cambia nombre, categoría, unidad o `is_active`; no existe `DELETE` (los movimientos no se borran).
6. Desactivar un movimiento lo oculta del selector del formulario de WOD pero no cambia ningún WOD existente.
7. Admin y coach pueden crear y editar (`require_role("admin", "coach")`); un usuario `member` recibe 403.
8. Toda creación y edición deja una fila en auditoría (`__audited__ = True`) con antes y después.
9. Fechas `created_at` y `updated_at` en UTC con zona.

## Escenarios BDD

```gherkin
# language: es
Característica: Catálogo de movimientos

  Escenario: El coach agrega un movimiento nuevo
    Dado que inicié sesión como coach
    Y el catálogo no tiene "Back squat"
    Cuando creo el movimiento "Back squat" de categoría "weightlifting" con unidad "kg"
    Entonces el movimiento aparece activo en la lista de movimientos
    Y queda una entrada de auditoría de inserción con mi usuario

  Escenario: Nombre repetido
    Dado que el catálogo ya tiene "Pull-up"
    Cuando intento crear el movimiento " pull-up "
    Entonces el sistema rechaza la creación con el mensaje de nombre ya registrado
    Y el catálogo sigue teniendo un solo "Pull-up"
```

## Endpoints

- `GET /api/v1/movements` — rol(es): admin, coach — entrada: `q`, `category`, `active`, `limit`, `offset` — salida: página de movimientos — códigos: 200, 401, 403, 422
- `POST /api/v1/movements` — rol(es): admin, coach — entrada: `{ name, category, unit }` — salida: movimiento — códigos: 201, 401, 403, 409, 422
- `PATCH /api/v1/movements/{id}` — rol(es): admin, coach — entrada: campos parciales — salida: movimiento — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `Movimientos` en `/movimientos`: lista filtrable, panel lateral de crear y editar, interruptor activo. Estados de carga, vacío ("Aún no hay movimientos") y error.

## Notas técnicas

- **Migración:** sí; crea esquema `wods` y tabla `wods.movements` con columnas comunes, índice único sobre `lower(trim(name))`.
- **Trigger / restricciones:** CHECK de enums de `category` y `unit`.
- **Funciones puras a probar:** `normalize_movement_name("  Back Squat ") == "back squat"`.
- **Pruebas:** service con base real (unicidad, desactivar), router (403 member, 409, 422), front (página y panel).
- **Archivos principales:** `api/src/app/modules/wods/{models,schemas,service,router}.py`, `web/src/features/wods/pages/MovementsPage.tsx`.

## Supuestos

- Supuesto: el coach puede crear y editar movimientos (`ROUTES.md` lo incluye en lo que el coach "ve y usa"; no hay regla que lo limite a solo lectura).

## Dependencias

- US-016 · Hook de auditoría (auditar el catálogo)
- US-034 · Dependencias de rol
- US-061 · PanelLayout

## INVEST

- **Independiente:** solo requiere núcleo y layout; no depende de WODs.
- **Negociable:** columnas y filtros de la lista ajustables.
- **Valiosa:** es la base para publicar WODs consistentes.
- **Estimable:** CRUD conocido sobre una tabla.
- **Pequeña:** una tabla, tres endpoints, una pantalla.
- **Testeable:** unicidad, enums y rol verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `wods.movements`
- [ ] Revisión de PR aprobada
