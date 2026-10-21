# US-127 · Como coach quiero ver a quién hay que avisar hoy y abrir el WhatsApp con el mensaje listo para avisar en segundos

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `PorAvisarHoy` (`/avisos/hoy`)

## Historia

Como coach o administrador
quiero una lista de los avisos pendientes y fallidos de hoy con un botón que abre WhatsApp con el mensaje escrito
para avisar a cada socio sin buscar su número ni redactar el texto

## Contexto de dominio

- **Aggregate / entidades:** `Notification`; adaptador `WhatsAppLinkChannel` (genera `https://wa.me/<número>?text=<cuerpo>`, no envía nada).
- **Reglas que aplica:** `whatsapp_link` pasa a `sent` cuando el usuario lo abre, con `sent_by` (`02_domain_model.md` 2.10); RN-13 (el teléfono se descifra vía `contact_for_notification` con propósito `notify` y se audita); RN-15.
- **Eventos que emite:** `NotificationSent`
- **Eventos que consume:** ninguno
- **Funciones puras:** `whatsapp.build_link(country_code, phone, text) -> str`

## Alcance

- **Backend:** `GET /notifications/today`, `GET /notifications/{id}/wa-link`.
- **Front:** pantalla `PorAvisarHoy` con lista agrupada por regla, acciones Abrir WhatsApp, Omitir (US-128) y estado.

## Criterios de aceptación

1. `GET /api/v1/notifications/today` devuelve los avisos con `target_date = today_bogota()` y estado `pending` o `failed`, más los `failed` de días anteriores sin resolver; pagina con `limit`/`offset` (máx. 200) y responde `{ items, total, limit, offset }`.
2. Cada ítem trae `id`, nombre del socio en claro, plan, `end_date`, regla, canal, estado, `last_error` y `attempts`; nunca el teléfono ni el correo.
3. `GET /api/v1/notifications/{id}/wa-link` descifra el teléfono vía `members.service.contact_for_notification(member_id, "notify")`, devuelve `{ url }` con el texto URL-encoded, y en la misma transacción marca el aviso `sent`, `sent_at` (UTC), `sent_by` = usuario y emite `NotificationSent` (auditado).
4. Pedir el enlace de un aviso ya `sent` devuelve el enlace de nuevo sin cambiar `sent_at` ni `sent_by` (idempotente) y deja auditoría del descifrado.
5. Un aviso `skipped` responde 409 en `wa-link`.
6. Un socio sin teléfono registrado responde 422 con `code = "member_without_phone"`.
7. Un aviso de canal `email` o `telegram` en estado `failed` también puede enviarse por WhatsApp desde esta pantalla: `wa-link` lo marca `sent` con `channel` original conservado y `sent_by` lleno.
8. Admin y coach acceden; un socio recibe 403.
9. La pantalla abre el `wa.me` en una pestaña nueva solo después de recibir la respuesta 200.

## Escenarios BDD

```gherkin
# language: es
Característica: Por avisar hoy

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-17
    Y hay un aviso pendiente por WhatsApp para Juan Ríos con teléfono 3001234567

  Escenario: Abrir WhatsApp y marcar enviado
    Dado que inicié sesión como coach
    Cuando abro "Por avisar hoy" y pulso "Abrir WhatsApp" en el aviso de Juan
    Entonces recibo un enlace "https://wa.me/573001234567?text=..."
    Y el aviso queda "sent" con mi usuario como remitente
    Y queda auditado el descifrado del teléfono con propósito "notify"

  Escenario: Socio sin teléfono
    Dado que inicié sesión como administrador
    Y Laura Gómez no tiene teléfono registrado y tiene un aviso pendiente
    Cuando pido el enlace de WhatsApp de su aviso
    Entonces la respuesta es 422 con código "member_without_phone"
```

## Endpoints

- `GET /api/v1/notifications/today` — rol(es): admin, coach — entrada: `limit`, `offset`, `channel`, `status` — códigos: 200, 401, 403, 422
- `GET /api/v1/notifications/{id}/wa-link` — rol(es): admin, coach — salida: `{ url }` — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `PorAvisarHoy` en `/avisos/hoy`: lista por regla con `StatusTag` (Pendiente, Falló, Enviado), botón Abrir WhatsApp de 44 px, botón Omitir, estados de carga, vacío ("Nadie por avisar hoy") y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `build_link` con teléfono con espacios, con indicativo ya incluido, con texto con tildes y saltos de línea.
- **Pruebas:** service con base real (marcar sent, idempotencia, 409, 422); router con rol; E2E Playwright: el coach abre por avisar hoy, envía uno por WhatsApp y omite otro con motivo (junto con US-128).
- **Archivos principales:** `api/src/app/modules/notifications/channels/whatsapp_link.py`, `web/src/features/notifications/pages/TodayPage.tsx`.
- `GET` con efecto (marcar enviado) es el contrato de `ROUTES.md`; se documenta en OpenAPI.

## Supuestos

- Supuesto: un `failed` de otro canal se puede resolver por WhatsApp desde esta pantalla; los documentos dicen que los fallidos aparecen aquí pero no cómo se cierran.
- Supuesto: los fallidos de días anteriores siguen visibles hasta que se envíen u omitan.

## Dependencias

- US-124 · Generar avisos del día
- US-077 · Contacto para avisos auditado

## INVEST

- **Independiente:** no requiere correo ni Telegram.
- **Negociable:** agrupación y orden de la lista.
- **Valiosa:** reemplaza el WhatsApp manual de hoy.
- **Estimable:** dos endpoints y una pantalla.
- **Pequeña:** 5.
- **Testeable:** estado, auditoría y enlace verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] E2E del flujo por avisar hoy en verde
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
