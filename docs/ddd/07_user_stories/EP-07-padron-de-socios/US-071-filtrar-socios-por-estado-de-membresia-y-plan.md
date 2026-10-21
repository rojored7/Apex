# US-071 · Como recepción quiero filtrar socios por estado de membresía y por plan para ver de un vistazo quién está al día, quién vence y quién debe plata

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`), Conformist de Memberships (`status_for`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socios_Lista` (`/socios`, chips y filtro de plan)

## Historia

Como administrador o coach
quiero chips "Al día", "Por vencer", "Vencidos", "Congelados", "Pendiente de pago", "Sin membresía" y "Dados de baja", y un filtro por plan
para saber en segundos a quién cobrar o avisar sin abrir ficha por ficha

## Contexto de dominio

- **Aggregate / entidades:** `Member`; lectura derivada `membership_status` (estado de la última membresía no cancelada, o `none`), resuelta por `memberships.service.status_for(member_ids)`.
- **Reglas que aplica:** RN-06 con `expiring_days` (Q11); Q3 (estado `pending_payment` visible con chip "Pendiente de pago", estilo `--warning`); Q1 (si un socio tiene vigente y futura, el estado mostrado es el de la vigente); RN-14 (dados de baja aparte); prohibición de joins entre esquemas (`03_context_map.md` sección 5).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.chip_to_filter(chip) -> {status?, membership_status?}`

## Alcance

- **Backend:** `members.service.list` acepta `membership_status` (`active`, `expiring`, `expired`, `frozen`, `pending_payment`, `none`) y `plan_id`; para filtrar pide a `memberships.service` los `member_ids` que cumplen (`member_ids_by_status(status, plan_id)`) o, para pintar la página, `status_for(ids)`; nunca hace `JOIN` con `memberships`. Cada `MemberRow` trae `membership_status` y `plan_name`.
- **Front:** `Chips` de estado con conteo opcional, selector de plan (planes activos), `StatusTag` en la columna Membresía con texto; "Dados de baja" solo visible para admin.

## Criterios de aceptación

1. `GET /api/v1/members?membership_status=expiring` devuelve solo socios cuya membresía vigente está en `expiring` según `compute_status` con `expiring_days` de Settings, paginado con `limit`/`offset`.
2. `membership_status=pending_payment` devuelve socios con una membresía vendida sin cobertura completa; la etiqueta en pantalla es "Pendiente de pago" con el estilo de advertencia (Q3).
3. `membership_status=none` devuelve socios sin ninguna membresía no cancelada.
4. Un socio con una membresía vigente y una futura aparece con el estado de la vigente.
5. `plan_id` filtra por el plan de la membresía vigente; un `plan_id` inexistente devuelve lista vacía, no error; un `plan_id` que no es UUID responde 422.
6. Un valor de `membership_status` fuera del enum responde 422 con `field = "membership_status"`.
7. El módulo `members` no importa `app.modules.memberships.models` ni hace joins al esquema `memberships` (prueba de arquitectura US-022 en verde).
8. El chip "Dados de baja" solo se muestra a `admin`; para coach, el API con `status=deleted` responde 403 (US-070).
9. Cada `StatusTag` muestra texto además de color; los chips seleccionados usan `aria-pressed`.
10. El chip activo y el plan quedan en la URL; cambiarlos reinicia `offset` a 0.

## Escenarios BDD

```gherkin
# language: es
Característica: Filtrar socios por estado de membresía y plan

  Antecedentes:
    Dado un usuario autenticado con rol "coach"
    Y "Expiring days" configurado en 7
    Y hoy es 20 de octubre de 2026 en Bogotá

  Escenario: Socios por vencer
    Dado "Ana" con membresía activa que termina el 25 de octubre
    Y "Juan" con membresía activa que termina el 30 de noviembre
    Cuando selecciona el chip "Por vencer"
    Entonces la lista muestra a "Ana"
    Y no muestra a "Juan"

  Escenario: Pendiente de pago visible
    Dado "Laura" con una membresía vendida sin pagos
    Cuando selecciona el chip "Pendiente de pago"
    Entonces la lista muestra a "Laura" con la etiqueta "Pendiente de pago"

  Escenario: Vigente y futura
    Dado "Pedro" con una membresía activa y una renovación futura pendiente de pago
    Cuando abre la lista sin filtros
    Entonces "Pedro" aparece con el estado "Al día"

  Escenario: Estado inválido
    Cuando pide la lista con membership_status "moroso"
    Entonces recibe un error 422 con el campo "membership_status"

  Escenario: Coach no ve dados de baja
    Cuando abre la lista de socios
    Entonces no ve el chip "Dados de baja"
```

## Endpoints

- `GET /api/v1/members?membership_status&plan_id&q&status&sort&limit&offset` — rol(es): admin, coach — salida: `Page[MemberRow]` con `membership_status` y `plan_name` — códigos: 200, 401, 403, 422.
- Contrato interno consumido: `memberships.service.status_for(member_ids)` y `memberships.service.member_ids_by_status(status, plan_id)` (US-092).

## Pantalla

- `Socios_Lista`: chips de estado y selector de plan. `// DESIGN-GAP:` el chip "Pendiente de pago" no está en el diseño (Q3).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `chip_to_filter` para los siete chips.
- **Pruebas:** service con base real y `FrozenClock` (cada estado, vigente más futura, plan); prueba de arquitectura sin imports cruzados; router (422, 403); front (chips, URL, etiquetas con texto).
- **Archivos principales:** `api/src/app/modules/members/service.py`, `web/src/features/members/components/MemberStatusChips.tsx`.

## Supuestos

- Supuesto: `memberships.service` expone `member_ids_by_status(status, plan_id)` además de `status_for(ids)` para poder paginar en Members sin joins; el contrato de `05_service_design.md` solo nombra `status_for`. Alternativa: filtrar en memoria, inviable con paginación correcta.
- Supuesto: el filtro por plan usa el plan de la membresía vigente, no de la futura.

## Dependencias

- US-070 · Buscar y listar socios.
- US-092 · Resumen y consultas de estado (`status_for`).
- US-092 debe exponer memberships.service.member_ids_by_status(status, plan_id) (agregado en consolidación)

## INVEST

- **Independiente:** se apoya en un contrato de Memberships ya definido; se prueba con un doble si US-092 no está.
- **Negociable:** chips con o sin conteo.
- **Valiosa:** cumple la frase guía (quién está al día, quién vence).
- **Estimable:** un filtro y una consulta delegada.
- **Pequeña:** 2 a 3 días.
- **Testeable:** cada estado tiene caso con reloj fijo.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
