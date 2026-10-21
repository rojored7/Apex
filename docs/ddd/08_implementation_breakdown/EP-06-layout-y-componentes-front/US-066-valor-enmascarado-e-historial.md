# US-066 · Valor enmascarado e historial — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-066-valor-enmascarado-e-historial.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El supuesto central de la historia (el enmascarado lo calcula el API y el front nunca recibe el valor completo para enmascarar) es exactamente lo que decide DECISIONES N-01. Reveal para admin y coach (Q6), acciones de auditoría (N-08) y alcance del historial de la ficha (N-31) también están decididos. El vencimiento de 60 segundos es un supuesto de interfaz negociable que no toca el contrato.

## Resumen

Construye `MaskedValue`, que recibe el valor enmascarado del API (`CC •••• 4417`) y una función `onReveal`. Al pulsar "Mostrar" la llama una vez y muestra el claro solo en el estado local del componente; lo descarta al ocultar, al desmontar o a los 60 s. Si el campo está vacío muestra "Sin dato", y si `useCan("members.reveal")` es falso no muestra el botón. Construye también `HistoryAside`: lista cronológica con fecha y hora de Bogotá, usuario, acción en español y resumen de los campos cambiados. Nunca muestra blobs: un campo cifrado aparece como "dato cifrado modificado". Tiene carga incremental por `limit` y `offset`, y estados vacío y de error.

## Correcciones aplicadas por DECISIONES.md

- Enmascarado → lo calcula el servidor en memoria al leer la ficha; no existen columnas `*_hint`; las listas no muestran datos cifrados ni enmascarados. `MaskedValue` solo se usa en fichas, y `maskValue(kind, maskedFromApi)` no enmascara nada: devuelve el texto del API o "Sin dato", con el prefijo de tipo si el API no lo trae: corregido por DECISIONES N-01.
- Acciones del historial (la historia nombra `insert`, `update`, `delete` y `reveal`) → `HistoryAside` traduce todas las acciones de `AuditEntry.action`: `insert` ("creó"), `update` ("modificó"), `delete` ("eliminó"), `reveal` ("mostró"), `export` ("exportó"), `download` ("descargó"), `login` ("inició sesión") y `verify` ("verificó"). Una acción desconocida se muestra tal cual, sin romper: corregido por DECISIONES N-08.
- Alcance del historial → la ficha del socio muestra auditoría de `members`, `memberships` y `payments` del socio, así que `HistoryAside` muestra en cada entrada la entidad ("Socio", "Membresía", "Pago") además de la acción: corregido por DECISIONES N-31.
- Permiso para mostrar → el nombre de la acción es `members.reveal`, el de la matriz de US-040; la historia escribe `member.reveal`. Admin y coach lo tienen: coherente con DECISIONES Q6.

## Validación contra el dominio

- RN-13: mostrar en claro se audita. El evento `SensitiveFieldRevealed` y la fila `reveal` los genera el backend (US-074). El front solo dispara `onReveal`, una vez por pulsación (criterio 2), para que cada vista en claro deje exactamente una auditoría.
- `AuditEntry.before` y `after` guardan los campos cifrados como blob (`02_domain_model.md` 2.12). `HistoryAside` reconoce un blob por el prefijo `apx1.` (formato del bus) o por la lista de campos cifrados de la entidad, y nunca lo muestra.
- Funciones puras: `maskValue(kind, maskedFromApi) -> string` y `summarizeChange(entry) -> string[]` (campos cambiados y etiquetas en español).

## Validación contra la arquitectura

- Capas de backend: no aplica. La feature conecta `onReveal` a `POST /api/v1/members/{id}/reveal` (US-074) y el historial a `GET /api/v1/members/{id}/audit?limit&offset` (US-106).
- El valor en claro solo vive en `useState` del componente. No pasa por TanStack Query: la feature llama a la mutación con `gcTime: 0` y sin `onSuccess` que cachee. No toca `localStorage` ni la URL (criterio 3). El bus de criptografía no aplica en el front.
- `web/src/shared/ui/MaskedValue.tsx`, `HistoryAside.tsx` y `web/src/shared/lib/audit-labels.ts`.

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
- [ ] T1 · `web/src/shared/lib/audit-labels.test.ts`: `maskValue` para documento, teléfono y correo (devuelve el texto del API sin tocar los dígitos), vacío o null ("Sin dato"); `summarizeChange` con un `update` de teléfono (blob `apx1.…` en `before` y `after`) que da "Teléfono: dato cifrado modificado"; con cambio de `first_name` da "Nombres"; con acción desconocida no lanza; ningún resultado contiene `apx1.` — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/tests/lint/no-reveal-cache.test.ts`: búsqueda estática de que `MaskedValue.tsx` no importa `@tanstack/react-query` ni usa `localStorage` o `sessionStorage` — 0.5 h

### Front
- [ ] T3 · `web/src/shared/lib/audit-labels.ts`: `ACTION_LABELS` (las ocho acciones de N-08), `ENTITY_LABELS` (`members`, `memberships` y `payments`), `FIELD_LABELS` (campos de las tres tablas), `ENCRYPTED_FIELDS` (`document`, `phone`, `email`, `birth_date` y `emergency_contact`) y las dos funciones puras — 1 h
- [ ] T4 · `web/src/shared/ui/MaskedValue.tsx`: props `label`, `masked: string | null`, `onReveal: () => Promise<string>`, `revealAction = "members.reveal"`; botón "Mostrar" (44 px, `aria-describedby` con el campo) solo si `useCan(revealAction)`; estados enmascarado, cargando (botón deshabilitado), en claro con "Ocultar" y temporizador de 60 s (constante `REVEAL_TTL_MS`), y error (403 muestra "No tienes permiso para ver este dato" y sigue enmascarado; otro error muestra el `message`); limpieza del claro al desmontar; el claro se anuncia con `aria-live="polite"` — 2 h
- [ ] T5 · `web/src/shared/ui/HistoryAside.tsx`: props `entries: AuditEntryOut[]`, `total`, `onLoadMore`, `isLoading`, `error`, `onRetry`; cada entrada muestra `formatDateTime(at)`, el usuario (nombre del API o "Sistema" si es `SYSTEM_USER_ID`), la entidad, la acción y `summarizeChange`; "Ver más" mientras `entries.length < total`; vacío "Sin cambios registrados" y error con "Reintentar"; `<aside aria-label="Historial">`, a la derecha en escritorio y al final en celular — 2 h
- [ ] T6 · `web/src/shared/ui/MaskedValue.test.tsx` (con temporizadores falsos): una pulsación produce una llamada a `onReveal`; el claro se ve y a los 60 s vuelve el enmascarado; al desmontar el claro no queda en el DOM; un espía de `localStorage.setItem` sin llamadas; un 403 muestra el mensaje; sin permiso no hay botón — 1.5 h
- [ ] T7 · `web/src/shared/ui/HistoryAside.test.tsx`: entrada de teléfono cifrado; usuario "Sistema"; "Ver más" llama a `onLoadMore` con el siguiente offset; vacío; error con reintento; entradas de membresía y pago con su entidad (N-31) — 1.5 h
- [ ] T8 · `axe` sobre los dos componentes en sus estados, en `web/src/shared/ui/masked-history.a11y.test.tsx` — 0.5 h

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión: el valor en claro nunca va a logs, caché, URL ni almacenamiento; ninguna prop inicial recibe el claro (criterio 1, verificado con un tipo `masked: string` sin un campo `value`); `HistoryAside` no renderiza `before` ni `after` crudos; la regla de `console` de US-059 aplica también aquí — 1 h

## Orden de ejecución
1. T1 (en rojo)
2. T3
3. T6 (en rojo)
4. T4
5. T7 (en rojo)
6. T5
7. T2
8. T8
9. T9

## Dependencias técnicas
- US-010 · Componentes base: `Button`.
- US-040 · Matriz de permisos: `useCan("members.reveal")`.
- US-059 · Cliente API: `ApiError` para distinguir el 403.
- US-060 · Formato de fechas: `formatDateTime`.
- US-074 y US-106 (EP-07 y EP-11): conectan `onReveal` y el historial; no bloquean el componente.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- Que una feature pase el valor completo del API como `masked` por error — mitigación: N-01 hace que el API nunca devuelva el claro en la ficha; T9 lo revisa; el tipo no tiene un campo `value`.
- Que el formato de `before` y `after` de la auditoría cambie y aparezca un blob sin el prefijo `apx1.` — mitigación: doble detección (prefijo y lista `ENCRYPTED_FIELDS`); T1 cubre los dos casos.
- El historial de una ficha con mucho movimiento crece sin límite — mitigación: carga incremental con `limit` de 25 y "Ver más".

## Estimación
- Backend: 0 h
- Front: 5 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 11 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/MaskedValue src/shared/ui/HistoryAside src/shared/lib/audit-labels tests/lint`
- [ ] En el catálogo (US-068), después de "Mostrar" y 60 s, el DOM no contiene el valor en claro (aserción de Playwright con el reloj controlado)
- [ ] `grep -rn "localStorage\|sessionStorage" web/src/shared/ui/MaskedValue.tsx` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/shared/ui src/shared/lib`
