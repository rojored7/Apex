# US-010 · Componentes base Button, Field y StatusTag — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-010-componentes-base-button-field-statustag.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Los tres componentes están descritos en la historia y en `docs/design/DESIGN.md` (secciones Color, Componentes y Reglas 9 y 10), y DECISIONES Q3 fija el estilo de "Pendiente de pago". Dos detalles visuales que el diseño no cubre (la variante `ghost` y el color de "Cancelado") se resuelven con la convención `DESIGN-GAP:` que el proyecto ya usa, sin cambiar contrato ni comportamiento. El front depende del gate D1, anotado como riesgo.

## Resumen

`Button` (variantes `primary`, `secondary`, `danger`, `ghost`; tamaños `md` de 44 px y `lg` de 56 px; `loading` con `aria-busy` que bloquea el clic; `type="button"` por defecto), `Field` (etiqueta asociada, ayuda, error con `aria-invalid` y `aria-describedby`, marca de obligatorio, compatible con react-hook-form y con un enlace opcional en el error para el `existing_id` del socio duplicado) y `StatusTag` (siete estados de membresía, siempre con texto en español más color de token), con estilos solo de `tokens.css`, pruebas de componente, chequeo `axe` y cobertura de 80 % o más. La función pura `statusLabel` se exporta para que listas, chips y fichas usen las mismas etiquetas.

## Correcciones aplicadas por DECISIONES.md

- Ninguna corrección de contenido; la historia ya es coherente con DECISIONES.md. Confirmaciones: `pending_payment` es un estado visible con borde y texto `--warning` (DECISIONES Q3), y `none` es "Sin plan" (consulta derivada `membership_status` de `02_domain_model.md` 2.1).
- `DESIGN-GAP:` (no es DECISIONES): `DESIGN.md` define `primary`, `secondary`, `danger` y el tamaño `gym`; no define `ghost` ni el estilo de "Cancelado". Por defecto: `ghost` sin borde, texto `--blue-deep`, fondo `--blue-tint` en hover; "Cancelado" con el estilo de "Congelado / Inactivo" (borde `--line`, texto `--muted`). El tamaño `lg` de la historia es el `gym` del diseño (56 px, `--control-gym`, `--text-button-gym`).

## Validación contra el dominio

- `StatusTag` refleja `Membership.status` (`active`, `expiring`, `expired`, `frozen`, `cancelled`, `pending_payment`) más `none` de la consulta derivada del socio. Etiquetas: "Al día", "Por vencer", "Vencido", "Congelado", "Cancelado", "Pendiente de pago", "Sin plan". Coincide con el lenguaje ubicuo de `02_domain_model.md` sección 1.
- Colores por estado según `DESIGN.md` (Estados de membresía): al día relleno `--apex-blue` y texto `--black`; por vencer y pendiente de pago borde y texto `--warning`; vencido y sin plan relleno `--danger` y texto `--white`; congelado y cancelado borde `--line` y texto `--muted`.
- No se emite ni consume ningún evento; no hay reglas RN-xx de backend aquí. RN-06 se refleja solo en la etiqueta, el cálculo del estado es del servidor.

## Validación contra la arquitectura

- Kit compartido en `web/src/shared/ui/` (`05_service_design.md` sección 5); EP-06 construye el resto del kit sobre estos tres.
- Nada de colores ni fuentes literales: CSS Modules por componente con `var(--…)`; el lint de US-009 lo verifica.
- El tipo `MembershipStatusView` se declara a mano aquí; cuando US-059 genere `web/src/core/api/types.ts` desde `docs/openapi.json`, `StatusTag` debe aceptar el enum generado (prueba de tipos en US-059).
- Accesibilidad de `DESIGN.md` regla 10 y `01_product_discovery.md` sección 6: botones reales, `label` por campo, foco visible con borde azul, el color nunca es el único portador de significado.
- Sin backend, sin bus, sin roles, sin paginación ni auditoría: no aplica.

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
- [ ] T1 · `web/src/shared/ui/statusLabel.test.ts`: `statusLabel(status)` devuelve la etiqueta exacta para los siete estados y `statusTone(status)` devuelve `"ok" | "warning" | "danger" | "neutral"` según la tabla de `DESIGN.md`; prueba de exhaustividad de tipos con `satisfies Record<MembershipStatusView, string>` — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/src/shared/ui/styles.test.ts`: lee los tres `*.module.css` y exige `min-height: var(--control)` en el tamaño `md` y `var(--control-gym)` en `lg` de `Button` y del control de `Field` (criterio 2, verificación estática porque jsdom no calcula layout), `:focus-visible` con `outline` o `box-shadow` basado en `var(--blue-deep)` o `var(--apex-blue)` en los tres (criterio 3), y ninguna coincidencia de `#[0-9a-f]{3,8}` ni `rgb(` (criterio 7, refuerzo del lint) — 1 h

### Front
- [ ] T3 · `web/src/shared/ui/statusLabel.ts`: tipo `MembershipStatusView = "active" | "expiring" | "expired" | "frozen" | "cancelled" | "pending_payment" | "none"`, constantes inmutables `STATUS_LABELS` y `STATUS_TONES` (`as const satisfies Record<...>`), funciones puras `statusLabel(status: MembershipStatusView): string` y `statusTone(status: MembershipStatusView): StatusTone` — 0,5 h
- [ ] T4 · `web/src/shared/ui/Button.tsx` y `Button.module.css`: props `variant` (`primary` por defecto), `size` (`md` | `lg`), `loading`, `disabled`, resto de `ButtonHTMLAttributes`; `type="button"` por defecto; con `loading` pone `aria-busy="true"`, `disabled` y no llama `onClick`; tipografía `--text-button` y `--text-button-gym`; estados hover, active, `:focus-visible` y deshabilitado con tokens; `ghost` con comentario `/* DESIGN-GAP: variante ghost no definida en DESIGN.md */` — 2 h
- [ ] T5 · `web/src/shared/ui/Field.tsx` y `Field.module.css`: props `label`, `name`, `hint?`, `error?`, `errorAction?: { href: string; text: string }` (enlace al registro existente, US-069), `required?`, y el control por `children` o como `input` por defecto; `id` estable con `useId()`; `htmlFor`; `aria-invalid` y `aria-describedby` con los ids de ayuda y error; marca de obligatorio visible y `aria-required`; `ref` reenviado al `input` con `forwardRef` (compatible con `register` de react-hook-form); error en `--danger` debajo del control, control de 44 px — 2,5 h
- [ ] T6 · `web/src/shared/ui/StatusTag.tsx` y `StatusTag.module.css`: prop `status: MembershipStatusView`; píldora (`--radius-pill`) con el texto de `statusLabel` siempre visible y la clase de `statusTone`; `pending_payment` con borde y texto `--warning` (Q3); `cancelled` con comentario `/* DESIGN-GAP: estilo de Cancelado no definido; se usa el de Congelado */`; `role` no necesario (es texto) — 1 h
- [ ] T7 · `web/src/shared/ui/index.ts` que exporta `Button`, `Field`, `StatusTag`, `statusLabel`, `statusTone` y `MembershipStatusView` — 0,5 h
- [ ] T8 · `web/src/shared/ui/Button.test.tsx`: variantes y tamaños renderizan su clase; `type` por defecto `button`; con `loading` un clic no llama `onClick` y existe `aria-busy="true"` (criterio 6); deshabilitado no llama `onClick`; `userEvent.tab()` enfoca el botón (criterio 3); `axe` sin violaciones (criterio 8) — 1,5 h
- [ ] T9 · `web/src/shared/ui/Field.test.tsx`: `getByLabelText("Documento")` encuentra el control; con `error` el control tiene `aria-invalid="true"` y `aria-describedby` apunta al nodo del mensaje (criterio 4); `errorAction` renderiza un enlace con su `href`; integración con `useForm().register` (el valor escrito llega al `handleSubmit`); `userEvent.tab()` llega al control; `axe` sin violaciones — 1,5 h
- [ ] T10 · `web/src/shared/ui/StatusTag.test.tsx`: `it.each` sobre los siete estados verifica el texto (criterio 5) y la clase de tono; `pending_payment` tiene la clase `warning`; `axe` sin violaciones — 1 h
- [ ] T11 · Dependencias de prueba: `vitest-axe` (MIT) en `devDependencies` y su `expect.extend` en `web/src/test/setup.ts`; umbral de cobertura 80 % sobre `src/shared/ui/**` en `vite.config.ts` — 0,5 h

### DevOps
- [ ] T12 · `NOTICE` y licencias: `axe-core` (MPL-2.0, sin modificar, solo desarrollo) queda listado en `NOTICE` y en `scripts/ci/licenses-exceptions.txt` con comentario, aunque el chequeo de producción de US-004 no lo vea — 0,5 h

### Seguridad
- [ ] T13 · Revisión: el enlace de `errorAction` solo acepta rutas internas (empieza por `/`) para no abrir una redirección a un sitio externo desde un mensaje de error; ningún `dangerouslySetInnerHTML`; los mensajes de error se renderizan como texto — 0,5 h

## Orden de ejecución
1. T1, T2 (pruebas puras y estáticas en rojo)
2. T3 (función pura y tipo)
3. T11 (dependencias de prueba)
4. T8, T9, T10 (pruebas de componente en rojo)
5. T4, T5, T6, T7 (componentes)
6. T12, T13 (licencias y revisión)

## Dependencias técnicas
- US-009 · Esqueleto del front: `tokens.css`, `fonts.css`, lint de colores, Vitest y jsdom.
- US-004 · Chequeo de licencias: lista de excepciones MPL-2.0 donde entra `axe-core`.
- US-059 · Cliente API y tipos generados: alinea `MembershipStatusView` con el enum del contrato (no bloquea).

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1: si el gate no aprueba el front en este repositorio, la historia sale del alcance.
- jsdom no calcula alturas ni estilos de foco: los criterios 2 y 3 quedan cubiertos de forma estática (T2) y con foco por teclado (T8, T9), no midiendo píxeles — mitigación: US-068 (capturas por ancho con Playwright) mide los 44 y 56 px reales en navegador.
- `forwardRef` en React 19: sigue soportado, pero React 19 ya acepta `ref` como prop y anuncia su retiro futuro — mitigación: se usa `forwardRef` como pide la historia y se encapsula para cambiarlo en un solo lugar.
- `axe-core` es MPL-2.0: entra como herramienta de desarrollo sin modificar, permitida por la regla MPL de `CLAUDE.md` — mitigación: T12 lo deja explícito en `NOTICE` y en la lista de excepciones.
- `DESIGN-GAP` en `ghost` y "Cancelado": si el diseño define otra cosa, cambia solo CSS — mitigación: comentarios `DESIGN-GAP:` buscables y prueba de clases, no de colores.

## Estimación
- Backend: 0 h
- Front: 7 h
- Pruebas: 6 h
- DevOps / seguridad: 1 h
- **Total: 14 h**

## Definición de hecho
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- --run src/shared/ui`
- [ ] `cd web && npm test -- --run --coverage --coverage.include="src/shared/ui/**" --coverage.thresholds.lines=80` en verde
- [ ] `grep -rnE "#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(" web/src/shared/ui` no devuelve nada
- [ ] `grep -rn "DESIGN-GAP" web/src/shared/ui` muestra las dos marcas documentadas (`ghost` y "Cancelado")
- [ ] `cd web && npm run build` termina con código 0
- [ ] `cd web && npm run licenses` en verde (US-004)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npm test -- --run --coverage`
