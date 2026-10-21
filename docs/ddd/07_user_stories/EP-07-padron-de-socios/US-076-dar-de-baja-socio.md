# US-076 · Como administrador quiero dar de baja a un socio con borrado lógico para sacarlo del padrón activo sin perder su historial de pagos ni su auditoría

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, modal "Dar de baja")

## Historia

Como administrador
quiero dar de baja a un socio desde su ficha con un modal de confirmación
para que deje de aparecer en la lista y en la búsqueda, conservando sus membresías, pagos e historial

## Contexto de dominio

- **Aggregate / entidades:** `Member`.
- **Reglas que aplica:** RN-14 (borrado lógico con `deleted_at`; nunca físico); RN-15 (`DELETE /members/{id}` solo admin, `BRECHAS.md` sección 5); invariante de documento único entre no borrados (al dar de baja se libera el documento para un registro nuevo).
- **Eventos que emite:** `MemberDeactivated(member_id)`
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `members.service.deactivate(id, by)`: fija `deleted_at = now()` (UTC) y `status = "inactive"`, emite `MemberDeactivated`; router `DELETE /members/{id}` con `require_role("admin")`.
- **Front:** acción "Dar de baja" en `PageHeader` de la ficha visible solo para admin; `ConfirmModal` que explica que el socio deja de aparecer en la lista y que sus pagos y su historial se conservan; tras confirmar, vuelve a `/socios` con un mensaje.

## Criterios de aceptación

1. `DELETE /api/v1/members/{id}` con rol `admin` responde 204 y fija `deleted_at` en UTC; la fila sigue existiendo en `members.members`.
2. Con rol `coach` responde 403 y no cambia nada; con `member` 403; sin token 401.
3. Un socio ya dado de baja responde 409 con `code = "member_already_deactivated"`; un socio inexistente 404.
4. Después de la baja, el socio no aparece en `GET /members` por defecto ni en la búsqueda por documento, teléfono, correo o nombre; aparece con `status=deleted` para admin.
5. Las membresías y los pagos del socio no se modifican ni se borran (pagos inmutables, RN-02); la auditoría del socio sigue consultable.
6. Queda una entrada de auditoría `update` (o `delete` lógico) en `members` con `deleted_at` antes y después, y se emite `MemberDeactivated` en la misma transacción.
7. Después de la baja se puede registrar un socio nuevo con el mismo documento (US-069).
8. Ninguna ruta del API ejecuta `DELETE FROM members.members` (prueba de arquitectura o revisión de SQL generado).
9. En el front, el coach no ve la acción; el modal muestra el error del API si la baja falla.

## Escenarios BDD

```gherkin
# language: es
Característica: Dar de baja socio

  Antecedentes:
    Dado un socio "Pedro Ruiz" con documento "998877" y dos pagos registrados

  Escenario: Baja lógica por el administrador
    Dado un usuario autenticado con rol "admin"
    Cuando da de baja a "Pedro Ruiz" y confirma
    Entonces "Pedro Ruiz" no aparece en la lista de socios
    Y sus dos pagos siguen existiendo sin cambios
    Y queda una entrada de auditoría de la baja
    Y se emite el evento MemberDeactivated

  Escenario: Baja repetida
    Dado que "Pedro Ruiz" ya fue dado de baja
    Cuando un administrador intenta darlo de baja otra vez
    Entonces recibe un error 409 con el código "member_already_deactivated"

  Escenario: Reutilizar el documento tras la baja
    Dado que "Pedro Ruiz" fue dado de baja
    Cuando un coach registra un socio nuevo con documento "998877"
    Entonces el socio nuevo queda creado

  Escenario: Coach no puede dar de baja
    Dado un usuario autenticado con rol "coach"
    Cuando intenta dar de baja a "Pedro Ruiz" por el API
    Entonces recibe un error 403
    Y "Pedro Ruiz" sigue activo
```

## Endpoints

- `DELETE /api/v1/members/{id}` — rol(es): admin — salida: sin cuerpo — códigos: 204, 401, 403, 404, 409.

## Pantalla

- `Socio_Ficha`: acción "Dar de baja" y `ConfirmModal`.

## Notas técnicas

- **Migración:** no (`deleted_at` existe desde US-069).
- **Trigger / restricciones:** el índice único parcial `WHERE deleted_at IS NULL` libera el documento.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (fila conservada, pagos intactos, evento, auditoría, documento liberado), router (403 coach, 409, 404), front (acción oculta al coach, modal).
- **Archivos principales:** `api/src/app/modules/members/{service,router}.py`, `web/src/features/members/components/DeactivateMemberModal.tsx`.

## Supuestos

- Supuesto: dar de baja no cancela automáticamente las membresías vigentes del socio; si hace falta, el admin las anula aparte (US-090). Las fuentes no definen el efecto.
- Supuesto: no hay acción de reactivar un socio dado de baja en v0.1; se registra de nuevo.

## Dependencias

- US-073 · Ver ficha del socio.
- US-065 · Panel lateral y modal de confirmación.

## INVEST

- **Independiente:** solo necesita la ficha.
- **Negociable:** efecto sobre membresías vigentes y reactivación.
- **Valiosa:** mantiene limpio el padrón sin perder evidencia.
- **Estimable:** un endpoint y un modal.
- **Pequeña:** 2 a 3 días.
- **Testeable:** baja lógica, rol y conservación de pagos verificables.

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
