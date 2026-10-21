# US-073 · Como recepción quiero abrir la ficha de un socio con sus datos sensibles enmascarados para ver su información sin exponerla a quien esté al lado

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`)

## Historia

Como administrador o coach
quiero abrir la ficha de un socio con encabezado, datos básicos enmascarados y pestañas
para tener en un solo lugar su información, sus membresías, sus pagos y su historial

## Contexto de dominio

- **Aggregate / entidades:** `Member`.
- **Reglas que aplica:** RN-13 (campos cifrados enmascarados por defecto; abrir la ficha no descifra nada); RN-14 (un socio dado de baja se puede ver, marcado como tal); Q16 (la ficha marca la falta de autorización de datos).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.mask(field, blob_meta) -> str` (valor enmascarado sin descifrar el campo completo)

## Alcance

- **Backend:** `members.service.get(id, by) -> MemberDetail` con nombres, sexo, estado, notas, `data_consent_at`, `deleted_at`, campos sensibles enmascarados y `membership_status`; router `GET /members/{id}`.
- **Front:** `MemberDetailPage` con `PageHeader` (nombre, `StatusTag` de estado de membresía, acciones Editar, Vender membresía, Dar de baja según rol), bloque de datos con `MaskedValue` por campo sensible, aviso "Sin autorización de datos registrada" cuando `data_consent_at` es nulo, y `Tabs` con Membresías, Pagos e Historial (contenido en US-093, US-101, US-106) y pestañas futuras deshabilitadas (Asistencia, Resultados, Atleta, Avisos, Adjuntos) con su versión.

## Criterios de aceptación

1. `GET /api/v1/members/{id}` con rol `admin` o `coach` responde 200 con `MemberDetail`; `member` recibe 403; sin token, 401; un `id` inexistente responde 404; un `id` que no es UUID responde 422.
2. `document`, `phone`, `email`, `birth_date` y `emergency_contact` vienen enmascarados (por ejemplo `•••• 0304`, `••• ••• 4567`, `l•••@•••.com`, `••/••/1990` o `"Registrado"`), nunca en claro.
3. Abrir la ficha no genera ninguna fila de auditoría `reveal` ni ninguna operación `decrypt` en `crypto_ops`.
4. Un socio dado de baja se muestra con la etiqueta "Dado de baja" y sin acciones de edición ni venta; solo `admin` puede abrirlo (coach recibe 404 para no revelar su existencia).
5. Si `data_consent_at` es nulo, la ficha muestra el aviso "Sin autorización de datos registrada" sin bloquear ninguna acción.
6. Las acciones del encabezado respetan el rol: "Dar de baja" solo para `admin`.
7. La pestaña activa se refleja en la URL; las pestañas de versiones futuras se ven deshabilitadas con su versión.
8. Estados de carga, 404 ("Socio no encontrado") y error con reintento.

## Escenarios BDD

```gherkin
# language: es
Característica: Ver ficha del socio

  Antecedentes:
    Dado un socio "Laura Gómez" con documento "1020304"

  Escenario: Coach abre la ficha
    Dado un usuario autenticado con rol "coach"
    Cuando abre la ficha de "Laura Gómez"
    Entonces ve el documento como "•••• 0304"
    Y no queda ninguna entrada de auditoría de mostrar dato
    Y no ve la acción "Dar de baja"

  Escenario: Socio sin autorización de datos
    Dado que "Laura Gómez" no tiene autorización registrada
    Cuando un administrador abre su ficha
    Entonces ve el aviso "Sin autorización de datos registrada"

  Escenario: Identificador inexistente
    Dado un usuario autenticado con rol "admin"
    Cuando abre la ficha de un identificador que no existe
    Entonces recibe un error 404
    Y la pantalla muestra "Socio no encontrado"

  Escenario: Coach intenta abrir un socio dado de baja
    Dado un socio dado de baja "Pedro Ruiz"
    Y un usuario autenticado con rol "coach"
    Cuando abre la ficha de "Pedro Ruiz"
    Entonces recibe un error 404

  Escenario: Rol socio denegado
    Dado un usuario autenticado con rol "member"
    Cuando pide la ficha de "Laura Gómez"
    Entonces recibe un error 403
```

## Endpoints

- `GET /api/v1/members/{id}` — rol(es): admin, coach — salida: `MemberDetail` enmascarado — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Socio_Ficha` en `/socios/:id`: encabezado, datos básicos con `MaskedValue`, contenedor de pestañas. `// DESIGN-GAP:` el diseño no muestra el aviso de autorización faltante.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `mask` por tipo de campo.
- **Pruebas:** service y router (rol, 404, 422, enmascarado, sin `reveal` en auditoría, sin `decrypt` en `crypto_ops`); front (acciones por rol, pestañas, aviso).
- **Archivos principales:** `api/src/app/modules/members/{service,router,schemas}.py`, `web/src/features/members/pages/MemberDetailPage.tsx`.

## Supuestos

- Supuesto: el enmascarado se calcula sin descifrar: al cifrar (crear o editar) se guarda una columna `<campo>_hint` en claro con los últimos 4 dígitos del documento y del teléfono y el dominio enmascarado del correo. Esto expone 4 dígitos en claro en la base; si el gate lo rechaza, la ficha muestra solo "Registrado" y el valor real exige `reveal`. Decisión necesaria antes de la migración de US-069.
- Supuesto: el coach recibe 404 al abrir un socio dado de baja (no lo ve en la lista ni en la ficha).

## Dependencias

- US-069 · Registrar socio.
- US-066 · Valor enmascarado e historial.
- US-064 · Encabezado, pestañas y KPI.
- US-040 · matriz de permisos del front (acciones por rol en la ficha; agregado en consolidación)

## INVEST

- **Independiente:** solo necesita el socio creado; las pestañas se llenan después.
- **Negociable:** formato de enmascarado y pestañas visibles.
- **Valiosa:** es el centro de trabajo de recepción.
- **Estimable:** un endpoint de lectura y una página.
- **Pequeña:** 2 a 3 días.
- **Testeable:** enmascarado y ausencia de descifrado verificables.

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
