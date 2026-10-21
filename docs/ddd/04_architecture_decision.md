# 04 · Decisión de arquitectura

Fecha: 21 de octubre de 2026. Entradas: `01_product_discovery.md`, `02_domain_model.md`, `03_context_map.md`, `CLAUDE.md`.

## 1. Decisión

**Monolito modular** en un solo proceso FastAPI, un solo PostgreSQL con un esquema por contexto, un worker en la misma imagen con comando distinto, y un front React estático servido por Nginx. Comunicación entre contextos por llamadas a `service.py` y por un bus de eventos en memoria que corre dentro de la misma transacción. Sin microservicios, sin colas externas, sin caché distribuida.

Esta decisión ya estaba tomada en `CLAUDE.md`; aquí se registra el razonamiento y los límites para que sea un ADR verificable (`docs/adr/ADR-001-monolito-modular.md` se genera a partir de esta sección en la Tarea 12).

## 2. Por qué

- Un solo gimnasio, un solo servidor, menos de 10 usuarios concurrentes y hasta 1.000 socios. La carga no justifica distribuir nada.
- La consistencia importa más que la disponibilidad parcial: vender una membresía y registrar su primer pago deben ser atómicos (S5); activar por cobertura (RN-03) necesita ver el pago en la misma transacción. Un bus en memoria dentro de la transacción lo da gratis; una cola externa obligaría a sagas.
- Operación por una persona no técnica: `docker compose up`, un backup nocturno y un `/health`. Cada servicio adicional es un punto de fallo que nadie vigila.
- El cifrado por campo con DEK en memoria exige que un solo proceso tenga las llaves abiertas; repartirlas entre servicios multiplica la superficie.
- Los bounded contexts siguen existiendo como módulos con esquema propio y reglas de importación estrictas. Si un día hace falta extraer uno (por ejemplo, notificaciones), la frontera ya está.

## 3. Alternativas descartadas

- **Microservicios por contexto:** más despliegues, más red, sagas para RN-03 y S5, y tres veces el trabajo operativo para el mismo gimnasio. No.
- **Monolito sin módulos (una carpeta `models.py` y otra `routers.py`):** rápido al inicio, imposible de mantener con 16 contextos y datos cifrados. No.
- **Backend-as-a-service (Supabase, Firebase):** licencias y datos personales fuera del servidor del gimnasio; el cifrado por campo con llaves propias no encaja. No.
- **Cola externa (Redis, RabbitMQ) para eventos:** útil cuando hay consumidores fuera del proceso. Aquí el único proceso aparte es el worker, y lo que hace (vencimientos, avisos) es por tiempo, no por evento. Se reconsidera si los avisos por correo o Telegram empiezan a bloquear peticiones; entonces se mueve el envío al worker con una tabla `notifications` como cola (ya está modelada así).

## 4. Vista de despliegue

```
Internet / LAN del gimnasio
        │
   ┌────▼─────┐  TLS automático (v0.3), X25519MLKEM768
   │  caddy   │  (opcional; en v0.1 Nginx escucha directo en 80)
   └────┬─────┘
   ┌────▼─────┐  sirve web/dist, proxy /api → api:8000,
   │  nginx   │  cabeceras de seguridad, CSP, 5 MB de subida
   └────┬─────┘
   ┌────▼─────┐  FastAPI + Uvicorn, alembic upgrade head al arrancar,
   │   api    │  DEKs en memoria, /health
   └────┬─────┘
   ┌────▼─────┐  misma imagen, comando worker: APScheduler
   │  worker  │  07:00 America/Bogota: expirations, notify, sign_audit, backup_check
   └────┬─────┘
   ┌────▼─────┐  PostgreSQL 16, volumen pgdata, 16 esquemas
   │    db    │
   └──────────┘
   ┌──────────┐  pg_dump nocturno, cifrado con age, subida con rclone,
   │  backup  │  firma ML-DSA (v1.0)
   └──────────┘
   ┌──────────┐  OpenBao con motor Transit (v0.2): KEK y llaves de firma
   │ openbao  │  nunca salen; desellado con llaves fuera del servidor
   └──────────┘
   Volúmenes: pgdata, uploads (/data/uploads), backups, keys (KEK local v0.1, 600)
```

## 5. Patrones de comunicación

- **Síncrono dentro del proceso:** `modules/<a>/service.py` llama a `modules/<b>/service.py`. Nunca a `models` ajenos. Lo verifica un test de arquitectura que importa cada módulo y falla si encuentra `from app.modules.<otro>.models`.
- **Eventos en memoria:** `core/events.py` con `subscribe(EventType, handler)` y `emit(event)`. Los handlers corren en la misma sesión y transacción; un fallo revierte todo. Los eventos son dataclasses congeladas.
- **Trabajos por tiempo:** el worker no recibe eventos; consulta tablas. `expirations` recalcula estados y emite eventos dentro de su propia transacción; `notify` lee `notifications` en `pending` y envía.
- **HTTP hacia afuera:** `httpx` con timeout explícito para Telegram, SMTP (vía `aiosmtplib` o Brevo API), rclone en el contenedor de backup. Todo opcional y degradable: si el canal falla, el aviso queda `failed` con `last_error` y aparece en "por avisar hoy".
- **Front ↔ API:** REST JSON bajo `/api/v1`, OpenAPI exportado a `docs/openapi.json`; el front genera tipos desde ahí. Paginación `limit`/`offset` (S2). Errores con envelope `{ "error": { "code", "message", "field"? } }`.

## 6. Decisiones de seguridad que fija la arquitectura

- Las llaves (KEK local o token de OpenBao) entran por volumen o por `.env`, nunca por imagen.
- `core/crypto` y `core/security` son los únicos lugares con primitivas; lint `banned-api` lo impone.
- Todo endpoint declara rol; un test de arquitectura recorre las rutas registradas y falla si alguna no tiene dependencia de rol y no está en la lista blanca (`/health`, `/auth/login`, `/auth/forgot`, `/auth/reset`, `/tv/today`).
- Rate limit en login y en `forgot` (5 por minuto por IP) con `slowapi` (MIT) o contador en memoria.
- Nginx: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP con nonce para el front, `client_max_body_size 5m`.
- Logs JSON a stdout sin datos personales: nunca se loguea un campo cifrado ni un token.
- La TV usa un token de dispositivo largo, rotable desde Configuración, con alcance de solo lectura y sin datos personales (solo nombre y marca).

## 7. Decisiones de datos que fija la arquitectura

- Un esquema por contexto; Alembic con `version_table` por defecto y migraciones revisadas a mano; `create_all` prohibido fuera de tests.
- Triggers de PostgreSQL para inmutabilidad de `payments`, `audit_log`, `crypto_ops`, `wod_results` (solo `UPDATE` de columnas de anulación/validación permitido).
- Cadena de auditoría por hook `after_flush` en SQLAlchemy sobre tablas con `__audited__ = True`.
- Tipos de columna `Encrypted(data_class)` y `BlindIndexed(data_class)` en `core/crypto/types.py`; AAD = id del registro.
- UTC en base, `America/Bogota` solo para el worker (hora de disparo) y para el front.

## 8. Trade-offs aceptados

- Un solo proceso significa que un bug en un módulo tumba todo; se compensa con tests por módulo, healthcheck y reinicio automático de Compose.
- El bus en memoria no sobrevive a un reinicio: cualquier efecto que deba ocurrir sí o sí (avisos) se persiste en tabla y lo reintenta el worker.
- Las DEK en memoria del proceso: quien tenga acceso al contenedor en ejecución puede leerlas. Se acepta para v0.1; OpenBao en v0.2 saca la KEK del proceso y permite revocarla.
- La TV es pública dentro de la LAN con token: un token filtrado muestra nombres y marcas. Se acepta (es información que ya está en la pizarra del box) y el token se rota desde Configuración.

## 9. Preguntas acumuladas para el gate

- **P7:** ¿Habrá dominio público con TLS desde v0.1 o solo LAN? Supuesto: solo LAN en v0.1 (HTTP en el puerto 80 de la red local); Caddy con TLS en v0.3 cuando haya dominio. Si hay dominio desde el inicio, Caddy entra en v0.1 y el portal del socio puede adelantarse.
