# APEX · Runbook de operación

Procedimientos y valores de operación del api que no viven en el código. Alias usado en todo
el documento:

```
DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"
```

En producción se omite `-f infra/compose.dev.yml`.

## Índice

1. [Sesión y límites](#1-sesión-y-límites-s2-b2)
2. [Cuentas](#2-cuentas): primer admin, enlaces de activación y recuperación, ciclo de vida
3. [Auditoría de eventos de seguridad](#3-auditoría-de-eventos-de-seguridad-s2-b6)
4. [Socios](#4-socios): cifrado en reposo, búsqueda y listado
5. [Planes](#5-planes-s2-b9)
6. [Rollback por migración](#6-rollback-por-migración)

## 1. Sesión y límites (S2-B2)

### Capas del límite de intentos

Cada capa responde 429 `rate_limited` con `Retry-After`, el mismo cuerpo para cualquier correo
(no enumera cuentas). Los valores por defecto son los de producción; se cambian en `.env`.

1. **Borde (Nginx).** `limit_req` de `/api/v1/auth/`: 60 por minuto por IP con ráfaga de 30
   (zona en `infra/nginx/snippets/auth-zone.conf`, incluida por `infra/nginx/default.conf`). La
   imagen lleva siempre ese valor; solo el perfil E2E lo sube (ver abajo).
2. **Por IP en el api** (`core/ratelimit.rate_limit`). IPv4 exacta e IPv6 agrupada por /64.
   Ventana de 60 s: `LOGIN_IP_LIMIT=5` (`LOGIN_IP_WINDOW_S=60`), `REFRESH_IP_LIMIT=60`,
   `LOGOUT_IP_LIMIT=30`, `RESET_IP_LIMIT=10`, `FORGOT_IP_LIMIT=5`. La IP real sale de
   `X-Forwarded-For` solo si el socket es de `TRUSTED_PROXIES` (la IP fija de Nginx); el comando
   de desarrollo de uvicorn sigue sin `--proxy-headers` (S2-D51).
3. **Por cuenta y red** (`auth.service.login`, H-4). Clave `correo|red`, con la red /24 en IPv4
   y /64 en IPv6: `LOGIN_ACCOUNT_LIMIT=10` fallos por `LOGIN_ACCOUNT_WINDOW_S=900`. Solo suman
   los fallos (un acierto no consume cupo) y se comprueba antes de argon2, así el 429 llega sin
   gastar CPU. Diez fallos desde una red no impiden que la misma persona entre desde otra.
4. **Tope global por correo.** `LOGIN_ACCOUNT_GLOBAL_LIMIT=100` fallos por
   `LOGIN_ACCOUNT_GLOBAL_WINDOW_S=3600`, sumando todas las redes: solo desacelera un ataque
   repartido.
5. **Bloqueo persistente.** A los `LOGIN_LOCK_AFTER=20` fallos consecutivos la cuenta queda
   bloqueada (`auth.users.locked_at`), se cierran todas sus sesiones y se emiten `UserLocked` y
   `SessionsRevoked` con el usuario técnico como autor. Un acierto reinicia el contador
   (`failed_login_count`).

El **último admin activo** queda fuera de las capas 3, 4 y 5 (S2-D10): solo le rigen el
límite por IP y argon2, para que nadie pueda dejar el sistema sin administrador. Su
`failed_login_count` sí sube y queda en la base como evidencia.

### Contadores en memoria y desbloqueo

- Las capas 2 a 4 viven en la memoria del proceso del api (un solo proceso, sin `--workers`).
  `$DC up -d api` recrea el contenedor y los vacía. No usar `restart` tras editar `.env`:
  `env_file` solo se lee al crear el contenedor.
- El bloqueo persistente (capa 5) está en la base: lo levanta el botón "Desbloquear" del panel
  (`POST /users/{id}/unlock`, que también olvida los contadores en memoria de esa cuenta) o
  `cli unlock-user` (ver "Ciclo de vida de las cuentas"). `up -d api` limpia solo la memoria;
  el bloqueo sigue.
- Perfil E2E (E5): durante la validación V4 el `.env` sube los topes (por ejemplo
  `LOGIN_IP_LIMIT=1000`), se aplica con `up -d api` y se restaura al terminar. El borde se sube
  apilando `infra/compose.e2e.yml` (monta `infra/nginx/e2e/auth-zone.conf`, 6000r/m, sobre la
  zona de la imagen): `$DC -f infra/compose.e2e.yml up -d web`; se vuelve a producción con
  `$DC up -d web`. Comprobación: `docker exec apex-web-1 grep limit_req_zone
  /etc/nginx/snippets/auth-zone.conf` debe decir `rate=60r/m` fuera de V4. Todo el tráfico del
  host llega a Nginx con la misma IP (la puerta de enlace de la red de Compose) y cada carga de
  la SPA hace `POST /auth/refresh` y `GET /auth/me`: sin este perfil la suite `stack` recibe
  429 del borde en segundos.

### Refresh: rotación, gracia del reuso y tope absoluto

- El refresh viaja solo en la cookie `apex_refresh` (`HttpOnly`, `SameSite=Strict`,
  `Path=/api/v1/auth`, `Secure` con `COOKIE_SECURE=true`); en la base solo queda su SHA-256.
- Cada refresh rota la cookie (7 días, `REFRESH_TOKEN_TTL_DAYS`). Si llega un refresh ya rotado
  **antes de `REFRESH_REUSE_GRACE_S=10` segundos**, se trata como concurrencia benigna (recarga
  de página o dos pestañas): 401 `invalid_refresh` sin cerrar nada (M-2). Después de la gracia
  es un reuso real: se revocan todas las sesiones de esa cuenta, se fija
  `auth.users.tokens_valid_after` (los access ya emitidos dejan de valer en la siguiente
  petición, H-3) y se emite `SessionsRevoked(reason="refresh_reuse")`. La persona debe entrar
  de nuevo en todos sus dispositivos.
- Una familia de refresh dura como mucho `REFRESH_ABSOLUTE_TTL_DAYS=30` días desde el login
  (`family_started_at`), aunque siga rotando (L-4). Cada login borra los refresh de esa cuenta
  vencidos hace más de 30 días.
- Logout (por la cookie, H-1) revoca solo esa sesión, responde siempre 204 y borra la cookie,
  aunque el access ya haya vencido.
- Login, refresh y logout exigen el mismo origen (M-1): `Origin`, o `Referer` si falta, contra
  `AUTH_ALLOWED_ORIGINS` (vacía = el origen de `FRONT_BASE_URL`); sin ninguno de los dos acepta
  `Sec-Fetch-Site: same-origin|none`. Si no, 403 `forbidden` sin tocar la cookie. En local:
  `AUTH_ALLOWED_ORIGINS=http://localhost:8180,http://localhost:5173` (Nginx y Vite).

### Piso de duración del login (`LOGIN_MIN_DURATION_MS`)

Toda respuesta 401 de login dura al menos `LOGIN_MIN_DURATION_MS` (M-6, S2-D39), así un correo
existente y uno inexistente tardan lo mismo. El valor es 1,5 veces la mediana de
`verify_password` (argon2id 3 / 65536 KiB / 4) más el commit de una escritura, medida dentro
del contenedor `api` (un script desechable copiado con `docker cp` y corrido con
`docker exec -w /app apex-api-1 python`: `verify_password` en un hilo con los parámetros de
`Settings` y luego un `UPDATE` de una fila de `auth.users` con commit; 30 muestras por corrida
tras 2 de calentamiento):

- medición del 2026-10-22 (S2-B2): medianas de 47,8, 46,6 y 58,8 ms en tres corridas; 1,5 veces
  unos 48 ms da 72 ms, redondeado a **75 ms** (valor por defecto en `Settings` y
  `.env.example`).

Remedir si cambian los parámetros de argon2 o el hardware del servidor y ajustar
`LOGIN_MIN_DURATION_MS` en `.env`.

### Cookie sin TLS (riesgo aceptado P7)

En v0.1 el gimnasio corre en la LAN sin TLS. Con `ENV=production` el api no arranca con
`COOKIE_SECURE=false` salvo que `ALLOW_INSECURE_COOKIE=true` lo autorice de forma explícita
(M-9). Ponerla en `true` es aceptar que la contraseña y la cookie del refresh viajan en claro
por la red local; se quita al activar TLS (v0.3) junto con `COOKIE_SECURE=true`.

## 2. Cuentas

### Primer admin

`ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` van en `.env.seed` (solo lo lee el servicio `tools`):
`$DC run --rm tools seed`. El admin sembrado debe cambiar la contraseña al entrar
(`must_change_password`); `--no-force-change` solo se acepta con `ENV=dev`. Una segunda corrida
dice "omitido". Borrar `.env.seed` después del primer seed. Tras cambiar `cli.py` hay que
reconstruir la imagen (`$DC build api`) antes de usar `tools`.

### Enlaces de activación y restablecimiento (S2-B4)

#### Recuperar a un admin

`POST /users/{id}/resend-link` (botón "Reenviar enlace" del panel) responde 409
`user_not_eligible` sobre la propia cuenta del admin que lo pide y sobre otro admin activo con
contraseña (L-13): un admin no puede tomar la cuenta de otro desde el panel. Para esos casos,
y para el admin que olvidó su contraseña, se usa el CLI desde el servidor:

```
$DC build api   # solo si cambió cli.py desde la última imagen
$DC run --rm tools issue-reset-link <correo de la cuenta> --as <correo de un admin activo>
```

- `--as` es obligatorio y debe ser un admin en estado `active`; puede ser la misma cuenta (un
  admin que recuerda su contraseña pero quiere rotarla) u otro admin. Si no hay ningún admin
  activo, primero `cli unlock-user` (S2-B5) o, sin admins, `seed`.
- Imprime una sola vez la URL `<FRONT_BASE_URL>/restablecer/<token>`: con contraseña es un
  enlace `reset` de 1 h; sin contraseña (pendiente), uno `activate` de 72 h. Cerrar el
  terminal después de copiarla; la base guarda solo el hash del token.
- Cierra el enlace abierto anterior del mismo propósito: el último emitido es el único que
  sirve. Deja el `insert` auditado con el admin de `--as` como autor.
- Sale con 2, sin crear nada, si falta `--as`, si no es un admin activo o si la cuenta no puede
  recibir el enlace (no existe, está borrada, bloqueada o inactiva: el mismo mensaje, que no
  revela cuál).
- Usar el enlace (`POST /auth/reset`) fija la contraseña, limpia `must_change_password` y el
  contador de fallos y, si es `reset`, cierra todas las sesiones de la cuenta. No inicia sesión.
  Una cuenta bloqueada no puede usarlo: primero `cli unlock-user`.

#### `forgot` en v0.1

`POST /auth/forgot` responde siempre 204 sin cuerpo y en v0.1 **no envía ni crea nada** (H-2,
S2-D36): no hay canal al socio hasta US-131. Quien olvida la contraseña pide al admin un enlace
nuevo ("Reenviar enlace" en el panel; para admins, el CLI de arriba). Límites: 5 por minuto por
IP (`FORGOT_IP_LIMIT`) y 5 por hora por correo desde cualquier IP (`forgot-account`, constante
`FORGOT_ACCOUNT_LIMIT` / `FORGOT_ACCOUNT_WINDOW_S=3600` en `auth/service.py`), ambos en memoria
(`$DC up -d api` los vacía). Toda respuesta dura al menos `LOGIN_MIN_DURATION_MS`, y el log
(`forgot recibido`) no lleva el correo.

### Ciclo de vida de las cuentas (S2-B5)

#### Desbloquear una cuenta

Desde el panel, "Desbloquear" (`POST /users/{id}/unlock`, solo admin). Desde el servidor, por
ejemplo cuando el bloqueado es el único admin:

```
$DC build api   # solo si cambió cli.py desde la última imagen
$DC run --rm tools unlock-user <correo de la cuenta> --as <correo de una persona activa>
```

- Qué limpia: `locked_at` y `failed_login_count` (deja el `update` auditado con la persona de
  `--as` o, sin `--as`, con el usuario técnico) y cierra los enlaces de activación o
  restablecimiento que quedaron abiertos (un enlace emitido antes del bloqueo no revive).
- Qué no toca: las sesiones siguen cerradas (el bloqueo las revocó y fijó
  `tokens_valid_after`); la persona vuelve a entrar con su contraseña.
- Contadores en memoria: el botón del panel los olvida en el proceso del api (límite por
  cuenta y su tope global). El CLI corre en otro proceso y no los alcanza: si la cuenta sigue
  recibiendo 429 tras el CLI, `$DC up -d api` los vacía (todos).
- `--as` debe ser una persona en estado `active`; si no, sale con 2 y lo dice.
- Sale con 2 y el mismo mensaje, sin repetir el correo, si la cuenta no está bloqueada, no
  existe o está borrada (no revela cuál). Una segunda invocación sobre la misma cuenta sale
  con 2.

#### Bloquear, cerrar sesiones y dar de baja

- "Bloquear" (`POST /users/{id}/lock`) fija `locked_at`, cierra todas las sesiones y corta los
  access ya emitidos en la siguiente petición. Un admin no se bloquea a sí mismo (409
  `cannot_lock_self`).
- "Cerrar sesiones" (`POST /users/{id}/revoke-sessions`) revoca todos los refresh y corta los
  access sin bloquear: la persona vuelve a entrar con su contraseña. Responde
  `{"revoked": n}`.
- "Dar de baja" (`DELETE /users/{id}`) es una baja lógica: la fila queda con `deleted_at`, en
  la auditoría y visible en el detalle con estado `deleted`; nunca se borra. Cierra sus
  sesiones y libera el correo para una cuenta nueva. Una segunda baja da 404.
- Último admin: ninguna baja, bloqueo ni cambio de rol puede dejar el sistema sin un admin
  activo (409 `last_admin`). Un admin pendiente de activación, bloqueado o el usuario técnico
  no cuentan. Para retirar al último admin, primero crear y activar otro.
- Cambiar el correo de una cuenta (`PATCH /users/{id}`) cierra los enlaces de activación o
  restablecimiento abiertos: si la cuenta seguía pendiente, se le reenvía uno nuevo al correo
  corregido ("Reenviar enlace").

## 3. Auditoría de eventos de seguridad (S2-B6)

- Cada login sobre un correo existente (correcto o fallido), cada bloqueo, cada cierre de sesiones y cada cambio de contraseña deja una fila en `audit.audit_log` escrita por el módulo `audit` dentro de la misma transacción. Consulta rápida: `SELECT action, user_id, after FROM audit.audit_log ORDER BY seq DESC LIMIT 10;`. La fila `login` guarda `result`, `reason`, `ip` y `user_agent`, nunca el correo tecleado; un correo inexistente no deja fila.
- La auditoría es parte de la operación (fail-closed): si la cadena no se puede escribir (base sin espacio, candado de la cadena retenido, trigger), el login responde 500 y el fallo ni siquiera suma al contador; lo mismo pasa con bloquear, cerrar sesiones o cambiar la contraseña. Ante 500 en el login, revisar primero `docker compose logs api` y el estado de `audit.audit_log` antes de tocar las cuentas.
- Los comandos `seed`, `unlock-user` e `issue-reset-link` del CLI cargan los mismos suscriptores, así que lo que hacen queda auditado igual que desde el api.

## 4. Socios

### Cifrado en reposo (S2-B7)

- En claro en `members.members`: `first_name` y `last_name` (van al leaderboard), `sex`, `status`, `document_type`, `data_consent_at`, `data_consent_version` y las columnas comunes. No existe `notes` ni ninguna columna `*_hint`.
- Cifrados por el bus (AES-256-GCM, `aad = id` del socio, blob `apx1.<key_id>.A256GCM.<nonce>.<ciphertext>`): `document`, `phone`, `email`, `birth_date` y `emergency_contact`. Índices ciegos HMAC-SHA-256 en `document_idx`, `phone_idx` y `email_idx` (normalización N-02: el documento sin puntos ni guiones, el teléfono sin el `57` inicial, el correo en minúsculas). La base rechaza por CHECK cualquier texto en esas columnas que no empiece por `apx1.`.
- La respuesta del api enmascara en memoria (`CC •••• 4417` para `1.020.304.417`, `••• ••• 4321`, `l•••@•••.co`, `••/••/1991`, `Registrado`); el alta no descifra nada.
- Verificar con psql (no debe aparecer ningún dato legible):
  - `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml exec db psql -U apex -d apex -c "SELECT document, document_idx, phone, email FROM members.members LIMIT 5;"`: blobs `apx1.` y hashes hexadecimales de 64 caracteres;
  - `SELECT verb, data_class, record_id, user_id FROM crypto.crypto_ops ORDER BY at DESC LIMIT 10;`: cada alta deja `encrypt` por campo presente e `index` por índice, atribuidos a quien registró;
  - `SELECT action, table_name, subject_member_id, after->>'document' FROM audit.audit_log WHERE table_name = 'members.members' ORDER BY seq DESC LIMIT 5;`: la fila `insert` lleva el blob, nunca el claro.
- Un documento repetido entre socios no dados de baja responde 409 `member_document_duplicated` con `existing_id`; el único parcial `uq_members_document_idx_alive` decide aunque dos altas lleguen a la vez. La baja de socios llega con US-076 (Sprint 3); hasta entonces no hay forma de liberar un documento.
- Límite: 60 altas por minuto por usuario autenticado (429 `rate_limited` con `Retry-After`); el contador vive en memoria y se limpia con `up -d api`.
- Rotación: en v0.1 no hay rotación de llaves de `member.*`; llega en v0.2 con OpenBao (`cli rotate-key`, US-030), que recifra con la llave nueva sin cambiar el formato del blob.

### Búsqueda y listado (S2-B8)

- `GET /api/v1/members` (admin y coach) pagina con `limit` (1 a 200, 25 por defecto) y `offset`; filtra por `status` (`active`, `inactive`, `deleted`; sin `status` solo los no dados de baja) y ordena con `sort` (`last_name` por defecto, `-` es descendente). Las filas nunca traen documento, teléfono, correo, fecha de nacimiento ni contacto, ni en claro ni enmascarados; listar no descifra nada.
- La caja de búsqueda `q` (hasta 100 caracteres, nunca se registra en logs) se reparte así:
  - documento (solo letras y dígitos con al menos un dígito, tras quitar puntos, guiones y espacios): índice ciego, usa el único parcial `uq_members_document_idx_alive`;
  - teléfono (7 o más dígitos, con o sin `+57`): índice ciego, usa `ix_members_phone_idx`;
  - correo (si tiene `@`): índice ciego, usa `ix_members_email_idx`;
  - nombre y apellido, siempre: `ILIKE` sin mayúsculas ni tildes (`translate(lower(...))`) con `%`, `_` y `\` escapados. Esta rama NO usa índice (recorre la tabla de socios vivos); con cientos o pocos miles de socios responde en milisegundos. Si la tabla crece mucho, la deuda anotada para el Sprint 4A es un índice `pg_trgm` o una columna normalizada.
- Cada búsqueda con `q` deja en `crypto.crypto_ops` entre una y tres filas `index` del mismo lote (`batch_id`), una por clase; una búsqueda solo por nombre o una lista sin `q` no deja ninguna, y nunca hay `decrypt`.
- Límite: 60 búsquedas con `q` por minuto por usuario (429 `rate_limited` con `Retry-After`); la lista sin `q` no cuenta. El contador vive en memoria y se limpia con `up -d api`.
- Pruebas de rendimiento (marcador `perf`; 1.000 socios, búsqueda por documento bajo 500 ms con `EXPLAIN` del único parcial, y L-11 de 20 logins fallidos concurrentes con p95 bajo 2 s): `cd api && uv run pytest -m perf -q -s` (con `TEST_DATABASE_URL`). Los gates corren `-m "not perf"` salvo el de B8 y V5.

## 5. Planes (S2-B9)

- `POST /api/v1/plans` solo lo usa el admin. El nombre es único entre los planes no dados de baja sin distinguir mayúsculas ni espacios de los extremos: con "Mensual" creado, "mensual" o "  MENSUAL  " dan 409 `plan_name_duplicated` con `existing_id` (índice `uq_plans_name_alive` sobre `lower(btrim(name))`). Dar de baja un plan (Sprint 4A) libera el nombre.
- Tipos: `days` (sin `class_count`) y `classes` (con `class_count` de 1 a 1.000). Topes: precio de 1 a 1.000.000.000 COP (entero), duración de 1 a 3.650 días. La base repite las reglas por CHECK (`\d plans.plans`).
- Alcance del coach: `GET /api/v1/plans?active=true` y `GET /api/v1/plans/{id}` de planes activos; sin `active=true` o sobre un plan inactivo recibe 403 `forbidden`. El admin ve activos e inactivos. Los dados de baja no aparecen nunca (404 en el detalle).
- La búsqueda `q` no distingue mayúsculas ni tildes. En todas las listas (`/users`, `/members`, `/plans`) un `q` con caracteres de control (por ejemplo `%00`) da 422 con `field="q"`.

## 6. Rollback por migración

Regla general:
1. Bajar la migración primero: `$DC exec api alembic downgrade <revisión anterior>`.
2. Después revertir el checkpoint del slice con `git revert <sha>`.
3. Después `$DC restart api`.

Si se revierte primero el código, el archivo de migración desaparece y el arranque falla con "Can't locate revision". Antes de cada migración se guarda un `pg_dump -Fc` (P-MIG, paso 1); restaurar es `pg_restore --clean` sobre `apex-db-1`.

- **`0005_settings`:** `downgrade 0004_auth` borra `settings.settings_sections`; se pierde la configuración de desarrollo. Hay que revertir B1, y también B2 o posteriores si existen, porque `0005b` depende de ella: bajar en cadena `0007 → 0006 → 0005b → 0005`.
- **`0005b_auth_security`:** `downgrade 0005_settings` quita las cuatro columnas y el CHECK. El código de B2 a B5 las usa: se revierten esos checkpoints en orden inverso. Las sesiones vigentes siguen siendo válidas.
- **`0006_members`:** `downgrade 0005b_auth_security` borra `members.members` y sus blobs. Las llaves de `crypto_keys` se conservan. Solo hay datos de desarrollo. Se revierten B7 y B8 (y F6 si se fusionó).
- **`0007_plans`:** `downgrade 0006_members` borra `plans.plans`. Se revierte B9 (y F7).
- En CI y `db_test` no hace falta rollback: `migrated_database` vuelve a migrar desde cero.
