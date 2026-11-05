# Correo y Telegram: configuración de los canales

Procedimiento de operación de los canales de salida (Sprint 5, v0.2; S5-D29, S5-D30, S5-D44, S5-D64, S5-D78, S5-D203 a D205). Todos los comandos se corren desde la raíz del repositorio.

## 1. Qué hay

- **Correo (SMTP)**: lo envía `core/mail.py` con la biblioteca estándar. Es una cuenta de **solo envío** (no se leen buzones). Texto plano, nunca HTML. Conexión por STARTTLS (puerto 587) que verifica el certificado y el nombre del servidor.
- **Telegram**: canal **interno del equipo** (resumen diario de avisos y alertas del worker). Va al chat del equipo, **nunca a un socio** y nunca lleva datos de socios: solo conteos, nombres de job y el enlace a `/avisos/hoy`.
- **WhatsApp**: no se envía desde el servidor; es un enlace que abre la persona (solo se configura el indicativo del país).

## 2. Variables

| Dónde | Variable | Qué es |
|---|---|---|
| `.env` | `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_FROM`, `SMTP_TLS_MODE` (`starttls`) | Servidor y remitente. |
| `.env.ops` | `SMTP_PASSWORD` | Clave de la cuenta (nunca en `.env`). |
| `.env` | `TELEGRAM_CHAT_ID` | Chat del equipo (grupo o canal privado). |
| `.env.ops` | `TELEGRAM_BOT_TOKEN` | Token del bot (nunca en `.env`). |
| `.env` | `NOTIFY_NET_TIMEOUT_S` (10) | Tiempo máximo de cada conexión de salida. |

Reglas: o están `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM`, o no hay ninguno (si falta uno, el api no arranca y nombra la variable). Telegram solo se activa con token **y** chat. `SMTP_TLS_MODE=none` y una `TELEGRAM_API_BASE` distinta de la oficial solo se admiten con `ENV=dev`.

## 3. Cuenta de correo

1. Cree una cuenta (o un usuario de aplicación) dedicada a APEX, con permiso solo para enviar.
2. Ponga un **tope diario de envíos** en el proveedor (un valor un poco por encima de los socios activos) para que una cuenta comprometida no pueda enviar sin límite.
3. Configure SPF y DKIM del dominio del remitente; sin ellos los avisos caen en spam.
4. Cargue las variables y reinicie: `$DC up -d api worker`.

## 4. Bot de Telegram

1. Cree el bot con `@BotFather` y copie el token a `.env.ops`.
2. Cree un grupo privado del equipo, agregue el bot y obtenga el `chat_id` (negativo en los grupos); póngalo en `.env`.
3. Reinicie `api` y `worker`. La alerta pendiente sale antes del apagado (`flush`); si Telegram no responde, la alerta se pierde sin afectar al job y el log dice solo el tipo del error.

## 5. Qué ve el equipo en Ajustes

`GET /settings/channels` devuelve la sección (`email`, `whatsapp`, `telegram`, cada uno con `enabled`) y `credentials_present {email, telegram}`: si el servidor tiene lo necesario para cada canal. Nunca devuelve valores. Se puede activar un canal sin credenciales; simplemente no sale nada hasta cargarlas.

## 6. Probar en desarrollo

Con el perfil `avisos` (solo `compose.dev.yml`): Mailpit recibe el correo (interfaz en `http://127.0.0.1:8125`) y `telegram-fake` imprime el JSON de cada alerta en su log.

```
DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"
$DC --profile avisos up -d mailpit telegram-fake
# SMTP_HOST=mailpit SMTP_PORT=1025 SMTP_TLS_MODE=none SMTP_FROM=apex@dev.local
# TELEGRAM_API_BASE=http://telegram-fake:8081 TELEGRAM_BOT_TOKEN=123:prueba TELEGRAM_CHAT_ID=1
$DC logs telegram-fake
$DC --profile avisos stop mailpit telegram-fake
```

## 7. Límites conocidos

- **Solo STARTTLS en el 587.** El TLS implícito (puerto 465) no está soportado: con `SMTP_PORT=465` el envío falla cerrado por timeout. Si su proveedor solo ofrece el 465, pídalo para v0.3 (S5-D207).
- **Alertas de Telegram.** Cada proceso guarda como mucho 20 alertas pendientes (la 21.ª se descarta con una línea de log) y una misma alerta (mismo código y mismo job) no se repite dentro de 60 segundos.
- **Remitente y respuesta.** El nombre del remitente y el `Reply-To` los fija el administrador en Ajustes; se validan y no admiten saltos de línea (S5-D208).

## 8. Plantillas y reglas de aviso (S5-B6; S5-D24, S5-D25, S5-D212 a D214)

Los avisos de vencimiento salen de **plantillas** (el texto) y **reglas** (cuándo y por qué canal). Las edita el administrador; el entrenador solo las lee; el socio no las ve. Rutas: `/api/v1/notification-templates` y `/api/v1/notification-rules` (listas con `q`, `limit` y `offset`).

**Variables.** Cuatro, escritas entre llaves: `{nombre}` (nombre del socio), `{plan}`, `{vence}` (fecha de fin de la membresía) y `{dias}` (días de diferencia, **siempre sin signo**: "vence en {dias} días" y "venció hace {dias} días"). `{{` y `}}` escriben una llave literal. Cualquier otra cosa entre llaves (`{apellido}`, `{nombre!r}`, `{0}`, `{}`) o una llave sin cerrar da 422 con el campo (`subject` o `body`); el mensaje no repite el texto. Asunto de hasta 150 caracteres, cuerpo de hasta 2.000, nombre de hasta 80.

**Vista previa.** `POST /notification-templates/preview` con `{subject, body}` devuelve ambos renderizados con un socio de ejemplo (Ana, plan Mensual, vence el 20 oct 2026, 3 días). No escribe nada y consume la cubeta de lectura (`staff-read`, 120 por minuto), no la de escritura; asunto y cuerpo siguen las mismas reglas de texto que una plantilla (sin saltos de línea en el asunto, sin caracteres de control). Si al sustituir un valor del socio el asunto quedara con un salto de línea, se rechaza.

**Reglas.** Cada una tiene disparador, desfase en días, canal y plantilla:

| Disparador | Desfase | Significado |
|---|---|---|
| `membership_expiring` | 0 o negativo | Antes del fin (`-3` = tres días antes; `0` = el mismo día). |
| `membership_expired` | 1 o más | Después del fin (`7` = siete días después). |

Canales: `email` y `whatsapp_link`. Solo puede haber **una regla activa** por (disparador, desfase, canal): la segunda da 409 `duplicate_active_rule` con el id de la existente. Las reglas no se borran, se desactivan; las plantillas tampoco se borran. Se valida la regla resultante al editar (cambiar solo el disparador deja el desfase anterior y puede dar 422 `offset_days`). Una plantilla inexistente da 422 con `field=template_id`.

**Auditoría.** Toda alta o cambio queda en `audit.audit_log` a nombre de quien lo hizo.

## 9. Siembra de plantillas y reglas por defecto

Dos plantillas ("Vence pronto" y "Venció") y cinco reglas, todas por `whatsapp_link` y activas: `-3` y `0` (`membership_expiring`) y `1`, `7` y `15` (`membership_expired`).

- **Instalación nueva:** `seed` (primer administrador) las siembra también.
- **Instalación existente** (ya tenía un admin antes de v0.2): `$DC --profile tools run --rm tools seed-notifications --as <correo del admin>`.

Es **idempotente**: la segunda corrida imprime `plantillas creadas 0, reglas creadas 0` y no escribe ni audita. No pisa lo que el administrador ya cambió: una plantilla con el mismo nombre se conserva tal cual, y una regla con la misma clave (disparador, desfase y canal), sea cual sea su nombre y esté activa o no, cuenta como existente (no se reactiva ni se duplica). Con `ENV=production` `--as` es obligatorio. El job `notify` no siembra: el worker solo puede leer estas tablas. Dos siembras a la vez se serializan con un candado de la base: la segunda no crea nada (si algo chocara, 409 `seed_in_progress`: reintente). `seed` siembra los avisos en una segunda transacción tras crear al administrador; si esa siembra falla, el administrador queda creado, `seed` sale con 1 y se corre `seed-notifications`.
