# US-060 · Formato de dinero y fechas — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-060-formato-de-dinero-y-fechas.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/core/i18n/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Son seis funciones puras con entradas y salidas exactas en los criterios. Las reglas que aplican (RN-01, UTC en el dato, Bogotá en pantalla, fecha civil de Bogotá como "hoy" por Q28) están decididas. El único supuesto de la historia (formato de 12 horas con "a. m." y "p. m.") es de presentación, queda encapsulado en `format.ts` y no cambia el contrato.

## Resumen

Crea `web/src/core/i18n/format.ts` con `formatCop`, `parseCop`, `formatDate`, `formatDateTime`, `formatTime` y `todayBogota`. Todas usan `Intl` con `es-CO` y `timeZone: "America/Bogota"` fija. También agrega una regla de ESLint que prohíbe `toLocaleString`, `toLocaleDateString` e `Intl.*` fuera de `core/i18n`, y corre las pruebas con dos zonas horarias del sistema para garantizar que el resultado no depende del equipo.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md (Q28: `todayBogota()` del front es la misma fecha civil que `today_bogota()` del API).

## Validación contra el dominio

- Value object `Money`: entero en COP, nunca decimales (RN-01). `formatCop` rechaza los no enteros (en desarrollo lanza error; en producción devuelve `—`). `parseCop` devuelve `null` ante decimales o negativos, igual que el `CHECK amount_cop > 0` del API, que el formulario reporta.
- Fechas civiles (`start_date`, `end_date`, `measured_at` como fecha) contra instantes (`paid_at`, `created_at`, `at` de auditoría). `formatDate` no aplica zona a una `AAAA-MM-DD` (se interpreta como fecha civil, no como medianoche UTC). `formatDateTime` y `formatTime` convierten de UTC a Bogotá.
- Q28: `todayBogota()` del front coincide con `today_bogota()` de `core/clock.py`. El front lo usa para valores por defecto (por ejemplo, la fecha de inicio al vender) y nunca para decidir estados (eso lo hace el API).

## Validación contra la arquitectura

- Capas de backend: no aplica.
- `05_service_design.md` 5: `core/i18n/format.ts` es el único lugar de formato. `KpiCard` (US-064), `HistoryAside` (US-066) y todas las features lo importan.
- `TZ_DISPLAY = "America/Bogota"` es una constante de build en `web/src/config/locale.ts`. No sale del navegador ni de `Intl.DateTimeFormat().resolvedOptions()`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T1 · `web/src/core/i18n/format.test.ts`: los ejemplos de los criterios 1 a 6 y los bordes 999, 1.000.000, 50.000.000, `formatCop(1.5)` (lanza en dev), `parseCop` con `$ 120.000`, `120000`, `120.000`, `120.000,50`, `-5`, vacío y texto; medianoche de Bogotá (`2026-10-21T05:00:00Z` es `21 oct 2026, 12:00 a. m.`), fin de mes (`2026-11-01T03:00:00Z` es `31 oct 2026`), cambio de año, y `todayBogota()` con reloj falso a las 03:00 UTC del 21 de octubre, que da `2026-10-20` — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/tests/lint/no-intl-outside-i18n.test.ts`: ESLint programático; `amount.toLocaleString()` en `src/shared/ui/KpiCard.tsx` falla y `Intl.NumberFormat` en `src/core/i18n/format.ts` pasa (criterio 7) — 0.5 h

### Front
- [ ] T3 · `web/src/core/i18n/format.ts`: instancias únicas memorizadas de `Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 })`, normalizadas a `$ 120.000` (un espacio normal después del signo, para que el texto no dependa de la versión de ICU), e `Intl.DateTimeFormat("es-CO", { timeZone: TZ_DISPLAY, … })`; `formatDate` sin `new Date(iso)` para fechas civiles (separa `AAAA-MM-DD` y arma con `Date.UTC` y `timeZone: "UTC"`); abreviatura del mes en minúscula y sin punto (`oct`); `todayBogota()` con `formatToParts` — 2.5 h
- [ ] T4 · `web/src/config/locale.ts` (`LOCALE = "es-CO"`, `TZ_DISPLAY = "America/Bogota"`) y regla `no-restricted-syntax` y `no-restricted-properties` en `web/eslint.config.js` (`toLocaleString`, `toLocaleDateString`, `toLocaleTimeString` e `Intl`) con override para `src/core/i18n/**` — 0.5 h
- [ ] T5 · Mensaje de error de dinero compartido `MONEY_INVALID = "El monto debe ser un número entero en pesos"` en `format.ts`, para que lo usen los esquemas Zod de las features — 0.5 h

### DevOps
- [ ] T6 · `web/package.json`: `"test:tz": "TZ=UTC vitest run src/core/i18n && TZ=Asia/Tokyo vitest run src/core/i18n"` (con `cross-env` para Windows); en `ci.yml`, un paso que corre `npm run test:tz` — 1 h

### Seguridad
- No aplica (funciones puras sin datos sensibles).

## Orden de ejecución
1. T1 (en rojo)
2. T4
3. T3
4. T5
5. T2
6. T6

## Dependencias técnicas
- US-009 · Esqueleto del front: Vitest y ESLint.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- La salida de `Intl` cambia entre versiones de ICU (espacio duro, "p. m." con o sin espacio fino, mes con o sin punto) — mitigación: normalizar la salida en `format.ts` y probar con cadenas exactas en Node y en Playwright (Chromium).
- Colombia no tiene horario de verano, pero un navegador con datos de zona desactualizados podría equivocarse — mitigación: la zona es explícita y no se calcula con desfase manual.
- La regla de ESLint puede chocar con librerías que formatean por dentro — mitigación: la regla aplica solo a `src/`, no a `node_modules`.

## Estimación
- Backend: 0 h
- Front: 3.5 h
- Pruebas: 2.5 h
- DevOps / seguridad: 1 h
- **Total: 7 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/core/i18n tests/lint`
- [ ] `cd web && npm run test:tz` en verde con `TZ=UTC` y `TZ=Asia/Tokyo`
- [ ] `grep -rnE "toLocale(String|DateString|TimeString)|Intl\." web/src | grep -v src/core/i18n` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/core/i18n` (se espera 100 % en `format.ts`)
