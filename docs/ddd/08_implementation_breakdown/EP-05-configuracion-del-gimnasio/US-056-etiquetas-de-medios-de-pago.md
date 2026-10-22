# US-056 · Etiquetas de medios de pago — desglose técnico

> **Corregido en S3-W0-1** (`docs/ddd/blueprints/sprint-03-plan.md`, sección 1; registro en `docs/ddd/DECISIONES.md`, "Sprint 3"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - `GET /payments/methods` responde el objeto `PaymentMethodsOut { items }`, no un arreglo (S3-C7, D25).
> - `settings.service.payment_methods(session)` nace en S3-B3 con el estilo de `memberships_policy` (S3-C17); `label` y `hint` son `SafeText`, las etiquetas son únicas sin distinguir mayúsculas (422 `field="value.<code>.label"`) y la lectura tolera claves ajenas (S3-D55).
> - El hook `usePaymentMethods()` vive en `web/src/shared/data/paymentMethods.ts` (S3-D65), no en `features/payments/api.ts`.

- **Historia:** `docs/ddd/07_user_stories/EP-05-configuracion-del-gimnasio/US-056-etiquetas-de-medios-de-pago.md`
- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context / módulo:** Settings (`api/src/app/modules/settings/`); consumido por Payments (`api/src/app/modules/payments/`); front `web/src/features/system/`
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**NEEDS_REFINEMENT**

El esquema y la pestaña están resueltos: el enum es fijo por S8 y cada medio tiene `label` y `hint`. El criterio 7 dice que el coach recibe las etiquetas "por el endpoint de pagos", pero ningún documento ni historia define ese endpoint. US-095 y US-085 solo tienen `POST`, y `GET /settings/payment_methods` es solo para admin. Los paneles de registrar pago y de vender con primer pago, que usa el coach, necesitan las etiquetas. Falta fijar la ruta, que es un cambio de contrato.

## Resumen

Registra el esquema `PaymentMethodsSettings`, con exactamente las claves `cash`, `nequi` y `breb`, cada una con `label` y `hint`. Agrega la función pura `decorate_methods` y `settings.service.payment_methods()`, que devuelve el enum fijo decorado en orden. Construye la pestaña "Medios de pago" de `Config`, con tres filas fijas y sin botones de agregar ni quitar. Bajo la alternativa por defecto de la pregunta abierta, expone las etiquetas al coach con un endpoint de lectura en el módulo de pagos, que delega en settings.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md (S8 enum fijo, Q12 sin secretos).

## Validación contra el dominio

- `SettingsSection(key = payment_methods)`. El enum `Payment.method` (`cash`, `nequi`, `breb`) es del aggregate Payment y lo protege el `CHECK` de `0010_payments`. Settings solo decora el enum: no lo amplía (S8). Se confirma.
- Invariante del criterio 5: los pagos guardan el `code`, no la etiqueta, así que cambiar una etiqueta no toca ningún pago (RN-02 intacta). Se confirma.
- Función pura nueva `settings.decorate_methods(codes: tuple[str, ...], labels: PaymentMethodsSettings) -> list[MethodOut]`. El orden sale del enum, no del JSON.
- Eventos: ninguno.
- La fuente del enum es una constante `PAYMENT_METHOD_CODES = ("cash", "nequi", "breb")`. Para no acoplar settings a payments (settings no depende de nadie), la constante vive en `settings/schemas.py`. Una prueba de arquitectura compara que coincide con el `Literal` de `payments/schemas.py`, para que no diverjan.

## Validación contra la arquitectura

- Settings no importa payments. Payments llama a `settings.service.payment_methods()` (service a service, Conformist según `03_context_map.md`: "Settings ← Payments (medios)"). No hay ciclo: settings no llama a payments.
- No hay models cruzados: payments no lee `settings.models`.
- Rol: el `PATCH` y el `GET` de `/settings/payment_methods` siguen siendo solo admin (US-054). La lectura para el coach no abre `/settings`; va por un endpoint de propósito específico en payments, bajo la alternativa por defecto.
- Sin bus ni primitivas criptográficas. La sección queda auditada por US-054.
- Front: `web/src/features/system/components/PaymentMethodsForm.tsx`. El hook de lectura para los consumidores va en `web/src/features/payments/api.ts`.
- Diseño: `Config.html` muestra casillas por medio de pago (habilitar o deshabilitar). Esa función no está en la historia ni en S8, así que no se construye y se marca `// DESIGN-GAP:`.

## Preguntas abiertas

- ¿El coach (y los paneles de registrar pago y vender con primer pago) obtiene las etiquetas con un endpoint nuevo `GET /api/v1/payments/methods` (roles admin y coach; salida `[{ code, label, hint }]` en el orden `cash`, `nequi`, `breb`) que el router de payments implementa delegando en `settings.service.payment_methods()`, construido dentro de esta historia? Alternativa por defecto propuesta: sí, con esa ruta y esos roles, en esta historia. El desglose ya incluye las tareas (T3, T7 y T10) bajo esa alternativa.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `settings/schemas.py`: `PAYMENT_METHOD_CODES`, `MethodLabel(SectionValue)` con `label: constr(min_length=1, max_length=30, strip_whitespace=True)` y `hint: str | None` (hasta 120), y `PaymentMethodsSettings(SectionValue)` con los campos obligatorios `cash`, `nequi` y `breb` (defaults "Efectivo", "Nequi" y "Bre-B"), `extra="forbid"` y registro en `SECTION_REGISTRY` — 1 h
- [ ] T2 · `settings/service.py`: función pura `decorate_methods(codes, labels) -> list[MethodOut]` y caso de uso `payment_methods(session) -> list[MethodOut]` (usa `get(session, SectionKey.payment_methods)`, con defaults si no hay fila) — 1 h
- [ ] T3 · `payments/service.py`: `methods(session) -> list[MethodOut]`, que delega en `settings.service.payment_methods`; `payments/schemas.py`: `PaymentMethodOut { code: Literal["cash","nequi","breb"], label, hint }` (alternativa por defecto de la pregunta abierta) — 0.5 h

### Schemas
- No aplica (los esquemas se cuentan en T1 y T3).

### Router
- [ ] T4 · `payments/router.py`: `GET /api/v1/payments/methods` con `require_role("admin", "coach")`, 200, 401 y 403 (alternativa por defecto). Se declara antes de `GET /payments/{id}` para que la ruta no choque con el parámetro — 0.5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/settings/test_payment_methods_rules.py`: `decorate_methods` con etiquetas por defecto y personalizadas, con orden fijo aunque el JSON venga en otro orden; `validate_section` con la clave extra `tarjeta` (`field: "value.tarjeta"`), sin `nequi` (`value.nequi`), con `label` vacía (`value.cash.label`) y con `hint` de 121 caracteres — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/settings/test_payment_methods_service.py`: `payment_methods()` sin fila devuelve los defaults; después de guardar `hint` de Nequi lo devuelve; guardar etiquetas no cambia ninguna fila de `payments.payments` (conteo y `method` iguales antes y después) — 1 h

### Tests de router
- [ ] T7 · `api/tests/settings/test_payment_methods_router.py` y `api/tests/payments/test_payment_methods_router.py`: `PATCH /settings/payment_methods` con `tarjeta` da 422 con `value.tarjeta`; el coach da 403 en `PATCH` y en `GET /settings/payment_methods`; `GET /payments/methods` da 200 al coach y al admin con 3 elementos en orden, 403 al socio y 401 sin token — 1.5 h

### Tests de arquitectura
- [ ] T8 · `api/tests/architecture/test_payment_method_codes.py`: `settings.schemas.PAYMENT_METHOD_CODES` coincide con los valores del `Literal` de `payments.schemas` y del `CHECK` de `0010_payments` (S8). `test_no_cross_models.py` sigue verde — 0.5 h

### Front
- [ ] T9 · `web/src/features/system/components/PaymentMethodsForm.tsx`: tres filas fijas (Efectivo, Nequi, Bre-B) con `Field` de etiqueta y de ayuda; sin botones de agregar ni eliminar; nota "Para agregar un medio nuevo se requiere una actualización del sistema"; usa `useSettingsSection("payment_methods")` y `useSaveSettingsSection` de US-055, con el mismo manejo de 409; `// DESIGN-GAP:` por las casillas del diseño. Esquema Zod `paymentMethodsSchema` en `features/system/schemas.ts` — 2 h
- [ ] T10 · `web/src/features/payments/api.ts`: hook `usePaymentMethods()` (`GET /payments/methods`, `staleTime` de 5 minutos) que consumen el `SidePanel` de US-095 y la sección "Primer pago" de US-085 — 0.5 h
- [ ] T11 · Vitest `web/src/features/system/components/PaymentMethodsForm.test.tsx` (no hay botón de agregar; etiqueta vacía muestra el error bajo "Efectivo"; guardar muestra "Cambios guardados") y `web/src/features/payments/api.test.ts` (el hook devuelve los tres medios en orden con MSW) — 1.5 h

### DevOps
- [ ] T12 · Regenerar `docs/openapi.json` y `types.ts` con `PaymentMethodsSettings` y `GET /payments/methods` — 0.5 h

### Seguridad
- [ ] T13 · Revisión: `GET /payments/methods` no expone ningún otro dato de settings; el socio recibe 403; el `PATCH` sigue solo para admin — 0.5 h

## Orden de ejecución
1. T5 (en rojo)
2. T1
3. T2
4. T6
5. T3
6. T7 (en rojo)
7. T4
8. T8
9. T12
10. T10
11. T11 (en rojo)
12. T9
13. T13

## Dependencias técnicas
- US-054 · Secciones de configuración validadas: registro, `get` y endpoints de settings.
- US-055 · Datos del gimnasio: pestañas de `Config` y hooks `useSettingsSection` y `useSaveSettingsSection`.
- US-095 · Registrar pago: es dueña del router y el service de payments; T3 y T4 se agregan sobre ese módulo. Si US-056 se hace antes, crea `payments/router.py` solo con esta ruta.
- US-034 · require_role.

## Endpoints
- `GET /api/v1/settings/payment_methods` — roles: admin
- `PATCH /api/v1/settings/payment_methods` — roles: admin
- `GET /api/v1/payments/methods` — roles: admin, coach

## Riesgos
- Si se rechaza la alternativa por defecto, US-085 y US-095 no tienen de dónde leer las etiquetas para el coach — mitigación: decidir en el refinamiento; mientras tanto, el front cae a las etiquetas por defecto codificadas en `features/payments/constants.ts`.
- Una divergencia entre `PAYMENT_METHOD_CODES` y el enum de payments mostraría un medio que el API rechaza — mitigación: T8.
- Front condicionado a D1 — mitigación: el backend es independiente.

## Estimación
- Backend: 3 h
- Front: 2.5 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 12 h**

La estimación supera la referencia de 2 puntos (6 a 10 h) por el endpoint de lectura en payments y sus pruebas, que la historia exige en el criterio 7 sin nombrarlo.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/settings/test_payment_methods_rules.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_payment_methods_service.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_payment_methods_router.py tests/payments/test_payment_methods_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system src/features/payments`
- [ ] `curl -H "Authorization: Bearer <coach>" /api/v1/payments/methods` devuelve `{"items":[{"code":"cash",…},{"code":"nequi",…},{"code":"breb",…}]}` (S3-C7)
- [ ] `curl -X PATCH /api/v1/settings/payment_methods` con la clave `tarjeta` responde 422 con `"field":"value.tarjeta"`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.settings --cov=app.modules.payments --cov-fail-under=80` y `cd web && npx vitest run --coverage src/features/system`
