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
