# US-123 · Como coach quiero registrar por qué canales acepta avisos cada socio para no escribirle por donde no quiere

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Members (esquema `members`), consumido por Notifications
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Avisos, bloque Canales)

## Historia

Como administrador o coach
quiero marcar en la ficha del socio qué canales de aviso tiene activos
para que el sistema respete sus preferencias y no le envíe correos o mensajes que no quiere

## Contexto de dominio

- **Aggregate / entidades:** `Member` con entidad interna `MemberChannelPreference` (`channel`, `active`).
- **Reglas que aplica:** RN-17 indirecto (Notification "respeta las preferencias de canal del socio"); Q14 (sin `push` hasta v1.0); auditoría.
- **Eventos que emite:** `MemberUpdated`
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.effective_channels(preferences) -> set[channel]`

## Alcance

- **Backend:** tabla `members.member_channel_preferences`; endpoints de lectura y actualización; `members.service.channels_for(member_id)` para Notifications.
- **Front:** bloque Canales dentro de la pestaña Avisos de la ficha, con un interruptor por canal.

## Criterios de aceptación

1. `GET /api/v1/members/{id}/channels` devuelve `email`, `telegram` y `whatsapp_link` con `active` (bool); si el socio no tiene filas, todos vienen `active = true`.
2. `PATCH /api/v1/members/{id}/channels` con `{ channel, active }` (uno o varios) actualiza y responde 200; un canal desconocido o `push` responde 422 con `field = channel`.
3. Un socio dado de baja (`deleted_at` no nulo) responde 404.
4. `members.service.channels_for(member_id)` devuelve solo los canales activos; Notifications no lee la tabla directamente.
5. Cada cambio deja auditoría con antes y después (`__audited__ = True`) y emite `MemberUpdated`.
6. Admin y coach pueden leer y cambiar; un socio (rol `member`) recibe 403 en estas rutas (su versión llega en `/me/channels`, US-193).
7. La fila de preferencias no contiene datos cifrados ni contacto.

## Escenarios BDD

```gherkin
# language: es
Característica: Preferencias de canal del socio

  Escenario: Desactivar el correo de un socio
    Dado que inicié sesión como coach
    Y el socio "Laura Gómez" tiene todos los canales activos
    Cuando desactivo el canal "email" en su ficha
    Entonces la respuesta es 200
    Y los canales efectivos de Laura son "telegram" y "whatsapp_link"
    Y queda una fila de auditoría de la preferencia

  Escenario: Rechazar un canal no disponible
    Dado que inicié sesión como administrador
    Cuando activo el canal "push" para un socio
    Entonces la respuesta es 422
```

## Endpoints

- `GET /api/v1/members/{id}/channels` — rol(es): admin, coach — códigos: 200, 401, 403, 404
- `PATCH /api/v1/members/{id}/channels` — rol(es): admin, coach — entrada: lista de `{ channel, active }` — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Socio_Ficha`, pestaña Avisos, bloque Canales: interruptores con etiqueta de texto. `// DESIGN-GAP:` si la pestaña del diseño no trae el bloque de canales.

## Notas técnicas

- **Migración:** sí, `members.member_channel_preferences` (`member_id`, `channel`, `active`, comunes), único (`member_id`, `channel`).
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `effective_channels` sin filas, con un canal desactivado, con todos desactivados.
- **Pruebas:** pura; service con base real; router con rol; Vitest del bloque.
- **Archivos principales:** `api/src/app/modules/members/`, `web/src/features/members/components/ChannelPreferences.tsx`.

## Supuestos

- Supuesto: sin preferencia registrada, todos los canales se consideran aceptados (opt-out). Ningún documento fija el valor por defecto; debe validarse contra la Ley 1581.
- Supuesto: los endpoints `/members/{id}/channels` no están en el contrato; se nombran aquí.

## Dependencias

- US-069 · Registrar socio
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** no requiere el envío.
- **Negociable:** el valor por defecto se puede invertir.
- **Valiosa:** evita molestar al socio.
- **Estimable:** una tabla y dos endpoints.
- **Pequeña:** 3.
- **Testeable:** canales efectivos verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
