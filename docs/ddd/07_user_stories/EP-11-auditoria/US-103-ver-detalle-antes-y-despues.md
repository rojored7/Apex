# US-103 · Como administrador quiero ver el antes y el después de un cambio auditado para entender exactamente qué se modificó sin exponer datos cifrados

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Auditoria` (`/sistema/auditoria`, panel de detalle)

## Historia

Como administrador
quiero abrir una entrada de auditoría y ver los valores antes y después del cambio
para saber exactamente qué campo cambió, sin que la auditoría muestre en claro un dato cifrado

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`.
- **Reglas que aplica:** RN-13 (los campos cifrados se guardan como blob `apx1...` y así se muestran), RN-16 (se muestran `prev_hash` y `hash`), RN-15 (solo admin).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `audit.diff(before, after) -> list[FieldChange]` (campos cambiados, agregados y quitados).

## Alcance

- **Backend:** `audit.service.get(seq)` y `GET /audit/{seq}` con `before`, `after`, `prev_hash`, `hash` y el diff calculado.
- **Front:** `SidePanel` de detalle en `Auditoria` con la lista de campos cambiados (antes → después); los blobs cifrados se muestran como "Cifrado" con el `key_id` del blob, sin botón para descifrar.

## Criterios de aceptación

1. `GET /api/v1/audit/{seq}` devuelve 200 con `seq`, `at` (UTC), `user_id`, `action`, `table_name`, `record_id`, `before`, `after`, `prev_hash`, `hash` y `changes` (campo, antes, después).
2. `seq` inexistente devuelve 404; `seq` no numérico devuelve 422.
3. Ningún valor en claro de un campo cifrado (`document`, `phone`, `email`, `birth_date`, `emergency_contact`) aparece en `before`, `after` ni `changes`: aparecen solo como blob `apx1.<key_id>....` (prueba con un socio creado y editado).
4. El front no ofrece descifrar desde la auditoría; muestra "Cifrado" y el `key_id`.
5. `audit.diff` es pura: para `insert` todos los campos son "agregados", para `delete` todos "quitados", para `update` solo los que difieren.
6. Rol: `require_role("admin")`; coach recibe 403; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Detalle de una entrada de auditoría

  Antecedentes:
    Dado que estoy autenticado como "admin"

  Escenario: Veo qué cambió al editar un socio
    Dado que un coach cambió el teléfono y las notas de "Laura Gómez"
    Cuando abro la entrada "update" de ese cambio
    Entonces veo que cambiaron los campos "phone" y "notes"
    Y el teléfono aparece como "Cifrado" en el antes y en el después, nunca en claro

  Escenario: Entrada inexistente
    Cuando abro la entrada con "seq" 999999999
    Entonces la respuesta es 404

  Escenario: Seq inválido
    Cuando abro la entrada con "seq" "abc"
    Entonces la respuesta es 422

  Escenario: El coach no ve el detalle
    Dado que estoy autenticado como "coach"
    Cuando abro cualquier entrada de auditoría
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/audit/{seq}` — rol(es): admin — salida: `AuditDetail` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Auditoria` en `/sistema/auditoria`: panel de detalle con carga y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `audit.diff` con insert, update sin cambios, update con dos campos, delete.
- **Pruebas:** pura; service con base real (blob nunca en claro); router (rol, 404, 422); front (render de "Cifrado").
- **Archivos principales:** `api/src/app/modules/audit/{service,router,schemas}.py`, `web/src/features/system/components/AuditDetailPanel.tsx`.

## Supuestos

- Supuesto: el detalle se pide por `seq` en `GET /audit/{seq}`; la ruta no está en `05_service_design.md` sección 4 y se agrega al contrato.

## Dependencias

- US-102 · Consultar auditoría.

## INVEST

- **Independiente:** solo amplía la lectura de US-102.
- **Negociable:** presentación del diff.
- **Valiosa:** convierte una fila en una respuesta comprensible.
- **Estimable:** un endpoint, una función pura y un panel.
- **Pequeña:** un día y medio.
- **Testeable:** diff y ausencia de claro probados.

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
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
