# US-122 · Como administrador quiero configurar los canales de aviso sin guardar secretos en la base para habilitar correo y WhatsApp de forma segura

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Settings (esquema `settings`), consumido por Notifications
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña Canales)

## Historia

Como administrador
quiero activar o desactivar cada canal de aviso y fijar el remitente, el correo de respuesta y el chat por defecto
para que el sistema envíe por los canales que el gimnasio usa sin exponer contraseñas ni tokens

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection` con `key = channels`.
- **Reglas que aplica:** Q12: secretos (SMTP, token de Telegram, llaves VAPID) solo en `.env`; `settings.channels` guarda lo no secreto. Sección auditada.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("channels", value)`

## Alcance

- **Backend:** esquema Pydantic de la sección `channels`; `notifications.service.channel_status()` que combina lo habilitado en Settings con la presencia de secretos en `Settings` de `core/config.py`.
- **Front:** pestaña Canales de `Config` con un interruptor por canal y el estado "credenciales configuradas / faltan en .env".

## Criterios de aceptación

1. La sección `channels` admite exactamente: `email.enabled` (bool), `email.from_name`, `email.reply_to` (correo válido), `whatsapp_link.enabled` (bool), `whatsapp_link.country_code` (por defecto `57`). Telegram no es canal de esta sección: es canal interno del equipo para alertas (N-34).
2. Cualquier campo con nombre que sugiera secreto (`password`, `token`, `api_key`, `secret`, `private_key`) responde 422; el esquema es cerrado (`extra = forbid`).
3. `PATCH /api/v1/settings/channels` con datos válidos responde 200 y deja auditoría con antes y después; ninguna fila de auditoría contiene un secreto.
4. `GET /api/v1/settings/channels` incluye por canal un campo de solo lectura `credentials_present` (bool) calculado desde `.env`, nunca el valor del secreto.
5. Activar `email` sin `SMTP_*` o `BREVO_API_KEY` en `.env` se permite, pero `credentials_present = false` y el envío deja los avisos en `failed` con `last_error = "credenciales ausentes"` (US-125).
6. Solo `admin`; el coach recibe 403.
7. `.env.example` agrega `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `BREVO_API_KEY`, `TELEGRAM_BOT_TOKEN` (alertas internas, N-34) vacíos y documentados.

## Escenarios BDD

```gherkin
# language: es
Característica: Canales de aviso

  Escenario: Habilitar el correo con remitente
    Dado que inicié sesión como administrador
    Y el archivo .env tiene SMTP_HOST y SMTP_PASSWORD
    Cuando guardo la sección canales con correo habilitado y remitente "APEX CrossFit"
    Entonces la respuesta es 200
    Y el canal correo muestra "credentials_present" verdadero
    Y la auditoría de la sección no contiene la contraseña SMTP

  Escenario: Rechazar un secreto en la configuración
    Dado que inicié sesión como administrador
    Cuando guardo la sección canales con el campo "telegram.token"
    Entonces la respuesta es 422
```

## Endpoints

- `GET /api/v1/settings/channels` — rol(es): admin — códigos: 200, 401, 403
- `PATCH /api/v1/settings/channels` — rol(es): admin — códigos: 200, 401, 403, 422

## Pantalla

- `Config`, pestaña Canales: interruptores, campos no secretos, insignia por canal con texto (no solo color) "Credenciales listas" o "Faltan credenciales en .env".

## Notas técnicas

- **Migración:** no (la sección se crea con su valor por defecto al primer `GET`, patrón de US-054).
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `validate_section("channels", ...)` con campo extra, correo inválido y valor por defecto.
- **Pruebas:** pura; router con rol; prueba de que la auditoría no contiene valores de `.env`.
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`, `api/src/app/core/config.py`, `.env.example`, `web/src/features/system/`.

## Supuestos

- Supuesto: `whatsapp_link.country_code` por defecto `57` para construir el `wa.me` con números colombianos guardados sin indicativo.

## Dependencias

- US-054 · Secciones de configuración validadas

## INVEST

- **Independiente:** solo depende de Settings.
- **Negociable:** los campos no secretos pueden crecer.
- **Valiosa:** habilita canales sin riesgo de filtrar secretos.
- **Estimable:** esquema más pestaña.
- **Pequeña:** 2.
- **Testeable:** 422 con secreto y ausencia de secretos en auditoría.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
