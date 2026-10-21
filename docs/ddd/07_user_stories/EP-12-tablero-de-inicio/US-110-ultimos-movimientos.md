# US-110 · Como coach o administrador quiero ver en Inicio los últimos movimientos del gimnasio en frases claras para enterarme de lo que pasó sin abrir la auditoría

- **Épica:** EP-12 · Tablero de inicio
- **Bounded context:** Dashboard (módulo `dashboard`), lectura de Audit, Members y Plans por services
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Inicio` (`/`, bloque "Últimos movimientos")

## Historia

Como coach o administrador
quiero ver las 10 acciones más recientes sobre socios, membresías y pagos como frases ("Ana P. registró un pago de $ 120.000 de Juan R.")
para enterarme de lo que pasó hoy en recepción de un vistazo

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry` (lectura), nombres de `Member` y `Plan` (lectura).
- **Reglas que aplica:** Q10 (últimas 10 entradas de auditoría de `members`, `memberships` y `payments` convertidas a frase, armadas por `dashboard.service` desde `audit.service.recent(tables, limit)`), RN-13 (las frases nunca usan campos cifrados; solo nombre y apellido en claro, montos y nombres de plan), RN-01.
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `dashboard.movement_phrase(entry, names) -> str` (traduce una entrada a frase).

## Alcance

- **Backend:** `audit.service.recent(tables, limit)`; `dashboard.service` llena `last_movements` de `GET /dashboard` con `{ seq, at, phrase, table_name, record_id }`, resolviendo nombres por `members.service.names_for(ids)`, `plans.service.names_for(ids)` y `auth.service.names_for(user_ids)`.
- **Front:** bloque "Últimos movimientos" en `Inicio` con la frase, la hora de Bogotá relativa ("hace 5 min") y enlace a la ficha del socio cuando aplica.

## Criterios de aceptación

1. `last_movements` contiene como máximo 10 elementos, las entradas más recientes (por `seq` descendente) de las tablas `members`, `memberships` y `payments`; las de otras tablas y las acciones `reveal`, `login`, `export` y `verify` no aparecen.
2. Frases mínimas: alta de socio ("Ana P. registró a Laura G."), edición de socio ("Ana P. actualizó los datos de Laura G."), baja ("Ana P. dio de baja a Laura G."), venta ("Se vendió Plan Mensual a Laura G."), cancelación de membresía ("Ana P. anuló la membresía Plan Mensual de Laura G."), pago ("Ana P. registró un pago de $ 120.000 de Juan R."), anulación de pago ("Ana P. anuló un pago de $ 120.000 de Juan R."); cualquier otra entrada de esas tablas usa la frase genérica "Ana P. modificó <entidad> de Laura G.".
3. Los nombres se muestran como nombre y la inicial del apellido; ninguna frase contiene documento, teléfono, correo, fecha de nacimiento ni contacto de emergencia (prueba sobre la respuesta).
4. Los montos de la frase salen de `after.amount_cop` (entero, en claro) y se formatean `$ 120.000` en el servidor.
5. Con menos de 10 entradas devuelve las que haya; sin entradas devuelve lista vacía y el front muestra "Todavía no hay movimientos".
6. El tablero sigue respondiendo en menos de 300 ms con 100.000 entradas de auditoría (consulta por índice de `table_name` y `seq`).
7. Rol: el campo llega por `GET /dashboard` con `require_role("admin", "coach")`; `member` recibe 403.
8. Prueba de arquitectura: `dashboard` obtiene las entradas solo por `audit.service.recent`, sin leer `core.audit` models directamente.

## Escenarios BDD

```gherkin
# language: es
Característica: Últimos movimientos en Inicio

  Antecedentes:
    Dado que "Ana Pérez" vendió "Plan Mensual" a "Laura Gómez" y registró un pago de 120000 de "Juan Ruiz"
    Y que estoy autenticado como "coach"

  Escenario: Veo lo último que pasó en recepción
    Cuando entro a Inicio
    Entonces veo "Ana P. registró un pago de $ 120.000 de Juan R."
    Y veo "Se vendió Plan Mensual a Laura G."
    Y veo como máximo 10 movimientos, el más reciente primero

  Escenario: Las consultas en claro no aparecen como movimientos
    Dado que "Ana Pérez" mostró en claro el documento de "Laura Gómez"
    Cuando entro a Inicio
    Entonces ningún movimiento menciona la consulta ni el documento

  Escenario: Sin movimientos
    Dado una instalación sin entradas de socios, membresías ni pagos
    Cuando entro a Inicio
    Entonces veo "Todavía no hay movimientos"

  Escenario: Un socio no ve los movimientos del gimnasio
    Dado que estoy autenticado como "member"
    Cuando pido el tablero
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/dashboard` (campo `last_movements`) — rol(es): admin, coach — códigos: 200, 401, 403.

## Pantalla

- `Inicio` en `/`: bloque "Últimos movimientos" con estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no (usa el índice `(table_name, record_id)` y `seq` de auditoría; si la medición lo pide, índice `(table_name, seq DESC)` en migración propia).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `movement_phrase` con cada tipo del criterio 2 y la frase genérica; nombre con apellido compuesto ("Gómez Restrepo" → "G.").
- **Pruebas:** pura; service con base real (filtrado de tablas y acciones, límite 10); prueba de ausencia de datos cifrados; front (bloque y vacío).
- **Archivos principales:** `api/src/app/modules/audit/service.py` (`recent`), `api/src/app/modules/dashboard/service.py`, `web/src/features/dashboard/components/LastMovements.tsx`.

## Supuestos

- Supuesto: las frases y su catálogo exacto son las del criterio 2; Q10 solo da dos ejemplos.
- Supuesto: se agregan `names_for(ids)` a `members.service`, `plans.service` y `auth.service` para resolver nombres en lote.
- Supuesto: para frases de pagos, el socio se obtiene vía `memberships.service` desde `membership_id`, dentro de `dashboard.service` (lectura compuesta permitida para Dashboard).

## Dependencias

- US-108 · Contrato del tablero (campo `last_movements`).
- US-102 · Consultar auditoría (`audit.service`).
- US-069, US-078 y US-041 deben exponer names_for(ids) (agregado en consolidación)

## INVEST

- **Independiente:** llena un campo ya reservado en el contrato.
- **Negociable:** redacción de las frases.
- **Valiosa:** resume la actividad de recepción sin abrir la auditoría.
- **Estimable:** una consulta, una función pura y un bloque.
- **Pequeña:** dos a tres días.
- **Testeable:** frases y filtrado probados.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
