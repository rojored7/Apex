# US-058 · Parámetros de membresías — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-05-configuracion-del-gimnasio/US-058-parametros-de-membresias.md`
- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context / módulo:** Settings (`api/src/app/modules/settings/`); consumido por Memberships; front `web/src/features/system/`
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Los cuatro campos y sus valores por defecto vienen de Q9 y Q11. Los rangos, que la historia dejaba como supuesto, los fija DECISIONES N-18 (dos de ellos distintos a los de la historia). La API interna `memberships_policy()` y su uso como parámetro de las funciones puras de memberships están claros. Ningún consumidor necesita leer la política con un rol distinto de admin.

## Resumen

Registra el esquema `MembershipsSettings` (`expiring_days`, `max_freeze_days_per_membership`, `max_freezes_per_membership` y `max_retroactive_days`) y expone `settings.service.memberships_policy()`. Esa función devuelve un objeto inmutable con los cuatro valores, o los valores por defecto si la sección nunca se guardó. Construye la pestaña "Membresías" de `Config`. Memberships pasa los valores como parámetro a `compute_status` (US-083), `apply_freeze` (US-089), a la validación de `start_date` retroactivo (US-084) y al job diario (US-094).

## Correcciones aplicadas por DECISIONES.md

- Rangos de la historia: `max_freeze_days_per_membership` de 1 a 180 y `max_freezes_per_membership` de 0 a 10 → `max_freeze_days_per_membership` va de 0 a 180 y `max_freezes_per_membership` de 0 a 12; `expiring_days` (1 a 30) y `max_retroactive_days` (0 a 30) coinciden: corregido por DECISIONES N-18.
- Por esa corrección, el escenario BDD "escribe 0 en `max_freeze_days_per_membership` → 422" ya no aplica: 0 es válido (significa "no se permite congelar"). El escenario se verifica con 181.
- Valores por defecto 7, 30, 2 y 7: coinciden con DECISIONES Q9 y Q11.
- `max_retroactive_days` también limita el `start_date` de la venta por el API: confirmado por DECISIONES N-24. Se documenta como consumidor.

## Validación contra el dominio

- `SettingsSection(key = memberships)`. Se confirma.
- RN-06 corregida por Q11: "por vencer si faltan `expiring_days` días o menos". `compute_status(membership, today, expiring_days)` con `today = today_bogota()` (Q28). La función sigue siendo pura: recibe el umbral, no lee la configuración (criterio 4).
- Q9 y N-25: `apply_freeze` recibe `max_freeze_days_per_membership`, `max_freezes_per_membership` y `max_retroactive_days` como parámetros, junto con la lista de `MembershipFreeze`.
- Criterio 5: cambiar `expiring_days` no reescribe estados guardados. Lo recalcula la siguiente consulta o el job de US-094. Settings no emite eventos, así que no hay recálculo inmediato. Se confirma.
- No emite ni consume eventos.

## Validación contra la arquitectura

- Memberships llama a `settings.service.memberships_policy(session)`, de service a service (Conformist). Settings no llama a memberships, así que no hay ciclo. Nadie importa `settings.models`.
- El tipo de retorno `MembershipsPolicy` (dataclass congelada) vive en `settings/schemas.py`. Memberships importa ese tipo desde `settings.schemas`, no desde `models`. La prueba de US-022 solo prohíbe los models.
- Rol: `GET` y `PATCH` solo admin. El coach congela (Q7) y vende con `start_date` retroactivo (N-24), pero no necesita leer la política: el API le devuelve 422 con un `message` que incluye el límite ("Máximo 30 días de congelación por membresía"). No hace falta un endpoint de lectura para el coach.
- Sin bus. Auditoría por el hook de US-054.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `settings/schemas.py`: `MembershipsSettings(SectionValue)` con `expiring_days: conint(strict=True, ge=1, le=30) = 7`, `max_freeze_days_per_membership: conint(strict=True, ge=0, le=180) = 30`, `max_freezes_per_membership: conint(strict=True, ge=0, le=12) = 2` y `max_retroactive_days: conint(strict=True, ge=0, le=30) = 7` (en modo `strict` se rechazan `7.5` y `"7"`); registro en `SECTION_REGISTRY`; `@dataclass(frozen=True) MembershipsPolicy` con los cuatro enteros — 0.5 h
- [ ] T2 · `settings/service.py`: `memberships_policy(session) -> MembershipsPolicy`, a partir de `get(session, SectionKey.memberships)`, con los defaults de Q9 y Q11 si no hay fila — 1 h

### Schemas
- No aplica (el esquema de la sección se cuenta en T1).

### Router
- No aplica (lo cubre `/settings/{section}` de US-054).

### Tests unitarios puros
- [ ] T3 · `api/tests/settings/test_memberships_schema.py`: bordes de cada rango (para `expiring_days`: 0, 1, 30 y 31; para `max_freeze_days_per_membership`: −1, 0, 180 y 181; para `max_freezes_per_membership`: −1, 0, 12 y 13; para `max_retroactive_days`: −1, 0, 30 y 31), decimal `7.5` y cadena `"7"` rechazados con `field: "value.<campo>"` — 1 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/settings/test_memberships_policy.py`: sin fila devuelve `MembershipsPolicy(7, 30, 2, 7)`; después de guardar `expiring_days = 5` devuelve 5; el objeto es inmutable (`FrozenInstanceError`) — 0.5 h

### Tests de router
- [ ] T5 · `api/tests/settings/test_memberships_router.py`: `PATCH` con `max_freeze_days_per_membership = 181` da 422 con su `field`; con 0 da 200; el coach da 403 en `GET` y `PATCH` — 0.5 h

### Tests de arquitectura
- No aplica (siguen verdes `test_no_cross_models.py` y `test_settings_no_secrets.py`).

### Front
- [ ] T6 · `web/src/features/system/components/MembershipsSettingsForm.tsx`: cuatro `Field` numéricos enteros (`inputMode="numeric"`), cada uno con su explicación y el valor por defecto entre paréntesis ("Días antes del vencimiento en que la membresía se marca Por vencer (por defecto 7)", "Máximo de días congelados por membresía; 0 no permite congelar (por defecto 30)", "Máximo de congelaciones por membresía (por defecto 2)", "Días hacia atrás que se aceptan al vender o congelar (por defecto 7)"); `membershipsSettingsSchema` (Zod, `z.number().int()` con los rangos de N-18); manejo de 409 de US-055; `// DESIGN-GAP:` porque `Config.html` muestra "Días de gracia" y no los cuatro campos — 2.5 h
- [ ] T7 · Vitest `web/src/features/system/components/MembershipsSettingsForm.test.tsx`: 31 en `expiring_days` muestra el error; 0 en máximo de días se acepta; decimal rechazado; guardar envía enteros — 1 h

### DevOps
- [ ] T8 · Regenerar `docs/openapi.json` y `types.ts` — 0.5 h

### Seguridad
- [ ] T9 · Revisión: solo admin modifica la política; el `message` del 422 en memberships (US-089, US-084) no filtra nada más que el límite — 0.5 h

## Orden de ejecución
1. T3 (en rojo)
2. T1
3. T4 (en rojo)
4. T2
5. T5
6. T8
7. T7 (en rojo)
8. T6
9. T9

## Dependencias técnicas
- US-054 · Secciones de configuración validadas: registro, endpoints y auditoría.
- US-055 · Datos del gimnasio: pestañas y hooks.
- Consumidores (no bloquean): US-083 (`compute_status` con `expiring_days`), US-084 (`start_date` retroactivo, N-24), US-089 (`apply_freeze` con límites) y US-094 (job diario). Deben llamar a `memberships_policy()`.

## Endpoints
- `GET /api/v1/settings/memberships` — roles: admin
- `PATCH /api/v1/settings/memberships` — roles: admin

## Riesgos
- US-089 escribe que memberships lee los límites con `settings.service.get_section("memberships")`, que devuelve el envelope HTTP (`SectionOut`) y no un objeto tipado — mitigación: el contrato canónico para memberships es `memberships_policy()`; se reporta para que el desglose de EP-09 lo use.
- Bajar `expiring_days` cambia de golpe el conteo de "por vencer" del tablero — mitigación: es el comportamiento pedido (criterio 5); la auditoría registra quién y cuándo lo hizo.
- `max_freeze_days_per_membership = 0` con `max_freezes_per_membership > 0` es una combinación contradictoria pero válida — mitigación: `apply_freeze` (US-089) rechaza cualquier congelación de 1 día o más cuando el máximo es 0; se anota para el desglose de EP-09.
- Front condicionado a D1.

## Estimación
- Backend: 1.5 h
- Front: 2.5 h
- Pruebas: 3 h
- DevOps / seguridad: 1 h
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/settings/test_memberships_schema.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_memberships_policy.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_memberships_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/MembershipsSettingsForm`
- [ ] `curl -X PATCH /api/v1/settings/memberships` con `max_freeze_days_per_membership: 181` responde 422 con `"field":"value.max_freeze_days_per_membership"`
- [ ] `uv run python -c` sobre una sesión de prueba sin fila: `memberships_policy()` devuelve `7, 30, 2, 7`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.settings --cov-fail-under=80`
