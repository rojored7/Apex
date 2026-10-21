# EP-12 · Tablero de inicio

- **Versión del plan:** v0.1 en su versión mínima; crece en v0.2, v0.4 y v0.5 (`BRECHAS.md` sección 2, "Tablero de inicio"; `03_context_map.md`, contexto 14).
- **Bounded context:** Dashboard (lectura, módulo `dashboard`, sin esquema).
- **Estimación relativa:** S.

## Objetivo de negocio

Cumplir la frase guía del producto: que el dueño sepa en 10 segundos quién está al día, quién vence esta semana, cuánta plata ha entrado en el mes y a quién hay que avisarle, sin abrir cinco pantallas.

## Actores

- Administrador y coach.

## Capacidades incluidas

### Backend
- `dashboard.service.summary(today)`: compone `memberships.service.summary()` y `payments.service.summary(month)` sin tablas propias y sin joins cruzados (Conformist, solo lectura).
- Contrato estable desde v0.1 con los campos de versiones futuras en `null`: por avisar hoy (v0.2), asistencia de la semana y sesiones de hoy (v0.4), WOD de hoy (v0.5).
- Endpoint `GET /dashboard` (admin y coach).
- Cada épica posterior agrega su campo: EP-14 (por avisar), EP-21 (asistencia y sesiones), EP-22 (WOD de hoy). Esta épica fija el contrato; las otras lo llenan.

### Front
- Pantalla de inicio con `KpiCard` para socios al día, por vencer, vencidos e ingresos del mes; las tarjetas de versiones futuras se muestran vacías cuando el campo viene `null`.
- Enlaces desde cada KPI a la lista filtrada correspondiente.

## Fuera de alcance

- Gráficos históricos o reportes analíticos.
- "Últimos movimientos" mientras no se defina qué son (ver preguntas abiertas).

## Criterios de éxito medibles

- Los cuatro KPIs de v0.1 cuadran con `GET /memberships/summary` y `GET /payments/summary` sobre los datos de demo.
- `GET /dashboard` responde en menos de 300 ms con 1.000 socios.
- La pantalla carga y es usable en menos de 10 segundos desde el login en el computador de recepción (frase guía).
- Prueba de arquitectura: el módulo `dashboard` no tiene `models.py` ni importa `models` ajenos.

## Dependencias

- EP-09 Membresías y EP-10 Pagos (fuentes de los KPIs de v0.1).
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- Que el tablero se vuelva lento al crecer, por componer muchas consultas; si pasa, se mide antes de agregar caché.
- Que cada versión modifique el contrato en lugar de solo llenar campos `null`.

## Pantallas del diseño que habilita

- `Inicio` (KPIs de membresías y pagos; el resto vacío hasta su versión).
