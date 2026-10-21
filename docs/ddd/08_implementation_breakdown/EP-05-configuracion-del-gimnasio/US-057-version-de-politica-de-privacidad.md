# US-057 · Versión de la política de privacidad — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-05-configuracion-del-gimnasio/US-057-version-de-politica-de-privacidad.md`
- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context / módulo:** Settings (`api/src/app/modules/settings/`); consumido por Members desde v0.3; front `web/src/features/system/`
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**NEEDS_REFINEMENT**

DECISIONES N-18 define la sección `privacy` con `policy_version`, `policy_text`, `retention_years` (por defecto 5) y `consent_required_from` (fecha o null). No incluye `effective_from` ni `policy_url`, que son la base de los criterios 1 a 3 y del "desde cuándo" de la historia. Además, N-18 no dice si `policy_text` es obligatorio ni qué rango acepta `retention_years`. Las dos cosas cambian el esquema y las respuestas 422, así que hace falta una confirmación cerrada.

## Resumen

Registra el esquema `PrivacySettings` según N-18 y agrega `settings.service.current_privacy_version()` para Members. Construye la pestaña "Privacidad" de `Config`, con la advertencia antes de publicar una versión nueva. En v0.1 nadie copia la versión en el socio: `data_consent_version` queda vacío por N-19, y el consumidor real llega con US-149 (v0.3). El desglose está escrito con la alternativa por defecto de la pregunta abierta.

## Correcciones aplicadas por DECISIONES.md

- Campos de `privacy` (la historia propone `policy_version`, `effective_from`, `policy_url` y `policy_text`, con uno de los dos últimos obligatorio) → los campos son `policy_version`, `policy_text`, `retention_years` (por defecto 5) y `consent_required_from` (fecha o null). No existen `effective_from` ni `policy_url`: corregido por DECISIONES N-18. Por eso, los criterios 2 y 3 se reescriben sobre `value.policy_text` y `value.consent_required_from` (alternativa por defecto de la pregunta abierta).
- Criterio 4 (Members copia la versión en `data_consent_version` al registrar una autorización) → en v0.1 `data_consent_version` queda vacío y ningún flujo de v0.1 llama a `current_privacy_version()`. La función se deja lista y probada para US-149 (v0.3): corregido por DECISIONES N-19 (y Q16, autorización opcional).

## Validación contra el dominio

- `SettingsSection(key = privacy)`, con relación Settings ← Members (versión de la política, `03_context_map.md` 2). Se confirma.
- `Member.data_consent_version` y `data_consent_at` (`02_domain_model.md` 2.1). Cambiar la versión no reescribe socios (criterio 5): Settings no conoce a Members, así que es cierto por construcción.
- `consent_required_from` es el dato que hará obligatoria la autorización para socios nuevos desde una fecha (v0.3, Q16). En v0.1 solo se guarda.
- `retention_years` alimenta la política de retención (Ley 1581). En v0.1 nadie la consume.
- No emite ni consume eventos.

## Validación contra la arquitectura

- Solo hay cambios en `settings/schemas.py` y `settings/service.py`. Members, en v0.3, llamará a `settings.service.current_privacy_version()`, de service a service. No hay models cruzados.
- Rol: solo admin en `GET` y `PATCH` (US-054). El coach recibe 403 (criterio 7).
- `policy_text` es texto público de la política, no un secreto (Q12 respetada) ni un dato personal. No pasa por el bus.
- Auditoría: el hook guarda el `before` y el `after` completos, incluido el texto de hasta 20.000 caracteres. Se acepta porque la auditoría de la política es justamente la evidencia que pide la Ley 1581.
- Front: `web/src/features/system/components/PrivacySettingsForm.tsx`, con fechas por `formatDate` (US-060) y confirmación por `ConfirmModal` (US-065).

## Preguntas abiertas

- ¿Se aplica N-18 literal en v0.1, es decir: sin `effective_from` ni `policy_url`; `policy_version` obligatoria (1 a 20 caracteres); `policy_text` obligatorio (1 a 20.000 caracteres; sin él, 422 con `field: "value.policy_text"`); `retention_years` entero de 1 a 20 (por defecto 5); `consent_required_from` fecha `AAAA-MM-DD` o null; y en pantalla, como "Vigente desde", el `updated_at` de la sección? Alternativa por defecto propuesta: sí a todo lo anterior. Si se prefiere conservar la fecha de vigencia explícita de la historia, se agrega `effective_from` obligatoria como quinto campo (exige corregir N-18 en el gate).

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `settings/schemas.py`: `PrivacySettings(SectionValue)` con `policy_version: constr(min_length=1, max_length=20, strip_whitespace=True)`, `policy_text: constr(min_length=1, max_length=20000)`, `retention_years: conint(ge=1, le=20) = 5` y `consent_required_from: date | None = None` (alternativa por defecto); registro en `SECTION_REGISTRY`. `defaults_for("privacy")` devuelve `{ policy_version: null, policy_text: null, retention_years: 5, consent_required_from: null }` sin validar, porque una política nunca publicada no tiene versión — 1 h
- [ ] T2 · `settings/service.py`: `current_privacy_version(session) -> str | None` (None si la sección nunca se guardó) — 0.5 h

### Schemas
- No aplica (el esquema de la sección se cuenta en T1).

### Router
- No aplica (lo cubre `/settings/{section}` de US-054).

### Tests unitarios puros
- [ ] T3 · `api/tests/settings/test_privacy_schema.py`: valor válido; sin `policy_text` (`value.policy_text`); `policy_version` de 21 caracteres; `retention_years` 0, 21 y 2,5 (`value.retention_years`); `consent_required_from` `2026-13-01` (`value.consent_required_from`); campo `policy_url` rechazado por `extra="forbid"` — 1 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/settings/test_privacy_service.py`: `current_privacy_version()` devuelve None sin fila y "2026-10" después de guardar; guardar "2026-10" sobre "2026-01" deja auditoría `update` con las dos versiones en `before` y `after` — 0.5 h

### Tests de router
- [ ] T5 · `api/tests/settings/test_privacy_router.py`: el coach da 403 en `GET` y `PATCH`; sin texto da 422 con `field: "value.policy_text"`; el admin da 200 y versión + 1 — 0.5 h

### Tests de arquitectura
- No aplica (siguen verdes `test_no_cross_models.py` y `test_settings_no_secrets.py` de US-054).

### Front
- [ ] T6 · `web/src/features/system/components/PrivacySettingsForm.tsx`: campos versión, texto de la política (área de texto con contador), años de retención y "Autorización obligatoria desde" (fecha opcional); muestra "Versión vigente: 2026-10 · vigente desde 21 oct 2026" con `formatDate(updated_at)`; al cambiar `policy_version`, antes de guardar abre `ConfirmModal` con "Los socios que ya aceptaron conservan la versión anterior."; usa `useSettingsSection("privacy")` y el manejo de 409 de US-055; `privacySettingsSchema` (Zod) en `features/system/schemas.ts` — 2.5 h
- [ ] T7 · Vitest `web/src/features/system/components/PrivacySettingsForm.test.tsx`: cambiar la versión abre la advertencia y solo guarda al confirmar; guardar sin cambiar la versión no la abre; sin texto muestra el error; la fecha se ve en formato `20 oct 2026` — 1 h

### DevOps
- [ ] T8 · Regenerar `docs/openapi.json` y `types.ts` — 0.5 h

### Seguridad
- [ ] T9 · Revisión: el texto de la política se renderiza como texto plano en el front, nunca con `dangerouslySetInnerHTML` (XSS); solo admin — 0.5 h

## Orden de ejecución
1. Resolver la pregunta abierta
2. T3 (en rojo)
3. T1
4. T2
5. T4
6. T5
7. T8
8. T7 (en rojo)
9. T6
10. T9

## Dependencias técnicas
- US-054 · Secciones de configuración validadas: registro, endpoints, versión y auditoría.
- US-055 · Datos del gimnasio: pestañas y hooks de sección.
- US-060 · Formato de dinero y fechas: `formatDate`.
- US-065 · Panel lateral y modal de confirmación: advertencia antes de publicar.
- US-149 · Registrar autorización de datos (v0.3): primer consumidor de `current_privacy_version()`; no bloquea esta historia.

## Endpoints
- `GET /api/v1/settings/privacy` — roles: admin
- `PATCH /api/v1/settings/privacy` — roles: admin

## Riesgos
- US-149 lee la versión con `settings.service.get_section("privacy")` y esta historia ofrece `current_privacy_version()`: son dos contratos distintos para lo mismo — mitigación: queda como canónico `current_privacy_version()`; se reporta para el desglose de EP-19.
- Si el gate mantiene `effective_from`, cambian el esquema y la pantalla — mitigación: el esquema todavía no tiene datos en producción, así que agregar el campo antes de lanzar v0.1 no exige migración (es JSONB).
- Front condicionado a D1 — mitigación: el backend es independiente.

## Estimación
- Backend: 1.5 h
- Front: 2.5 h
- Pruebas: 3 h
- DevOps / seguridad: 1 h
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/settings/test_privacy_schema.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_privacy_service.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_privacy_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/PrivacySettingsForm`
- [ ] `curl -X PATCH /api/v1/settings/privacy` con `{"value":{"policy_version":"2026-10"},"version":0}` responde 422 con `"field":"value.policy_text"`
- [ ] `curl -H "Authorization: Bearer <coach>" /api/v1/settings/privacy` responde 403
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.settings --cov-fail-under=80`
