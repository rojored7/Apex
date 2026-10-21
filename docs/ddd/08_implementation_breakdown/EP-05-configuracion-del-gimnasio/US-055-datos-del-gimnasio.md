# US-055 · Datos del gimnasio — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-05-configuracion-del-gimnasio/US-055-datos-del-gimnasio.md`
- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context / módulo:** Settings (`api/src/app/modules/settings/`); front `web/src/features/system/`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La historia suponía los campos de `gym`. DECISIONES N-18 los define, así que el esquema queda cerrado. Los límites de longitud de la historia se conservan para los campos que no cambian. El mecanismo (versión, 409, 422 con `field`, auditoría) lo da US-054. La pantalla usa el kit de EP-06 y la guarda de rol de US-053.

## Resumen

Registra el esquema `GymSettings` para la clave `gym` y construye la pantalla `Config` en `/sistema/configuracion`, que solo ve el admin. La pantalla tiene una pestaña por sección habilitada en v0.1 (Gimnasio, Medios de pago, Privacidad, Membresías) y el formulario de la pestaña Gimnasio con React Hook Form y Zod. Cada pestaña tiene su botón "Guardar". Hay manejo del 409 por edición simultánea y confirmación al salir de una pestaña con cambios. Esta historia deja la estructura de pestañas y el hook común de sección que reutilizan US-056, US-057 y US-058.

## Correcciones aplicadas por DECISIONES.md

- Campos de `gym` (la historia propone `name`, `legal_id`, `address`, `city`, `phone` y `contact_email`) → los campos son `name`, `nit`, `address`, `city`, `phone`, `whatsapp` y `email`. `legal_id` pasa a llamarse `nit`, `contact_email` pasa a `email` y se agrega `whatsapp`: corregido por DECISIONES N-18. Por eso el criterio 3 se verifica con `field: "value.email"` en lugar de `value.contact_email`.
- Se conservan las restricciones de la historia para los campos que no cambian: `name` de 1 a 80 caracteres; `nit` opcional, con solo dígitos y un guion, hasta 15; `address` hasta 120; `city` hasta 60; `phone` hasta 20; `email` opcional y con formato válido. Para `whatsapp` se usa la misma regla de `phone` (opcional, hasta 20). Es una precisión mínima y no cambia el alcance.

## Validación contra el dominio

- `SettingsSection(key = gym)`: el valor se valida con `validate_section("gym", value)` (US-054). Se confirma.
- Ningún campo de `gym` es dato personal de un socio: no aplica RN-13 ni el bus. El NIT y el teléfono son datos del negocio.
- No emite ni consume eventos. Consumidor futuro: el recibo PDF (EP-16, v0.2), que leerá `settings.service.get(SectionKey.gym)`.
- RN-15: solo admin. Se confirma.

## Validación contra la arquitectura

- Backend: solo `modules/settings/schemas.py` (esquema y registro) y la habilitación ya prevista en `ENABLED_SECTIONS`. No hay migración ni cambios en el router.
- Rol: los endpoints de US-054 ya tienen `require_role("admin")`. En el front, la ruta declara `roles: ["admin"]` (US-067) y la guarda de US-053 muestra "Sin permiso" al coach.
- La auditoría la da el hook sobre `settings_sections` (US-016 y US-054).
- Front: `web/src/features/system/{api.ts,schemas.ts,pages/ConfigPage.tsx,components/GymSettingsForm.tsx}`, con `PageHeader` y `Tabs` (US-064), `Field` y `Button` (US-010) y `ConfirmModal` (US-065). Las llamadas van por `client.ts` (US-059) y los tipos salen de `types.ts`. No hay colores literales.
- Diseño: `Config.html` es una sola página con secciones numeradas, no pestañas. La historia pide pestañas, así que se marca `// DESIGN-GAP:` en `ConfigPage.tsx`. El campo "Zona horaria" del diseño no existe en N-18, así que no se construye (la zona es fija, `America/Bogota`); también se marca `// DESIGN-GAP:`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `schemas.py`: `GymSettings(SectionValue)` con `name: constr(min_length=1, max_length=80, strip_whitespace=True)`, `nit: str | None` (patrón `^\d+(-\d)?$` y hasta 15 caracteres), `address: str | None` (hasta 120), `city: str | None` (hasta 60), `phone: str | None` (hasta 20), `whatsapp: str | None` (hasta 20) y `email: EmailStr | None`; registro en `SECTION_REGISTRY[SectionKey.gym]`; el default de `name` es `"APEX"` para que `GET` sin fila devuelva un valor válido — 1.5 h

### Schemas
- No aplica (el esquema de la sección se cuenta en T1; `SectionOut` y `SectionPatchIn` son de US-054).

### Router
- No aplica (lo cubre `PATCH /settings/{section}` de US-054).

### Tests unitarios puros
- [ ] T2 · `api/tests/settings/test_gym_schema.py`: `validate_section("gym", …)` con un valor válido; `name` vacío y con solo espacios (`value.name`); NIT `901234567-8` válido y `90-12-3` o `ABC` inválidos (`value.nit`); correo mal formado (`value.email`); campo desconocido `legal_id` rechazado con 422 (verifica que no queda el nombre viejo) — 1 h

### Tests de service con PostgreSQL
- No aplica (el guardado, la versión y la auditoría los prueba US-054; aquí no hay lógica de service nueva).

### Tests de router
- [ ] T3 · `api/tests/settings/test_gym_router.py`: `PATCH /api/v1/settings/gym` como admin da 200 con versión nueva; `name` vacío da 422 con `field: "value.name"`; correo inválido da 422 con `field: "value.email"`; coach da 403 — 1 h

### Tests de arquitectura
- [ ] T4 · `api/tests/architecture/test_settings_no_secrets.py` (US-054) sigue verde con `GymSettings` registrado — 0 h (verificación incluida en T3)

### Front
- [ ] T5 · `web/src/features/system/api.ts`: hooks `useSettingsSection(key)` (TanStack Query, `GET /settings/{key}`, clave `["settings", key]`) y `useSaveSettingsSection(key)` (mutación `PATCH` con `{ value, version }`; si sale bien actualiza la caché de esa clave sin invalidar las otras; ante `ApiError` 409 `version_conflict` expone `isConflict`); los reutilizan US-056, US-057 y US-058 — 1.5 h
- [ ] T6 · `web/src/features/system/schemas.ts`: `gymSettingsSchema` (Zod) con las mismas reglas de T1 y mensajes en español ("El nombre es obligatorio", "NIT inválido: solo dígitos y un guion", "Correo inválido"); mapeo de `field` del API (`value.name` a `name`) en un helper `applyApiFieldError(form, error)` — 1 h
- [ ] T7 · `web/src/features/system/pages/ConfigPage.tsx`: `PageHeader` "CONFIGURACIÓN" y `Tabs` con `?tab=` (Gimnasio, Medios de pago, Privacidad, Membresías; Horas, Canales, Clases y TV no se muestran en v0.1); guarda de cambios sin guardar al cambiar de pestaña o salir de la ruta con `ConfirmModal` ("Tienes cambios sin guardar. ¿Descartarlos?"); `// DESIGN-GAP:` por pestañas en lugar de secciones y por "Zona horaria"; ruta `/sistema/configuracion` registrada con `feature: "settings"` y `roles: ["admin"]` en `routes.tsx` y `config/features.ts` — 3 h
- [ ] T8 · `web/src/features/system/components/GymSettingsForm.tsx`: React Hook Form con `zodResolver`, siete `Field` de 44 px, botón "Guardar" con estado de envío, aviso "Cambios guardados", aviso de conflicto "Otra persona cambió esta sección. Recarga para ver los cambios." con botón "Recargar" (refetch) y sin sobrescribir; estados de carga y error de la consulta — 2.5 h
- [ ] T9 · Vitest y Testing Library: `web/src/features/system/components/GymSettingsForm.test.tsx` (nombre vacío muestra el error bajo "Nombre"; 422 del API ubica el error en su campo; 409 muestra el aviso y no llama a un segundo `PATCH`; éxito muestra "Cambios guardados") y `web/src/features/system/pages/ConfigPage.test.tsx` (pestañas visibles, `?tab=` sobrevive a recargar, salir con cambios abre `ConfirmModal`) — 2 h
- [ ] T10 · Playwright `web/tests/e2e/settings-gym.spec.ts`: el admin guarda nombre y NIT, recarga y ve los mismos datos; un coach que abre `/sistema/configuracion` ve "Sin permiso"; `axe` sin violaciones en la pantalla — 1.5 h

### DevOps
- [ ] T11 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` (`npm run gen:api`) con `GymSettings` — 0.5 h

### Seguridad
- [ ] T12 · Revisión: la ruta y la entrada del menú solo para admin (`can("admin","settings.manage")`); el formulario no guarda borradores en `localStorage`; el 403 del API se muestra como "Sin permiso" y no como error genérico — 0.5 h

## Orden de ejecución
1. T2 (pruebas puras, en rojo)
2. T1 (esquema)
3. T3 (router, con el router de US-054)
4. T4
5. T11 (contrato y tipos)
6. T5
7. T6
8. T9 (en rojo)
9. T7
10. T8
11. T10
12. T12

## Dependencias técnicas
- US-054 · Secciones de configuración validadas: tabla, registro, endpoints, versión y auditoría.
- US-059 · Cliente API y tipos generados: `client.ts`, `ApiError` y `types.ts`.
- US-061 · Panel layout, TopBar y SideNav: entrada "Configuración" solo para admin.
- US-064 · Encabezado, pestañas y KPI: `PageHeader` y `Tabs`.
- US-065 · Panel lateral y modal de confirmación: `ConfirmModal` para cambios sin guardar.
- US-053 · Guardas de ruta por rol: "Sin permiso" para el coach.
- US-067 · Mapa de rutas: ruta `/sistema/configuracion` con `feature` y `roles`.

## Endpoints
- `GET /api/v1/settings/gym` — roles: admin
- `PATCH /api/v1/settings/gym` — roles: admin

## Riesgos
- Front condicionado a D1: si el gate no aprueba S1, T5 a T10 salen del repositorio — mitigación: el backend (T1 a T3) queda independiente.
- El diseño muestra la configuración en una sola página con secciones y la historia pide pestañas — mitigación: `// DESIGN-GAP:` y validación con el dueño en la revisión visual; el hook por sección sirve igual en ambos formatos.
- La barra superior necesita el nombre del gimnasio también para el coach, que no puede leer `/settings/gym` — mitigación: se resuelve en US-061 (pregunta abierta allí); esta historia no abre `/settings` a otros roles.

## Estimación
- Backend: 1.5 h
- Front: 8 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 16 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/settings/test_gym_schema.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_gym_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system`
- [ ] `cd web && npx playwright test tests/e2e/settings-gym.spec.ts`
- [ ] `curl -X PATCH /api/v1/settings/gym` con `{"value":{"name":""},"version":0}` responde 422 con `"field":"value.name"`
- [ ] `SELECT after->'value'->>'name' FROM audit.audit_log WHERE table_name='settings_sections' ORDER BY seq DESC LIMIT 1` muestra el nombre guardado desde la pantalla
- [ ] Capturas de `Config` en 320, 768, 1024 y 1440 px, en claro y oscuro, sin desborde horizontal
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.settings --cov-fail-under=80` y `cd web && npx vitest run --coverage src/features/system`
