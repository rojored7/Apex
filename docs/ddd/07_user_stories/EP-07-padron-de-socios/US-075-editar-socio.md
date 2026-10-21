# US-075 · Como recepción quiero editar los datos de un socio para corregir un teléfono o un correo sin perder el cifrado ni el rastro del cambio

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Form` (`/socios/:id/editar`)

## Historia

Como administrador o coach
quiero editar los datos de un socio existente
para mantener el padrón al día, con los campos sensibles recifrados, sus índices ciegos recalculados y cada cambio auditado

## Contexto de dominio

- **Aggregate / entidades:** `Member`.
- **Reglas que aplica:** RN-13 (recifrado con la llave activa y nuevo índice ciego); invariante de documento único entre no borrados; nombres no vacíos; RN-14 (no se edita un socio dado de baja); auditoría `update` con campos cifrados como blob.
- **Eventos que emite:** `MemberUpdated(member_id, changed_fields)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.validate_member_input(data)` (de US-069); `members.diff_fields(before, patch) -> set[str]`

## Alcance

- **Backend:** `members.service.update(id, data, by)` con semántica PATCH (solo cambia lo enviado; `null` borra un campo opcional), recifrado e índice de los campos sensibles cambiados, verificación de duplicado de documento, actualización de `updated_at` y `updated_by`; router `PATCH /members/{id}`.
- **Front:** `MemberFormPage` en modo edición: campos no sensibles precargados; campos sensibles vacíos con su valor enmascarado como ayuda y opción "Cambiar" (no se descifran para editar); guarda solo campos modificados.

## Criterios de aceptación

1. `PATCH /api/v1/members/{id}` con rol `admin` o `coach` responde 200 con `MemberDetail` enmascarado; `member` recibe 403; sin token, 401; inexistente, 404.
2. Solo cambian los campos enviados; un campo sensible enviado se recifra con la llave activa de su `data_class` (nuevo `nonce`, mismo `aad = id`) y su índice ciego se recalcula.
3. Cambiar el documento a uno que ya tiene otro socio no borrado responde 409 con `field = "document"` y `existing_id`; sin cambios parciales.
4. `first_name` o `last_name` vacíos responden 422; `sex` inválido responde 422; `birth_date` futura responde 422.
5. Editar un socio dado de baja responde 409 con `code = "member_deactivated"`.
6. La edición deja una entrada de auditoría `update` con `before` y `after` solo de los campos cambiados; los campos cifrados aparecen como blob en ambos lados, nunca en claro.
7. Un `PATCH` sin cambios efectivos responde 200 y no crea entrada de auditoría ni emite evento.
8. Se emite `MemberUpdated` con la lista de campos cambiados (nombres de campo, nunca valores).
9. El formulario de edición no pide `reveal`: no muestra el valor actual en claro de los campos sensibles; solo permite reemplazarlos.
10. Tras guardar, la ficha refleja los cambios y la lista invalida su caché.

## Escenarios BDD

```gherkin
# language: es
Característica: Editar socio

  Antecedentes:
    Dado un usuario autenticado con rol "coach"
    Y un socio "Laura Gómez" con teléfono "3001234567"

  Escenario: Cambiar el teléfono
    Cuando cambia el teléfono de "Laura Gómez" a "3109876543"
    Entonces la búsqueda por "310 987 6543" encuentra a "Laura Gómez"
    Y la búsqueda por "3001234567" ya no la encuentra
    Y queda una entrada de auditoría de actualización con el teléfono como dato cifrado

  Escenario: Documento repetido
    Dado otro socio activo con documento "55667788"
    Cuando cambia el documento de "Laura Gómez" a "55.667.788"
    Entonces recibe un error 409 con el campo "document"
    Y el documento de "Laura Gómez" no cambia

  Escenario: Apellido vacío
    Cuando cambia el apellido de "Laura Gómez" a ""
    Entonces recibe un error 422 con el campo "last_name"

  Escenario: Socio dado de baja
    Dado que "Laura Gómez" fue dada de baja
    Cuando un administrador intenta cambiar su teléfono
    Entonces recibe un error 409 con el código "member_deactivated"

  Escenario: Rol socio denegado
    Dado un usuario autenticado con rol "member"
    Cuando intenta editar a "Laura Gómez"
    Entonces recibe un error 403
```

## Endpoints

- `PATCH /api/v1/members/{id}` — rol(es): admin, coach — entrada: subconjunto de los campos de creación — salida: `MemberDetail` enmascarado — códigos: 200, 401, 403, 404, 409, 422.

## Pantalla

- `Socio_Form` en `/socios/:id/editar`. `// DESIGN-GAP:` el diseño no define cómo se presentan los campos sensibles en edición (se usa "Cambiar" sobre el valor enmascarado).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** índice único parcial de US-069 (también cubre la carrera en edición).
- **Funciones puras a probar:** `diff_fields` (sin cambios, un cambio, `null` en opcional).
- **Pruebas:** service con base real (recifrado: el blob cambia y descifra al nuevo valor; índice recalculado; duplicado; dado de baja; auditoría solo de cambiados; sin auditoría si no hay cambios), router (rol, 404, 409, 422); front (solo envía modificados, no muestra claro).
- **Archivos principales:** `api/src/app/modules/members/{service,router,schemas}.py`, `web/src/features/members/pages/MemberFormPage.tsx`.

## Supuestos

- Supuesto: el coach puede cambiar el documento (las fuentes le permiten editar socios sin excepción de campo).
- Supuesto: los `hint` de enmascarado (supuesto de US-073) se recalculan al cambiar el campo.

## Dependencias

- US-073 · Ver ficha del socio.

## INVEST

- **Independiente:** solo necesita socio y ficha.
- **Negociable:** qué campos puede cambiar el coach.
- **Valiosa:** mantiene el padrón correcto, condición para los avisos.
- **Estimable:** un endpoint PATCH y el formulario en modo edición.
- **Pequeña:** 3 a 5 días.
- **Testeable:** recifrado, índice y auditoría verificables.

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
