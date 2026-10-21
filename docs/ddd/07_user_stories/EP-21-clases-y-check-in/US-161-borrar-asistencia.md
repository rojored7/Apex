# US-161 · Como coach quiero borrar una asistencia registrada por error para corregir la lista de la clase y devolver la clase al socio

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`)
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `CheckIn` (`/clases/:id/checkin`, acción en la lista de asistentes)

## Historia

Como coach
quiero quitar de la lista de una clase a un socio que registré por error
para que la asistencia sea real y su tiquetera recupere la clase

## Contexto de dominio

- **Aggregate / entidades:** `ClassSession` / `Attendance`.
- **Reglas que aplica:** Q8 (borrar una asistencia: admin y coach, auditado; emite `AttendanceRemoved` que devuelve la clase si el plan es por clases); RN-15.
- **Eventos que emite:** `AttendanceRemoved(member_id, session_id, attendance_id)`
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `DELETE /api/v1/attendance/{id}` con motivo opcional; emite el evento en la misma transacción (lo consume US-160).
- **Front:** acción "Quitar" en cada asistente de `CheckIn` con `ConfirmModal`.

## Criterios de aceptación

1. Admin y coach pueden borrar; socio recibe 403; sin token, 401.
2. Borrar una asistencia existente responde 204, emite `AttendanceRemoved` y deja una fila de auditoría `delete` con el `before` completo de la asistencia y el usuario.
3. Un `id` inexistente devuelve 404.
4. Si el socio tenía un plan por clases vigente, la clase se devuelve en la misma transacción (US-160); si el handler falla, la asistencia no se borra.
5. Después de borrar, el mismo socio puede volver a hacer check-in en esa sesión.
6. Borrar una asistencia de una sesión `cancelled` también se permite.

## Escenarios BDD

```gherkin
# language: es
Característica: Borrar una asistencia

  Escenario: El coach quita un check-in equivocado
    Dado que inicié sesión como coach
    Y registré por error a "Pedro Díaz" en la clase de las 18:00
    Cuando lo quito de la lista y confirmo
    Entonces "Pedro Díaz" ya no aparece en la clase
    Y queda una fila de auditoría del borrado con mi usuario

  Escenario: Un socio intenta borrar una asistencia
    Dado que inicié sesión con una cuenta de socio
    Cuando pido DELETE /api/v1/attendance/{id}
    Entonces recibo 403
```

## Endpoints

- `DELETE /api/v1/attendance/{id}` — rol(es): admin, coach — entrada: `reason?` (query o cuerpo) — salida: vacío — códigos: 204, 401, 403, 404

## Pantalla

- `CheckIn`, acción Quitar con `ConfirmModal`. Estado de error si la API falla.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna (la asistencia no está en la lista de tablas con borrado físico prohibido).
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (evento, auditoría, reversión si el handler falla), router (rol, 404), front.
- **Archivos principales:** `api/src/app/modules/classes/{service,router}.py`, `web/src/features/classes/components/AttendeeList.tsx`.

## Supuestos

- Supuesto: el borrado es físico con rastro completo en la auditoría (`before`); `CLAUDE.md` solo prohíbe el borrado físico en pagos, resultados, auditoría y llaves, y no exige borrado lógico en asistencias.
- Supuesto: el motivo es opcional (Q8 no lo exige).

## Dependencias

- US-159 · Check-in en tablet
- US-160 · Descontar y devolver clases (reacción al evento)

## INVEST

- **Independiente:** un endpoint sobre la asistencia.
- **Negociable:** motivo obligatorio o no.
- **Valiosa:** corrige errores con efecto en plata.
- **Estimable:** pequeño.
- **Pequeña:** sí.
- **Testeable:** 204, 403, evento y auditoría verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba del modal; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `attendance`
- [ ] Revisión de PR aprobada
