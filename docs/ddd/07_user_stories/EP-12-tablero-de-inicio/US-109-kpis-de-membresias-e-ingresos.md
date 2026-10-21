# US-109 · Como coach o administrador quiero ver en Inicio las tarjetas de socios al día, por vencer, vencidos e ingresos del mes para saber en 10 segundos cómo está el gimnasio

- **Épica:** EP-12 · Tablero de inicio
- **Bounded context:** Dashboard (módulo `dashboard`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Inicio` (`/`)

## Historia

Como coach o administrador
quiero ver al entrar las tarjetas de socios al día, por vencer, vencidos e ingresos del mes, y llegar a la lista filtrada con un clic
para saber en 10 segundos quién está al día, quién vence esta semana y cuánta plata ha entrado

## Contexto de dominio

- **Aggregate / entidades:** ninguno (presentación de `DashboardOut`).
- **Reglas que aplica:** RN-01 (formato `$ 120.000`), RN-06 con Q11 (el umbral de "por vencer" es `expiring_days`), Q3 (pendiente de pago visible), frase guía del producto.
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** ninguno nuevo (usa `GET /dashboard` de US-108).
- **Front:** página `Inicio` dentro de `PanelLayout` con cuatro `KpiCard` de v0.1 (Al día, Por vencer, Vencidos, Ingresos del mes) y las tarjetas de versiones futuras (Por avisar, Asistencia de la semana, Sesiones de hoy, WOD de hoy) en estado vacío cuando el campo es `null`; cada KPI enlaza a la lista filtrada.

## Criterios de aceptación

1. Las cuatro tarjetas muestran exactamente `members_active`, `members_expiring`, `members_expired` e `income_month_cop` de `GET /dashboard`; el ingreso con formato `$ 1.250.000` y el mes como "octubre 2026".
2. Las tarjetas cuyo campo viene `null` se muestran en estado vacío ("Disponible en una próxima versión") y no muestran 0.
3. Clic en "Al día" lleva a `/socios?membership_status=active`; "Por vencer" a `/socios?membership_status=expiring`; "Vencidos" a `/socios?membership_status=expired`; "Ingresos del mes" a `/pagos` con el rango del mes de Bogotá.
4. `members_pending_payment` se muestra como una línea secundaria bajo "Al día" ("N pendientes de pago") con enlace a `/socios?membership_status=pending_payment` (Q3).
5. La página muestra estados de carga y error (con reintentar) del `KpiCard`; el color nunca es el único portador de significado (cada tarjeta tiene texto).
6. El coach ve las mismas tarjetas que el admin (ambos tienen rol en `GET /dashboard`); un usuario `member` es redirigido a `/mi` por la guarda de ruta.
7. Desde el login, la pantalla queda usable en menos de 10 segundos en el computador de recepción (medición con Playwright y datos de demo).

## Escenarios BDD

```gherkin
# language: es
Característica: KPIs de membresías e ingresos en Inicio

  Antecedentes:
    Dado que el tablero devuelve 120 al día, 14 por vencer, 9 vencidos y 3250000 de ingresos de octubre de 2026

  Escenario: El administrador ve los números del día
    Dado que estoy autenticado como "admin"
    Cuando entro a Inicio
    Entonces veo "120" en "Al día", "14" en "Por vencer", "9" en "Vencidos" y "$ 3.250.000" en "Ingresos del mes"
    Y las tarjetas "Por avisar", "Asistencia de la semana", "Sesiones de hoy" y "WOD de hoy" aparecen vacías

  Escenario: Llego a la lista de socios por vencer
    Dado que estoy autenticado como "coach"
    Cuando hago clic en la tarjeta "Por vencer"
    Entonces llego a la lista de socios filtrada por "Por vencer"

  Escenario: El tablero no responde
    Dado que estoy autenticado como "admin"
    Y que el tablero responde con un error
    Cuando entro a Inicio
    Entonces veo el mensaje de error con la opción "Reintentar"

  Escenario: Un socio no ve el Inicio del panel
    Dado que estoy autenticado como "member"
    Cuando intento entrar a "/"
    Entonces soy redirigido a "/mi"
```

## Endpoints

- `GET /api/v1/dashboard` (de US-108) — rol(es): admin, coach.

## Pantalla

- `Inicio` en `/`: bloque de KPIs; tarjetas futuras vacías; enlaces a listas filtradas. `// DESIGN-GAP:` la línea de "pendientes de pago" no está dibujada.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna (formato con `core/i18n/format.ts` de US-060).
- **Pruebas:** Vitest y Testing Library de la página (valores, null, enlaces, error); Playwright con datos de demo (tiempo desde login); capturas en 320, 768, 1024 y 1440 en claro y oscuro.
- **Archivos principales:** `web/src/features/dashboard/pages/HomePage.tsx`, `web/src/features/dashboard/components/KpiGrid.tsx`.

## Supuestos

- Supuesto: los enlaces usan `membership_status` como parámetro de la lista de socios (US-071) y `from`/`to` en la de pagos (US-098).
- Supuesto: la tarjeta "Pendientes de pago" va como línea secundaria y no como quinta tarjeta, hasta que el diseño la defina.

## Dependencias

- US-108 · Contrato del tablero.
- US-064 · Encabezado, pestañas y KPI (`KpiCard` con estado null).
- US-071 y US-098 (suave: destinos filtrados de los enlaces de cada KPI; agregado en consolidación)

## INVEST

- **Independiente:** solo front sobre un contrato ya publicado.
- **Negociable:** textos y orden de las tarjetas.
- **Valiosa:** cumple la frase guía del producto.
- **Estimable:** una página con cuatro tarjetas.
- **Pequeña:** dos días.
- **Testeable:** valores, vacíos y enlaces probados.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Capturas en cuatro anchos y dos temas revisadas
- [ ] E2E de tiempo de carga desde el login en verde
- [ ] Revisión de PR aprobada
