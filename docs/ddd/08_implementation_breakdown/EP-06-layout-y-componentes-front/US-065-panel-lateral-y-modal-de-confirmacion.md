# US-065 · Panel lateral y modal de confirmación — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-065-panel-lateral-y-modal-de-confirmacion.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Los dos componentes tienen criterios cerrados: foco atrapado, Escape con cambios sin guardar, motivo obligatorio, texto de confirmación tecleado, un solo envío y error del API dentro del modal. El único supuesto (motivo de al menos 3 caracteres no vacíos en el front) es una validación de interfaz más estricta que la del API. No cambia el contrato y queda como prop configurable.

## Resumen

Construye `SidePanel`, que entra desde la derecha y es de ancho completo en celular. Tiene título, cuerpo y pie con Cancelar y Guardar, y se cierra con ✕, Cancelar, Escape o clic fuera, pidiendo confirmación si hay cambios. También construye `ConfirmModal`: pregunta en el título, consecuencia en una frase, campo "Motivo" opcional u obligatorio con longitud mínima, texto de confirmación tecleado opcional (`ROTAR`, `REENVOLVER`), botones "Volver" y la acción en `danger`, estado de envío sin doble clic, y error del API dentro del modal (en el campo de motivo si `field = "reason"`). Los dos comparten el hook `useFocusTrap`.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md. `confirmText` es genérico, así que también cubre `confirm: "REENVOLVER"` de N-48 (v1.0) sin cambios.

## Validación contra el dominio

- No hay aggregates. Da soporte a las reglas que exigen motivo: RN-02 (anular un pago), `Membership.cancel(reason)`, `skip` de un aviso (RN-17 y EP-14) y la rotación de llave (EP-18).
- El criterio 5 (sin doble clic) protege RN-02 en la interfaz: evita una doble anulación. La garantía real es el trigger de `0011_payments_immutability`, que solo deja anular una vez.
- Supuesto de la historia: el front exige al menos 3 caracteres no vacíos y el API solo "no vacío". Se implementa como `minReasonLength` (por defecto 3), porque la regla de dominio no cambia.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- `web/src/shared/ui/SidePanel.tsx`, `ConfirmModal.tsx` y `web/src/shared/hooks/useFocusTrap.ts`. El modal recibe `onConfirm(reason) => Promise<void>`; la feature hace la mutación con TanStack Query y el modal lee `ApiError` (US-059) para mostrar `message` o `field`.
- `DESIGN.md`: "Crear y editar usan el mismo formulario. Dar de baja, anular y congelar son modales con confirmación; anular pide motivo".

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
- No aplica (la historia no tiene funciones puras; `isReasonValid(text, min)` se prueba dentro de T5).

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica.

### Front
- [ ] T1 · `web/src/shared/hooks/useFocusTrap.ts`: guarda el elemento que abrió el diálogo, mueve el foco al primer control o al título, cicla Tab y Mayús+Tab dentro del contenedor y devuelve el foco al cerrar; bloquea el desplazamiento del `body` mientras está abierto — 1 h
- [ ] T2 · `web/src/shared/ui/SidePanel.tsx`: `role="dialog"`, `aria-modal="true"` y `aria-labelledby` con el título; props `open`, `title`, `isDirty`, `onClose`, `footer`; Escape, ✕, Cancelar y clic fuera llaman a `requestClose`, que con `isDirty` abre un `ConfirmModal` ("¿Descartar los cambios?"); ancho fijo en escritorio con tokens y ancho completo por debajo de 768 px; entrada con `transform` (respeta `prefers-reduced-motion`) — 2.5 h
- [ ] T3 · `web/src/shared/ui/ConfirmModal.tsx`: props `title`, `consequence`, `confirmLabel` (texto explícito, por ejemplo "Anular pago"), `tone: "danger" | "primary"`, `reasonRequired?`, `minReasonLength = 3`, `confirmText?`, `onConfirm(reason?)`; el botón de confirmar se deshabilita mientras el motivo (recortado) no alcanza el mínimo o el texto tecleado no coincide exactamente; durante el envío hay `aria-busy` y el botón ignora clics adicionales (bandera en `useRef` y no solo en el estado); si `onConfirm` rechaza con `ApiError`, el modal sigue abierto y muestra `message`, o el error bajo el motivo si `field === "reason"`; botones "Volver" y la acción — 3 h
- [ ] T4 · `web/src/shared/ui/SidePanel.test.tsx`: el foco queda atrapado y vuelve al botón que abrió; Escape con `isDirty` pregunta y sin `isDirty` cierra; clic fuera con cambios pregunta; en 390 px ocupa todo el ancho — 1.5 h
- [ ] T5 · `web/src/shared/ui/ConfirmModal.test.tsx`: "Pago duplicado" se envía tal cual y el modal cierra si sale bien; solo espacios deshabilita; "ab" deshabilita con mínimo 3; `confirmText="ROTAR"` con "rotar" deshabilita; doble clic con la petición pendiente produce una sola llamada; 422 con `field: "reason"` muestra el error bajo el motivo; 500 muestra el `message` y el modal sigue abierto — 2 h
- [ ] T6 · `axe` sobre los dos componentes abiertos, con y sin error, en `web/src/shared/ui/dialogs.a11y.test.tsx` — 0.5 h

### DevOps
- No aplica.

### Seguridad
- [ ] T7 · Revisión: no hay doble envío (T5); el motivo viaja tal cual y nunca se interpreta como HTML; el error del API se muestra como texto — 0.5 h

## Orden de ejecución
1. T4 y T5 (en rojo)
2. T1
3. T3
4. T2
5. T6
6. T7

## Dependencias técnicas
- US-010 · Componentes base: `Button` (variantes `danger` y `primary`) y `Field` para el motivo.
- US-059 · Cliente API: `ApiError` con `field` y `message`.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- `SidePanel` dentro de `SidePanel`, o un modal sobre un panel, puede romper la trampa de foco — mitigación: `useFocusTrap` mantiene una pila de diálogos y solo el de arriba atrapa; T4 lo prueba con el `ConfirmModal` de descartar cambios.
- La longitud mínima de 3 en el front puede molestar en motivos cortos válidos — mitigación: es una prop; cada feature la ajusta sin tocar el componente.

## Estimación
- Backend: 0 h
- Front: 6.5 h
- Pruebas: 4 h
- DevOps / seguridad: 0.5 h
- **Total: 11 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/SidePanel src/shared/ui/ConfirmModal src/shared/hooks/useFocusTrap`
- [ ] `axe` sin violaciones en los dos diálogos, en claro y oscuro
- [ ] En el catálogo (US-068), recorrer el modal con el teclado no saca el foco del diálogo, y al cerrarlo el foco vuelve al botón de origen
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/shared/ui src/shared/hooks`
