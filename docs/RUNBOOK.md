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
4. [Socios](#4-socios): cifrado en reposo, búsqueda y listado, ficha, revelar y editar, pestañas de membresías y pagos, historial de la ficha, contacto para avisos
5. [Planes](#5-planes-s2-b9)
6. [Rollback por migración](#6-rollback-por-migración)
7. [Imágenes base por digest y su renovación](#7-imágenes-base-por-digest-y-su-renovación-s3-d62)
8. [Primer admin sin `.env.seed`](#8-primer-admin-sin-envseed-s3-d64)
9. [Tiempos de espera de la base y 503 `busy`](#9-tiempos-de-espera-de-la-base-y-503-busy-s3-w0-2)
10. [Membresías y pagos](#10-membresías-y-pagos-sprint-3)
11. [Worker, auditoría verificable y tablero](#11-worker-auditoría-verificable-y-tablero-sprint-4a)

## 1. Sesión y límites (S2-B2)

### Capas del límite de intentos

Cada capa responde 429 `rate_limited` con `Retry-After`, el mismo cuerpo para cualquier correo
(no enumera cuentas). Los valores por defecto son los de producción; se cambian en `.env`.

1. **Borde (Nginx).** `limit_req` de `/api/v1/auth/`: 60 por minuto por IP con ráfaga de 30
   (zona en `infra/nginx/snippets/auth-zone.conf`, incluida por `infra/nginx/default.conf`). La
   imagen lleva siempre ese valor; solo el perfil E2E lo sube (ver abajo). El valor se revisa
   en el Sprint 10, cuando el portal del socio (v1.0) sume tráfico de sesión desde los
   celulares de la misma red: 60 por minuto por IP puede quedar corto detrás de un NAT (L5).
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

### Topes de las escrituras de admin y de cuerpo (V10 del Sprint 3)

- **`admin-write`** (30 por minuto por usuario, `USER_ADMIN_WRITE_LIMIT_PER_MIN`): una sola
  cubeta para toda escritura de solo admin: crear planes, los cinco `PATCH /settings/*`, crear
  usuarios, reenviar su enlace, editarlos y darlos de baja, anular pagos y membresías, y dar de
  baja y reactivar socios. La 31 del minuto da 429 con `Retry-After`; otro admin no se ve
  afectado (S3-D100).
- **Exentas a propósito:** `POST /users/{id}/lock`, `/unlock` y `/revoke-sessions`. Son la
  respuesta a un incidente: aunque la cubeta esté agotada siguen respondiendo. Pasan por la
  auditoría. `tests/architecture/test_writes_have_user_limit.py` falla si aparece una escritura
  nueva sin tope ni motivo.
- **Cuerpo en Nginx** (S3-D101): 16k en `/api/v1/auth/`, 64k en el resto de `/api/` (y en
  `/api/v1/tv/`), 128k solo en `PATCH /api/v1/settings/privacy` (el texto de la política admite
  20.000 caracteres) y 5m en el server para los adjuntos de v0.3. Un cuerpo mayor responde 413
  en el borde, sin llegar al api.

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
- `scripts/smoke/headers.sh` agota a propósito el `limit_req` de la IP desde la que corre (su
  ráfaga de 45 POST prueba el 429 del borde). Si después se corre `npm run e2e:stack` sin el
  perfil E2E, o se prueba el login a mano, las primeras peticiones a `/api/v1/auth/` reciben
  429: esperar 60 segundos (L4).

### IP real en el borde (N-6)

Nginx limita por `$binary_remote_addr` y pasa `X-Forwarded-For $remote_addr` al api, que
solo lo cree si el socket es de `TRUSTED_PROXIES`. Todo depende de que `remote_addr` sea la IP
del cliente:

- En Docker Desktop (Windows, macOS) y con el `userland-proxy` de Docker, `remote_addr` es la
  puerta de enlace de la red de Compose (en V4, `172.30.0.128`), no el cliente: todos
  comparten los 60r/m del borde y los 5 logins por minuto del api. Es lo que pasa en
  desarrollo y en CI, y por eso existe el perfil E2E.
- En el servidor del gimnasio (Linux con Docker Engine) se verifica al instalar, desde otro
  equipo de la LAN: abrir `/login` y mirar el access log,
  `docker logs --tail 5 apex-web-1 | grep -o '"remote_addr":"[^"]*"'`. Debe aparecer la IP del
  equipo. Si aparece la puerta de enlace, poner `"userland-proxy": false` en
  `/etc/docker/daemon.json`, reiniciar Docker y repetir; si sigue igual, no abrir el sistema
  hasta resolverlo, porque un solo equipo agotaría el límite de todos. Dueño: S4B-W0-2
  (despliegue en el servidor).

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
existente y uno inexistente tardan lo mismo. El valor es **150 ms (p99)**: debe quedar por
encima del p99 de la rama de cuenta existente (`verify_password` con argon2id 3 / 65536 KiB / 4,
el commit de una escritura y la fila de auditoría, que espera el candado global de la cadena),
no de su mediana. Con un piso por debajo del p99, bajo contención la cuenta existente pasa del
piso y vuelve a tardar más que la inexistente (N-7).

- Medición del 2026-10-22 (S2-B2), dentro del contenedor `api` (script desechable copiado con
  `docker cp` y corrido con `docker exec -w /app apex-api-1 python`: `verify_password` en un
  hilo con los parámetros de `Settings` y luego un `UPDATE` de una fila de `auth.users` con
  commit; 30 muestras por corrida tras 2 de calentamiento): medianas de 47,8, 46,6 y 58,8 ms.
  De ahí salió el primer valor, 75 ms (1,5 veces la mediana).
- Revisión de Fase 4 del Sprint 2 (N-7): el piso sube a 150 ms, por encima del p99 esperado
  bajo contención (V5: 20 logins fallidos concurrentes con p95 de 0,399 s de extremo a extremo,
  donde manda la cola de argon2 y no el piso). El backend cambia el valor por defecto en
  `Settings` y `.env.example` en esta misma revisión.

Remedir el p99 (no la mediana) si cambian los parámetros de argon2 o el hardware del servidor,
con carga concurrente, y ajustar `LOGIN_MIN_DURATION_MS` en `.env`.

### Cookie sin TLS (riesgo aceptado P7)

En v0.1 el gimnasio corre en la LAN sin TLS. Con `ENV=production` el api no arranca con
`COOKIE_SECURE=false` salvo que `ALLOW_INSECURE_COOKIE=true` lo autorice de forma explícita
(M-9). Ponerla en `true` es aceptar que la contraseña y la cookie del refresh viajan en claro
por la red local; se quita al activar TLS (v0.3) junto con `COOKIE_SECURE=true`.

### Fallos de Nginx hacia el api (`error_log crit`, M8)

`infra/nginx/default.conf` tiene `error_log /dev/stderr crit`: desde el nivel `error`, Nginx
escribe la línea de la petición con su query string (tokens, búsquedas) y eso no puede llegar
al log (S2-W0-1). El costo es que `docker logs apex-web-1` **no** muestra
`connect() failed`, `upstream timed out` ni `no live upstreams` cuando el api cae. Ante 502 o
504 en el panel:

1. Access log de Nginx: `docker logs --tail 50 apex-web-1 | grep '"status":50[24]'`. Un
   `"upstream_time":"-"` o vacío es que no hubo conexión con el api.
2. Estado y log del api: `$DC ps api` (debe estar `healthy`) y `$DC logs --tail 100 api`.
3. Conexión desde Nginx: `docker exec apex-web-1 wget -qO- http://api:8000/health`.
4. Solo si lo anterior no alcanza y en una ventana corta: bajar el nivel dentro del contenedor
   con `docker exec apex-web-1 sed -i 's#error_log /dev/stderr crit;#error_log /dev/stderr error;#' /etc/nginx/conf.d/default.conf`
   y `docker exec apex-web-1 nginx -s reload`, reproducir el fallo y volver a la imagen con
   `$DC up -d --force-recreate web`. Mientras dure, el log puede traer tokens o búsquedas: no
   copiarlo a ningún lado y descartarlo.

## 2. Cuentas

### Primer admin

`ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` van en `.env.seed` (solo lo lee el servicio `tools`):
`$DC run --rm tools seed`. El admin sembrado debe cambiar la contraseña al entrar
(`must_change_password`); `--no-force-change` solo se acepta con `ENV=dev`. Una segunda corrida
dice "omitido". Borrar `.env.seed` después del primer seed; la contraseña queda en el gestor de
contraseñas del operador y, si se pierde, se recupera sin el archivo (sección 8). Tras cambiar `cli.py` hay que
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
$DC run --rm tools unlock-user <correo de la cuenta> --as <correo de un admin activo>
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
- El correo de otro admin activo no se cambia desde el panel (L-13 aplicado al cambio de
  correo, N-8): responde 409, la misma regla que "Reenviar enlace". Si no, un admin podría
  poner su propio correo en la cuenta de otro y tomarla con la recuperación cuando `forgot`
  envíe correos (US-131). Implementado en la revisión de Fase 4 del Sprint 2 (S2-R3): el 409 es
  `user_not_eligible`; el propio admin sí puede cambiar su correo, y el de un admin pendiente
  de activación o bloqueado también se puede corregir (su enlace abierto se cierra).

- **`Cache-Control: no-store` duplicada.** Las rutas autenticadas la envían desde el api
  (`core/http.no_store`) y Nginx la vuelve a poner en `/api/` (`proxy-api.conf`). Son el mismo
  valor; no tiene efecto y no hay que "corregirlo" quitando una de las dos.

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
- Un documento repetido entre socios no dados de baja responde 409 `member_document_duplicated` con `existing_id`; el único parcial `uq_members_document_idx_alive` decide aunque dos altas lleguen a la vez. Un socio dado de baja (US-076, S3-B10) libera su documento: se puede dar de alta a otro con el mismo.
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
- Pruebas de rendimiento (marcador `perf`; 1.000 socios, búsqueda por documento bajo 500 ms con `EXPLAIN` del único parcial, y L-11 de 20 logins fallidos concurrentes con p95 bajo 2 s): `cd api && uv run pytest -m perf -q -s` (con `TEST_DATABASE_URL`). No son gate (S2-D27, revisión de Fase 4): `run-gates.sh` y el job `api` de la CI corren `-m "not perf"`, y la CI las corre en un paso aparte que informa sin bloquear (`continue-on-error`, 10 minutos). Se corrieron en el gate de B8 y en V5.

### Filtros por membresía y ficha del socio (S3-B9b, US-071 y US-073)

- `GET /api/v1/members` acepta además `membership_status` (`active`, `expiring`, `expired`, `frozen`, `pending_payment` o `none`) y `plan_id` (UUID; un plan inexistente da la lista vacía). El estado es el de la membresía que decide (la vigente antes que la futura, igual que `GET /memberships`); `plan_id` filtra por el plan de esa membresía y nunca encuentra socios sin membresía, así que `membership_status=none` con `plan_id` responde la página vacía sin consultar. Se combinan con `q`, `status`, `sort` y la paginación. El conjunto de ids lo resuelve `memberships` y viaja como un solo parámetro `uuid[]` (`= ANY` o, para `none`, `<> ALL`): 5.000 socios con membresía no expanden un `IN`. Los filtros sin `q` no gastan la cubeta de búsquedas y no descifran nada.
- Cada fila trae `membership_status` (`none` si no tiene membresía), `plan_name` y `membership_end_date` (la columna "Vence"); son datos comerciales en claro. La página se decora con una sola consulta de estados por página.
- `GET /api/v1/members/{member_id}` (admin y coach, también sobre un socio dado de baja) devuelve la ficha con los cinco campos sensibles enmascarados en memoria (`CC •••• 4417`, `••• ••• 4321`, `l•••@•••.co`, `••/••/1991`, `Registrado`) y el estado, plan y fin de su membresía. Para enmascarar, el api descifra en memoria: cada ficha deja en `crypto.crypto_ops` una fila `decrypt` con `purpose = 'mask'` por campo cifrado no nulo (cinco si el socio tiene todos), con el `record_id` del socio y quien la abrió como `user_id`, sin lote. Una ficha no escribe en `audit.audit_log` y no deja ninguna fila con `purpose = 'reveal'`: ver un dato completo llega con S3-B10.
- Verificar con psql tras abrir una ficha: `SELECT verb, purpose, count(*) FROM crypto.crypto_ops WHERE record_id = '<id>' GROUP BY 1, 2;` da `decrypt | mask | 5` (más las filas `encrypt` e `index` del alta) y `SELECT count(*) FROM audit.audit_log WHERE action = 'reveal';` sigue en 0.
- Límite: 120 fichas por minuto por usuario (`USER_DETAIL_LIMIT_PER_MIN`, cubeta `members-detail`, M-2; 429 `rate_limited` con `Retry-After`). Un 404 también cuenta (el límite va antes de buscar al socio), la lista del mismo usuario no se afecta y el contador vive en memoria (se limpia con `up -d api`).

### Revelar, editar, dar de baja y reactivar (S3-B10, US-074 a US-076)

- **Revelar un dato (`POST /api/v1/members/{member_id}/reveal`, admin y coach, también sobre un dado de baja).** Cuerpo `{"field": "document" | "phone" | "email" | "birth_date" | "emergency_contact"}` (otro campo da 422 con `field="field"`). Responde `{field, value}` con el valor en claro (la fecha como `AAAA-MM-DD`, el contacto como objeto, `null` si el campo está vacío) y `Cache-Control: no-store`. Cada llamada deja, en la misma transacción, una fila `reveal` en `audit.audit_log` (`after = {"field": ..., "ip": ...}`, nunca el valor; `user_id` es quien reveló y `subject_member_id` el socio) y una fila `decrypt` con `purpose = 'reveal'` en `crypto.crypto_ops` (un campo vacío audita igual y no descifra). Si la auditoría no se puede escribir, la petición responde 500 y el valor no sale; la fila `decrypt` queda igual (prueba de que se descifró).
- **Los tres cupos de `reveal`, por usuario:** 30 por minuto (`USER_REVEAL_LIMIT_PER_MIN`, cubeta `members-reveal`), 200 por hora (`USER_REVEAL_LIMIT_PER_HOUR`, `members-reveal-hour`) y 600 por día (`USER_REVEAL_LIMIT_PER_DAY`, `members-reveal-day`). El que se agota responde 429 `rate_limited` con `Retry-After`, y el registro `rate limit` nombra la cubeta (nunca el usuario). Los contadores viven en la memoria del proceso: valen porque el api corre en un solo proceso (sin `--workers`, sección 1); si algún día se corre con varios, cada uno tendría su propio cupo y habría que mover el contador a un almacén compartido. `up -d api` los limpia. Un 404 también cuenta.
- **Qué significa `reveal volume` en el log:** un `WARNING` con `user_id` y `count` cuando una persona pasa de la mitad de su cupo horario (con el tope de 200, desde la revelación 101 dentro de la misma hora). No lleva el socio ni el valor. Es una señal temprana de uso anómalo (una cuenta comprometida o alguien copiando la base): revisar `SELECT seq, at, record_id, after FROM audit.audit_log WHERE action = 'reveal' AND user_id = '<user_id>' ORDER BY seq DESC LIMIT 50;` y, si no se explica, bloquear la cuenta (`POST /users/{id}/lock`, sección 2, "Bloquear, cerrar sesiones y dar de baja"): corta sus sesiones y sus access en la siguiente petición.
- **Editar (`PATCH /api/v1/members/{member_id}`, admin y coach).** Solo los diez campos de `MemberPatch` (`first_name`, `last_name`, `sex`, `birth_date`, `phone`, `email`, `emergency_contact`, `document`, `document_type`, `data_consent`); `status`, `deleted_at` o `data_consent_at` en el cuerpo dan 422. `null` vacía `sex`, `phone`, `email`, `birth_date` y `emergency_contact`. El documento y su tipo son solo del admin: un coach que los envía, aunque sea el mismo valor, recibe 403 `forbidden_field`. Un documento de otro socio vivo da 409 `member_document_duplicated` con `existing_id`; editar a un dado de baja da 409 `member_deactivated` (hay que reactivarlo primero). `data_consent: true` fija la fecha de autorización solo si no la había; `false` da 422 `consent_cannot_be_withdrawn` (retirar la autorización es otro proceso). Solo se recifran los campos que cambian (nonce nuevo, índice ciego recalculado); un cambio solo de formato (`300 123 4567` frente a `3001234567`) no cuenta, y un PATCH sin cambios no escribe, no audita y no emite. La fila `update` de la auditoría lleva solo las columnas cambiadas, los blobs y los índices como `***`. Comparte el cupo `members-write` (60 por minuto) con el alta.
- **Dar de baja (`DELETE /api/v1/members/{member_id}`, solo admin):** 204; la fila sigue con `deleted_at` (UTC) y `status = 'inactive'`, auditada como `update`. Sale de la lista por defecto y de las búsquedas, aparece con `status=deleted`, su ficha y sus datos se pueden ver y revelar, y libera su documento. Sus membresías y pagos no cambian; una venta posterior sobre él responde 422 `member_inactive`. Una baja repetida da 409 `member_already_deactivated`.
- **Recuperar a un socio dado de baja (`POST /api/v1/members/{member_id}/reactivate`, solo admin):** 200 con la ficha; vuelve a `active` con `deleted_at` nulo (auditado como `update`). Si mientras tanto se dio de alta a otro socio vivo con el mismo documento, responde 409 `member_document_duplicated` con su `existing_id` y el socio sigue dado de baja: decidir cuál de los dos es el real, dar de baja el duplicado (y pasarle sus membresías a mano si hiciera falta) y reactivar. Sobre un socio vivo da 409 `member_not_deactivated`. Encontrar el id: `GET /api/v1/members?status=deleted&q=<nombre o documento>`.
- **Límite de baja y reactivación:** las dos consumen la cubeta por usuario `admin-write` (30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`), la misma de anular un pago y anular una membresía; la 31 del minuto responde 429 `rate_limited` con `Retry-After` (L1 de la revisión de Fase 4 del Sprint 3).
- **Concurrencia:** editar, dar de baja y reactivar toman primero el candado del socio (`lock_member`, el mismo de vender, congelar y pagar), así una venta y una baja simultáneas no dejan una membresía nueva sobre un dado de baja. Si la espera supera `lock_timeout`, 503 `busy` (sección 9).
- **Verificar con psql tras una revelación:** `SELECT action, after FROM audit.audit_log WHERE record_id = '<id>' AND action = 'reveal' ORDER BY seq DESC LIMIT 1;` da `{"field": ..., "ip": ...}` y `SELECT verb, purpose FROM crypto.crypto_ops WHERE record_id = '<id>' AND purpose = 'reveal';` una fila `decrypt | reveal` por revelación de un campo no vacío.

### Pestañas de la ficha: membresías y pagos (S3-B11, US-093 y US-101)

- **`GET /api/v1/members/{member_id}/memberships` (admin y coach, también sobre un socio dado de baja).** Página de `MembershipOut` de ese socio con `limit` (1 a 200), `offset` y `q`. Incluye las anuladas; orden `start_date` descendente y, en empate, `id`. Cada fila trae sus congelaciones, `paid_cop` (suma de los pagos no anulados) y el estado EFECTIVO (el mismo de `GET /memberships/{id}`: una `active` vencida sale `expired`, una congelada hoy sale `frozen`). `q` filtra por el nombre del plan sin tildes ni mayúsculas, incluidos los planes dados de baja (`Mensual` encuentra "Mensual Ilimitado"); si ningún plan coincide, la página sale vacía sin más consultas.
- **`GET /api/v1/members/{member_id}/payments` (admin y coach, también sobre un dado de baja).** Página de `PaymentRow` de ese socio con `limit`, `offset`, `q` y `voided` (`true`, `false` o ausente para todos). Orden `paid_at` descendente y, en empate, `id` descendente. `q` es la referencia COMPLETA sin distinguir mayúsculas (`nq-123` encuentra `NQ-123`; `NQ` no encuentra nada): en esta pestaña `q` nunca busca personas. Cada fila lleva `backdated` y el correo de quien registró en forma parcial, como `GET /payments`.
- **Errores:** socio inexistente 404 `member_not_found` (también con `q`: el 404 gana); `limit` fuera de 1 a 200, `offset` negativo, `q` de más de 100 caracteres o con controles, `voided` no booleano o `member_id` que no es UUID dan 422 con `field`; el rol `member` 403; sin sesión 401.
- **Sin cupo propio:** ninguna de las dos lleva límite por usuario ni responde 429 (D28). `q` no toca datos de personas (nombre de plan o referencia de pago), así que no gasta la cubeta de búsquedas de `GET /members` (60 por minuto, ver "Búsqueda y listado"). Ninguna descifra ni calcula índices ciegos: abrir las pestañas no deja filas en `crypto.crypto_ops`. Las dos responden `Cache-Control: no-store`.
- **Costo:** cada página hace un número fijo de sentencias (el socio, la página y el total, y una por vecino: nombres de socios y planes, sumas de pagos y congelaciones, o los datos de quien registró), sin importar cuántas filas tenga.
- **Verificar con psql:** `SELECT count(*) FROM memberships.memberships WHERE member_id = '<id>';` y `SELECT count(*) FROM payments.payments WHERE member_id = '<id>';` coinciden con el `total` de cada pestaña sin `q` (y, para pagos, `... AND NOT voided` con `voided=false`).

### Historial de la ficha (S4A-B5, US-106; S4A-D20, S4A-D109 a S4A-D111)

- **`GET /api/v1/members/{member_id}/audit` (admin y coach, también sobre un socio dado de baja).** Página de `MemberHistoryItem` con `limit` (1 a 200), `offset` (hasta 100.000) y `q`, en `seq` descendente. Trae las entradas de `audit.audit_log` cuyo `subject_member_id` es el socio: altas, ediciones, revelaciones y bajas de la ficha, y las ventas, activaciones, congelaciones, anulaciones y pagos de sus membresías. Responde `Cache-Control: no-store`.
- **Qué ve el coach (lo mismo que el admin).** Cada fila trae `seq`, `at`, `user_id`, `user_name` (la parte local del correo de quien actuó, o `Sistema`; nunca el correo completo), `action`, `table_name`, `record_id`, `fields` y `purpose`. `fields` son solo NOMBRES de campo, nunca valores: en una edición, las columnas que cambiaron (sin `*_idx`, `created_at` ni `updated_at`); en una revelación, el campo revelado (nunca la IP); en altas y bajas físicas, vacío. De los pagos jamás salen `reference` ni `void_reason`, ni siquiera el nombre: una anulación se ve como `voided`, `voided_at` y `voided_by`. El detalle con valores sigue siendo solo del admin en `GET /audit/{seq}`.
- **`purpose`.** Solo en una revelación automática: `notify` (el sistema descifró el contacto para avisar al socio) o `auth_link` (para un enlace de cuenta). En una revelación hecha por una persona desde la ficha es `null`; en cualquier otra acción también.
- **Por qué una congelación aparece por la membresía.** La fila de `memberships.membership_freezes` no lleva `subject_member_id` (es append-only y su dueño es la membresía), así que no sale en el historial. La congelación se ve por el `update` de `memberships.memberships` que la acompaña, con `fields` `["end_date", "status"]` y `record_id` de la membresía.
- **`q`.** Filtra por la parte local del correo de quien actuó, sin tildes ni mayúsculas (`PÉREZ` encuentra `ana.perez`); nunca por el dominio (`ejemplo` no encuentra nada). Si nadie coincide, la página sale vacía con `total` 0.
- **Errores y límites:** socio inexistente 404 `member_not_found` (gana sobre un `offset` fuera de rango); `offset` mayor que 100.000 da 422 con `field="offset"`; `limit` fuera de rango, `offset` negativo, `q` con controles o `member_id` que no es UUID dan 422 con `field`; el rol `member` 403; sin sesión 401. Consume `staff-read` (120 lecturas por minuto por usuario, compartida con `GET /audit`, `GET /audit/{seq}` y el tablero): la 121.ª da 429 con `Retry-After`. El `total` se satura en 100.001, como en `GET /audit`.
- **Solo lee:** abrir el historial no escribe en `audit.audit_log` ni en `crypto.crypto_ops`, y no descifra nada.
- **Verificar con psql:** `SELECT seq, action, table_name FROM audit.audit_log WHERE subject_member_id = '<id>' ORDER BY seq DESC LIMIT 25;` coincide con la primera página sin `q`.

### Contacto para avisos (S4A-B6, US-077; S4A-D21, S4A-D50, S4A-D113)

- **`members.service.contact_for_notification(session, member_id, purpose)`.** Devuelve un `Contact` con el nombre, el teléfono y el correo en claro del socio para mandarle un aviso. No es una ruta: no hay endpoint que la exponga. El `repr` y el `str` del `Contact` nunca muestran el teléfono ni el correo; quien lo recibe no lo guarda, no lo escribe en logs y no lo serializa: `pickle`, `copy`, `deepcopy`, `vars` y `json.dumps` sin ayuda lanzan `TypeError`, y `dataclasses.asdict`/`astuple` no se usan con él.
- **Quién puede llamarla.** En el Sprint 4A, nadie fuera de `members` (`CONTACT_CALLERS` vacío en `tests/architecture/test_contact_callers.py`). El Sprint 5 agrega `notifications.service` a `CONTACT_CALLERS`, y solo ese módulo.
- **Propósitos.** Solo `notify` (aviso al socio) y `auth_link` (enlace de cuenta), exactos: `NOTIFY`, ` notify`, `mask`, `reveal`, `export` o vacío dan `InvalidPurpose` antes de leer la base. Un socio inexistente o dado de baja da `MemberNotContactable` sin descifrar ni auditar.
- **Rastro.** Por cada campo no vacío (teléfono, correo): una fila `decrypt` en `crypto.crypto_ops` con el `purpose`, el `record_id` del socio, `count = 1` y el `batch_id` del lote del llamador, y una fila `reveal` en `audit.audit_log` con `after = {"field", "purpose"}` (nunca el valor ni la IP), `record_id` y `subject_member_id` del socio. El historial de la ficha la muestra con `purpose` `notify` o `auth_link`. Un campo vacío sale `None` y no deja filas.
- **Regla de composición.** No pide `lock_member` ni candados de fila (no escribe en `members`), pero la primera fila de auditoría toma el candado de la cadena. Una llamada por socio: en una transacción propia, o después de `lock_member` del mismo socio y antes de otras escrituras que pidan candados; nunca en un bucle sobre varios socios en la misma transacción. Quien la llama confirma la transacción antes de enviar el aviso: un rollback borra las filas `reveal` pero no las `decrypt` (`oplog` las escribe en otra conexión).
- **Verificar con psql:** `SELECT verb, purpose, count, batch_id FROM crypto.crypto_ops WHERE record_id = '<id>' AND purpose IN ('notify', 'auth_link');` y `SELECT action, after FROM audit.audit_log WHERE subject_member_id = '<id>' AND action = 'reveal' AND after ? 'purpose';` dan una fila por campo y llamada.

## 5. Planes (S2-B9)

- `POST /api/v1/plans` solo lo usa el admin. El nombre es único entre los planes no dados de baja sin distinguir mayúsculas ni espacios de los extremos: con "Mensual" creado, "mensual" o "  MENSUAL  " dan 409 `plan_name_duplicated` con `existing_id` (índice `uq_plans_name_alive` sobre `lower(btrim(name))`). Dar de baja un plan (Sprint 4A) libera el nombre.
- Tipos: `days` (sin `class_count`) y `classes` (con `class_count` de 1 a 1.000). Topes: precio de 1 a 1.000.000.000 COP (entero), duración de 1 a 3.650 días. La base repite las reglas por CHECK (`\d plans.plans`).
- Alcance del coach: `GET /api/v1/plans?active=true` y `GET /api/v1/plans/{id}` de planes activos; sin `active=true` o sobre un plan inactivo recibe 403 `forbidden`. El admin ve activos e inactivos. Los dados de baja no aparecen nunca (404 en el detalle).
- La búsqueda `q` no distingue mayúsculas ni tildes. En todas las listas (`/users`, `/members`, `/plans`) un `q` con caracteres de control (por ejemplo `%00`) da 422 con `field="q"`.

### Editar, activar o desactivar y dar de baja (S4A-B7, US-080 a US-082)

- Las cuatro escrituras son solo del admin y comparten la cubeta `admin-write` con `POST /plans` (30 por minuto; la 31 da 429). Las cuatro toman el plan con `SELECT ... FOR UPDATE`: dos cambios del mismo plan se serializan.
- Editar: `PATCH /api/v1/plans/{id}` con solo los campos que cambian (`name`, `price_cop`, `kind`, `duration_days`, `class_count`). `is_active` o `deleted_at` en el cuerpo dan 422. Pasar a `classes` exige `class_count`; pasar a `days` exige `class_count: null` explícito (si no, 422 con `field="class_count"`). Un nombre de otro plan vivo da 409 `plan_name_duplicated` con `existing_id`; el propio nombre con otras mayúsculas no cuenta como repetido. Sin cambios efectivos responde 200 sin tocar la fila, sin auditoría y sin evento.
- Cambiar el precio no toca las membresías ya vendidas: guardan su `agreed_price_cop` (y `guard_identity` impide cambiarlo por SQL). Una venta posterior cobra el precio vigente al vender (S4A-D60, riesgo aceptado: no hay `version` ni `expected_price_cop`).
- Activar o desactivar: `POST /api/v1/plans/{id}/activate` y `/deactivate`, idempotentes (repetir no audita ni emite). Un plan inactivo no se vende (422 `plan_inactive`), sigue en la lista del admin con `active=false` y sus membresías no cambian.
- Dar de baja: `DELETE /api/v1/plans/{id}` → 204 con `deleted_at` (hora del reloj de la app) e `is_active` falso en una sola fila `update` de la auditoría. Si el plan tiene membresías activas por estado efectivo (todo menos `cancelled` y `expired`, incluidas `pending_payment` y `frozen`) responde 409 `plan_has_active_memberships` con solo el conteo ("1 membresía activa" o "N membresías activas"), sin ids ni nombres: se desactiva en su lugar, o se anulan antes las `pending_payment` con `POST /memberships/{id}/cancel`. Un plan dado de baja da 404 en todas las rutas y libera su nombre.
- La columna "Socios con él" es `active_members_count` de `GET /plans` y `GET /plans/{id}`: el mismo conteo, en una sola consulta a `memberships.memberships` por página.

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
- **`0008_memberships`:** `downgrade 0007_plans` borra los tres triggers, las dos funciones, los índices y `memberships.memberships` (con sus filas: antes, el volcado de la sección 10). El esquema `memberships` y `btree_gist` quedan. Se revierte el checkpoint de S3-B1 (y los posteriores que usen la tabla). La auditoría de las ventas queda en `audit.audit_log` (append-only).
- **`0009_membership_freezes`:** `downgrade 0008_memberships` borra los dos triggers, la función `memberships.forbid_freeze_mutation()`, el índice y `memberships.membership_freezes` (con sus filas: antes, el volcado de la sección 10). Las membresías conservan el `end_date` ya corrido y el `status` guardado; sin la tabla, `compute_status` deja de ver las ventanas (una `frozen` guardada se lee por fecha). Quedan `memberships.memberships`, sus dos funciones, el esquema y `btree_gist`. Se revierte el checkpoint de S3-B2. La auditoría de las congelaciones queda en `audit.audit_log`.
- **`0012_worker_job_runs` (S4A-B1):** crea `worker.job_runs` (una fila por job y día de Bogotá; CHECKs `ck_job_runs_job_name_shape`, `ck_job_runs_result` y `ck_job_runs_finished_after_started`; sin triggers). `downgrade 0011_payments_immutability` borra los dos índices (`uq_job_runs_name_date`, `ix_job_runs_name_started`) y `worker.job_runs`; nunca el esquema `worker` (es de `0001`). Solo se pierde la bitácora de corridas del worker. Antes: `$DC stop worker` (enmienda E4: todo `downgrade` que borre `worker.job_runs` exige parar el worker antes y `$DC start worker` después, con `healthy` y `RestartCount` anotados). Se revierte el checkpoint de S4A-B1 (y W0-2 y B2 si existen).
- **`0013_audit_verifications` (S4A-B3):** crea `audit.verifications` (una fila por verificación terminada; CHECKs `ck_verifications_through_seq_non_negative`, `_rows_checked_non_negative`, `_source`, `_ok_matches_broken`, `_finished_after_started` y `_through_hash_shape`; índice `ix_verifications_finished_at (finished_at DESC)`; triggers `verifications_forbid_mutation` y `verifications_forbid_truncate` sobre la función existente `audit.forbid_mutation()`, los dos con `ENABLE ALWAYS`). `downgrade 0012_worker_job_runs` quita los dos triggers, el índice y la tabla, y con ella el ancla `through_hash` de la última verificación `ok`: antes, el volcado de P-MIG y la copia de la última línea `audit anchor` del log. Nunca borra `audit.forbid_mutation()` (la usa `audit.audit_log`) y las filas `verify` de la cadena se quedan (la cadena es inmutable). No toca `worker.job_runs`: no hace falta parar el worker (enmienda E4). Se revierte el checkpoint de S4A-B3.
- En CI y `db_test` no hace falta rollback: `migrated_database` vuelve a migrar desde cero.

## 7. Imágenes base por digest y su renovación (S3-D62)

Toda imagen base va como `imagen:tag@sha256:<digest>`, con un comentario en la línea de arriba que lleva la fecha de la consulta y el comando de renovación. El tag queda como referencia legible; Docker usa el digest. Lo vigila `scripts/ci/test_images_pinned.sh` (grep puro, sin Docker), que corre en `run-gates.sh` y en el job `scripts` de la CI: falla si un `FROM`, un `image:` (salvo `apex-*:local`) o la imagen de `test_nginx_conf.sh` no lleva `@sha256:` de 64 caracteres hexadecimales o no tiene el comentario con la fecha.

Dónde están:
- `api/Dockerfile`: `python:3.12-slim` (dos `FROM`: `builder` y `runtime`).
- `web/Dockerfile`: `node:22-alpine` (`build`) y `nginx:stable-alpine` (imagen final).
- `infra/compose.yml` (`db`) e `infra/compose.dev.yml` (`db_test`): `postgres:16`.
- `scripts/ci/test_nginx_conf.sh`: `nginx:stable-alpine` (contenedor desechable de la prueba funcional).
- `.github/workflows/ci.yml`: el servicio `postgres:16` del job `api` (desde la revisión de Fase 4 del Sprint 2, L3).

Renovación: a mano al abrir cada sprint (sin Dependabot para Docker en este repositorio).
1. Consultar el digest actual de cada imagen:
   ```
   docker buildx imagetools inspect python:3.12-slim --format '{{json .Manifest.Digest}}'
   docker buildx imagetools inspect node:22-alpine --format '{{json .Manifest.Digest}}'
   docker buildx imagetools inspect nginx:stable-alpine --format '{{json .Manifest.Digest}}'
   docker buildx imagetools inspect postgres:16 --format '{{json .Manifest.Digest}}'
   ```
   El digest es el del índice multiplataforma, el mismo que resuelve `docker pull imagen:tag`.
2. Reemplazar el digest y la fecha del comentario en cada sitio de la lista (`postgres:16` en los dos Compose y en `ci.yml` va con el mismo digest).
3. `bash scripts/ci/test_images_pinned.sh`, `bash scripts/ci/test_compose_config.sh` y `bash scripts/ci/test_nginx_conf.sh`.
4. Reconstruir y levantar: `$DC build api web && $DC up -d` (en este equipo, ver la nota de `network: host` abajo); esperar los servicios `healthy` y correr `bash scripts/smoke/headers.sh` y `bash scripts/ci/web-smoke.sh`.
5. Anotar los digests nuevos en el cuaderno del sprint.

Cambiar `postgres:16` a otro digest de la misma mayor no toca los datos del volumen `apex_pgdata`; cambiar de mayor (17) exige `pg_dump` y restauración, y no se hace en una renovación.

Nota de este equipo (Docker Desktop con Compose 5.6 y buildx 0.38, 22 de octubre de 2026): `compose.dev.yml` pide `build.network: host` y Compose construye con `buildx bake`, que ahora exige el permiso `network.host` y Compose no lo pasa (`additional privileges requested: pass "--allow=network.host"`). Mientras Compose no lo resuelva, se construye con buildx directo y se levanta sin construir:
```
docker buildx build --load --network host --allow network.host -t apex-api:local -f api/Dockerfile api
docker buildx build --load --network host --allow network.host -t apex-web:local -f web/Dockerfile .
$DC up -d --no-build
```
`apex-api:local` la usan `api`, `worker` y `tools`: tras reconstruirla, `$DC up -d --no-build` recrea `api` y `worker` (`tools` corre con `run --rm` y toma la imagen nueva en la siguiente invocación). Comprobación del worker en §9, "Worker".
En la CI (Linux, sin `compose.dev.yml`) no aplica.

## 8. Primer admin sin `.env.seed` (S3-D64)

`.env.seed` solo existe para el primer `seed` (sección 2) y se borra después: las credenciales del admin no se quedan en disco. Estado desde S3-W0-1 en el equipo de desarrollo: el archivo está borrado, el admin sigue en la base y su contraseña vive en el gestor de contraseñas del operador.

- Pruebas E2E del proyecto `stack` y smoke con sesión: exportar `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` en la shell de la sesión desde el gestor (nunca a un archivo del repositorio, al cuaderno ni a un log). `datosDeBase()` de `web/tests/e2e/helpers/stack.ts` las lee del entorno.
- Si la contraseña se pierde: `$DC run --rm tools issue-reset-link <correo del admin> --as <correo del admin>` (sección 2, "Recuperar a un admin"). No necesita la contraseña ni el `.env.seed`: imprime una sola vez el enlace de restablecimiento de 1 h; se abre, se fija la contraseña nueva y se guarda en el gestor. Si el admin está bloqueado, primero `cli unlock-user`.
- Si no queda ningún admin activo: `seed` con un `.env.seed` nuevo y efímero (sección 2), y se borra al terminar.
- En la CI el job `e2e-stack` crea un `.env.seed` efímero con contraseña aleatoria y lo descarta con el runner.

## 9. Tiempos de espera de la base y 503 `busy` (S3-W0-2)

Una transacción detenida (un `psql` de soporte con `BEGIN` abierto, una sentencia que no termina) congela todas las escrituras auditadas: cada una pide el candado de la cadena de auditoría (`pg_advisory_xact_lock(4270002)`, `core/audit.py`) y esperaría sin fin. Los tres tiempos de espera acotan esa espera (H-3, S3-D43) y la respuesta es un 503 `busy` corto, no un 500 ni un cuelgue (S3-D67).

### Qué hace cada tiempo de espera

`create_engine_from` (`core/db.py`) los pasa como `server_settings` de asyncpg a cada conexión del pool; valen para toda sentencia del api, del CLI y del worker:
- `DB_LOCK_TIMEOUT_MS` (10.000, `lock_timeout`): máximo que una sentencia espera un candado (fila con `FOR UPDATE`, tabla, candado asesor). Agotado: SQLSTATE `55P03`.
- `DB_STATEMENT_TIMEOUT_MS` (30.000, `statement_timeout`): máximo que dura una sentencia. Agotado: `57014`.
- `DB_IDLE_IN_TX_TIMEOUT_MS` (60.000, `idle_in_transaction_session_timeout`): una conexión que deja una transacción abierta sin hacer nada más de ese tiempo es cerrada por PostgreSQL y sus candados se liberan. El pool la descarta (`pool_pre_ping`).
- Un deadlock (`40P01`) también se responde como `busy`.
- Rango: de `0` a `2147483647` (el máximo de PostgreSQL; fuera de él `Settings` no arranca). `0` desactiva el tiempo correspondiente. Con `ENV=production` el piso es 1.000 ms (S3-D79, `DB_TIMEOUT_FLOOR_MS`): un `.env` de producción con `0` o menos de 1.000 hace que el api no arranque (`ConfigError` con el nombre de la variable). El CLI con `--db-timeouts off` los pone en `0` sobre una copia ya validada del `Settings` (`model_copy`), así que sigue funcionando en producción.

Un `psql` de soporte no los hereda (su conexión no pasa por `create_engine_from`): `SHOW lock_timeout` ahí da `0`. Los del api los comprueba `tests/core/test_db_timeouts.py` (`SHOW lock_timeout` = `10s` sobre un engine de `create_engine_from`).

### Cómo se ve un 503 `busy`

- Respuesta: `503` con `{"error": {"code": "busy", "message": "La base de datos está ocupada; intenta de nuevo en un momento."}}`, `Retry-After: 1` y `Cache-Control: no-store`. El front lo trata como cualquier 5xx: reintentar en un momento.
- La traduce `get_session` (el `try` abarca también el commit, E7) a `DatabaseBusy`, que responde `_handler_dominio`: en el log salen un `WARNING` `db busy` del logger `app.db` con solo el campo `sqlstate` (`55P03`, `57014` o `40P01`; nunca la sentencia ni sus parámetros) y la línea de acceso con `status` 503, **sin** traza ni registro de nivel `ERROR`. Un `500 internal_error` con traza sigue siendo un fallo real del api, nunca una espera agotada.
- Buscar en los logs: `$DC logs --since 10m api | grep 'db busy'` (el `sqlstate` dice si fue candado, sentencia larga o deadlock) o `grep '"status": 503'` (línea `http_request`, con la ruta). Las rutas públicas con sesión (login, refresh, logout, forgot, reset) también pueden responder 503 `busy` aunque el contrato no lo declare (E16, riesgo aceptado).

### Qué hacer si se repite

1. Buscar quién retiene el candado:
   ```
   $DC exec -T db psql -U apex -d apex -c "SELECT pid, usename, application_name, state, wait_event_type, wait_event, now() - xact_start AS en_tx, left(query, 80) AS query FROM pg_stat_activity WHERE datname = 'apex' ORDER BY xact_start NULLS LAST"
   ```
   Las que esperan aparecen con `wait_event_type = 'Lock'`; la que bloquea suele estar `idle in transaction` o con un `xact_start` viejo. Para ver quién bloquea a quién: `SELECT pid, pg_blocking_pids(pid) FROM pg_stat_activity WHERE wait_event_type = 'Lock'`.
2. Si la bloqueante es una sesión de soporte (un `psql` olvidado), cerrarla desde su terminal con `ROLLBACK`; si no hay acceso a ella, `SELECT pg_terminate_backend(<pid>)` sobre ese `pid` (solo la de soporte; nunca la de una migración en curso). `idle_in_transaction_session_timeout` la cierra igual a los 60 s.
3. Si la bloqueante es una sentencia del api que no termina, `statement_timeout` la corta a los 30 s; si se repite, revisar la consulta (plan, índice) antes de subir el valor.
4. No subir `DB_LOCK_TIMEOUT_MS` para "arreglar" un 503 repetido: se esconde la causa y el api vuelve a colgarse.

### Worker (US-113, Sprint 4A; S4A-B1, S4A-W0-2 completa la activación)

- Servicio `worker` de `infra/compose.yml`: misma imagen que el api, `command: ["python", "-m", "app.worker.main"]`, sin volúmenes (ni `keys` ni `uploads` hasta el Sprint 5), raíz de solo lectura con `/tmp` en memoria, `cap_drop: ALL` y `no-new-privileges` (S4A-D49). Arranca después de `db` y `api` `healthy` (el api aplica las migraciones). Desde S4A-W0-2 no tiene perfil: `$DC up -d` lo arranca con el resto del stack (también el `up -d --build` del job `e2e-stack` de la CI, que no lo espera: las E2E no lo usan), y `scripts/ci/compose-smoke.sh` exige `healthy`, 0 reinicios tras 30 s, `--run-once expirations` dos veces y la misma fila en las dos `--status`.
- Arranque y comprobación tras cambiar la imagen (S4A-W0-2, S4A-D42): el worker usa `apex-api:local`, así que la imagen se reconstruye con buildx (nota de §7) y `$DC up -d --no-build` recrea `api` y `worker`. Esperar los dos `healthy` (`$DC ps`), `docker inspect -f '{{.RestartCount}}' apex-worker-1` en 0 pasados 30 s y `$DC logs --tail 30 worker` con `Scheduler started` y `worker started` (`timezone` `America/Bogota`); `database not ready` mientras la base no responde es normal. Edad del latido: `docker exec apex-worker-1 python -c "import os, time; print(time.time() - os.path.getmtime('/tmp/apex-worker-heartbeat'))"` (en Git Bash con `MSYS_NO_PATHCONV=1`), menos de 30 s en marcha normal.
- Si queda `unhealthy`: `$DC logs --tail 50 worker` (`database not ready` = la base no responde: revisar `db`; `worker cycle failed` o `worker recovery failed` traen el tipo del error), edad del latido como arriba, y `$DC restart worker` cuando la causa esté resuelta. Si `RestartCount` crece, el proceso termina al arrancar: `$DC logs worker` muestra la traza del primer arranque (un `.env` con una variable que `Settings` no acepta, por ejemplo).
- Arranque después de las 07:00 de Bogotá con el ciclo del día ya cerrado (`ok` o `error`): la recuperación no lo repite (`reclaim_finished=False`, S4A-D79 y S4A-D81) y `--status` sigue mostrando el `started_at` del intento anterior; para repetirlo, `--run-once` (S4A-W0-2.4: la fila `ok` de las 02:40Z del 2026-10-29 siguió igual tras recrear el worker y las dos corridas manuales sumaron los intentos 2 y 3 a la misma fila).
- En desarrollo (`compose.dev.yml`) `worker` y `tools` ven `api/src` y `api/migrations` del repo en solo lectura. El worker no tiene `--reload`: mientras se edita `app/worker/` o `memberships/expirations.py` se para con `$DC stop worker` y se arranca en el checkpoint del slice (`$DC start worker`, o `$DC restart worker` tras un cambio). `read_only` no molesta al bind: la imagen trae `PYTHONDONTWRITEBYTECODE=1` y corre como el usuario 10001 (riesgo 9 del plan, verificado).
- Latido (S4A-D8, S4A-D56): cada 30 s el worker hace `SELECT 1` (con `statement_timeout` de 5 s) y solo si responde toca `/tmp/apex-worker-heartbeat`. El healthcheck (30s/5s/3, `start_period` 90s) da `unhealthy` si el archivo tiene más de 120 s. En el Sprint 4A `unhealthy` en `$DC ps` es el aviso (`/health` del api no lee `worker.job_runs` hasta v0.2).
- Una corrida a mano: `$DC run --rm worker python -m app.worker.main --run-once expirations`. Códigos: 0 ok, 1 el job falló, 2 job inexistente o argumentos inválidos (lista los registrados), 3 ya hay una corrida `running` vigente. Dos corridas el mismo día reutilizan la misma fila de `worker.job_runs` (`attempts` crece). En el smoke de compose (S4A-W0-2, enmienda E6) la primera invocación acepta 0 o 3 (el `serve` del contenedor pudo estar recuperando el ciclo) y la segunda exige 0.
- Estado: `$DC run --rm worker python -m app.worker.main --status expirations` imprime el último intento en JSON (sin `attempts`) y sale 0, o 2 si no hay corridas; `--status expirations_sim` muestra la simulada.
- Fecha simulada (S4A-D48, S4A-D63, enmienda E5): `--date <AAAA-MM-DD> --simulate` solo con `ENV=dev` y contra una base cuyo nombre termine en `_sim` o sea `apex_test`; si falta cualquiera de las tres condiciones, salida 2. La primera línea dice `RELOJ SIMULADO: <fecha>`, el reclamo usa `job_name = "<job>_sim"` y `details["clock_override"] = true`. Nunca contra `apex-db-1`: la demo corre sobre `apex_sim` en `apex-db_test-1` (procedimiento en §11).
- Horario: todos los días a las 07:00 de Bogotá (constantes de `worker/schedule.py`, S4A-D5). Si el contenedor arranca después de esa hora y el ciclo del día no está hecho, lo recupera una sola vez.
- `--simulate` siempre exige `ENV=dev` y la base de simulación, también con la fecha de hoy; `--date` o `--simulate` sin `--run-once`, una fecha mal escrita o `--run-once` junto a `--status` dan 2. La guarda lee `Settings.ENV` y el nombre de la base de `DATABASE_URL`, nunca el entorno del proceso.
- Arranque (`serve`, S4A-D6): espera a la base sondeando `worker.job_runs` (reintentos sin límite con esperas de 1, 2, 4, ... s y tope de 60 s; el log `database not ready` solo trae el tipo del error); después toca el latido, arranca el scheduler (`coalesce`, una sola instancia por trabajo) y recupera el ciclo del día si toca. Una corrida `running` de más de 2 × `timeout_s` (30 min con el tope de 15 min por job) se da por muerta y se vuelve a reclamar; un `ok` o un `error` del día no se repiten solos: el ciclo programado reclama sin `reclaim_finished` y la recuperación del arranque y el disparo de las 07:00 se turnan con un candado del proceso (S4A-D79); para repetir el día, `--run-once`, que sí reclama un día cerrado y suma un intento. Si la base no da el candado de la fila al reclamar (`lock_timeout`), el job no corre y queda `job claim busy` en el log (S4A-D81).
- Parada: `SIGTERM` (`$DC stop worker`) detiene el scheduler y espera hasta 30 s a la corrida en curso; si no termina se cancela y su fila queda `error` con `CancelledError` (el cierre va blindado). En Windows, sin señales del bucle, la parada es Ctrl+C.
- Qué guarda `worker.job_runs` (S4A-D55): `error` es solo el nombre del tipo de la excepción (`RuntimeError`, `TimeoutError`), nunca su mensaje; `details` solo conteos de claves cerradas (`DETAIL_KEYS`) más `clock_override` y los últimos 20 intentos. Un job que devuelve otra clave queda en `error` con `ValueError`. Cada fallo deja un `job_failed` en el log de `app.alerts` (`LogAlertSink`; Telegram llega en v0.2) con el job, el resultado y el tipo del error. Un intento vencido que otro proceso volvió a reclamar queda en `attempts` como `stale`; si el proceso vencido termina después, su cierre no escribe (`lost_claim` en el log, `job_failed` con `LostClaim`, S4A-D77). Con la base caída al reclamar o al cerrar, `--run-once` sale con 1 y deja `job run failed` con el tipo del error (S4A-D83); en `serve`, `worker cycle failed` o `worker recovery failed` (S4A-D84).

### CLI, worker y migraciones (E7)

- `rotate-key`, `sign-audit`, `seed`, `issue-reset-link`, `unlock-user` y los jobs del worker (Sprint 4A) usan `create_engine_from` y heredan los tres tiempos. Un comando corto que choca con un candado falla con el `DBAPIError` del SQLSTATE (sin traducir: no es una petición HTTP) y se reintenta.
- Los comandos largos (`rotate-key` sobre muchas filas, `sign-audit`, la importación de US-112) se corren con la opción global, antes del comando: `$DC run --rm tools --db-timeouts off rotate-key ...`. `--db-timeouts` solo acepta `on` (por defecto) u `off`; otro valor sale con código 2. `off` vale solo para esa invocación del CLI y se aplica sobre una copia del `Settings`; el api no tiene forma de activarlo.
- Las migraciones de Alembic no reciben los tiempos: `migrations/env.py` arma su propio engine sin `server_settings` (no usa `create_engine_from`; lo vigila `tests/core/test_db_timeouts.py`). Una migración larga no se corta por `statement_timeout`.

## 10. Membresías y pagos (Sprint 3)

Esta sección cubre lo que hicieron S3-B1 a S3-B8: la venta y `0008` (B1), las congelaciones y `0009` (B2), la tabla de pagos, las reglas de registrar pago, los medios de pago y `0010` (B3), la inmutabilidad de los pagos con `0011`, la venta con primer pago, la ruta de registrar pago y la activación por cobertura (B4), la anulación de pagos (B5), la renovación y la anulación de membresías (B6), la lista, el detalle y el resumen de membresías (B7) y los de pagos (B8).

### Volcado y restauración (P-MIG)

- Volcado previo a cada migración del sprint (`0008` a `0011`), solo desde Bash y solo de los dos esquemas que el sprint toca (S3-D58, E11): `$DC exec -T db pg_dump -U apex -Fc -n memberships -n payments apex > docs/scratch/sprint-03-antes-<rev>.dump && chmod 600 docs/scratch/sprint-03-antes-<rev>.dump`. `-T` es obligatorio (sin él `exec` asigna una TTY y corrompe el binario); en PowerShell la redirección también lo corrompe. `*.dump` y `*.sql.gz` están en `.gitignore`; los volcados se borran al cerrar el sprint.
- **Los volcados guardan en claro lo que no pasa por el bus** (referencias y motivos de pagos y membresías; L-C de V10): `chmod 600` no es efectivo en NTFS (Git Bash lo acepta y no cambia los permisos de Windows), así que la protección es el perfil del usuario de Windows. Los volcados de `docs/scratch/` se borran al cerrar el sprint (paso V12) y nunca se sincronizan con una nube (OneDrive, Google Drive) ni se copian fuera de la máquina; `.gitignore` ya los deja fuera del repositorio.
- Comprobar que el volcado se puede leer: `$DC exec -T db pg_restore -l < docs/scratch/sprint-03-antes-<rev>.dump | head`.
- Restauración: `pg_restore --clean` de los dos esquemas sobre `apex-db-1`, con el api detenido (`$DC stop api`).

### Comprobar la `EXCLUDE` y los triggers de `0008` (S3-B1)

Todo dentro de una transacción que se revierte, sobre `apex-db-1` (`$DC exec -T db psql -U apex -d apex`). Las filas de prueba usan UUID nuevos y no tocan socios reales; el `ROLLBACK` final no deja nada.

1. Estructura: `\d memberships.memberships` muestra la `EXCLUDE` `ex_memberships_member_dates` (`USING gist (member_id WITH =, daterange(start_date, end_date, '[]'::text) WITH &&) WHERE (status <> 'cancelled'::text)`), los diez CHECK `ck_memberships_*` y, en "Triggers firing always", los tres triggers.
2. Los triggers siempre activos: `SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = 'memberships.memberships'::regclass AND NOT tgisinternal;` debe dar `A` en `memberships_guard_identity`, `memberships_forbid_delete` y `memberships_forbid_truncate`. Una `O` significa que alguien corrió `ENABLE TRIGGER` sin `ALWAYS`: bajo `session_replication_role = replica` dejarían de correr (M-6). Se corrige con `ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER <nombre>`.
3. Las funciones: `SELECT proname, prosecdef, proconfig FROM pg_proc WHERE pronamespace = 'memberships'::regnamespace;` da `guard_identity` y `forbid_delete` con `prosecdef = f` (`SECURITY INVOKER`) y `proconfig = {search_path=pg_catalog}`.
4. La `EXCLUDE` (23P01): dentro de `BEGIN;`, dos `INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, agreed_price_cop, start_date, end_date, status) VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000001', '<uuid de socio>', gen_random_uuid(), 120000, '2026-10-01', '2026-10-28', 'active');` con el mismo `member_id`: el segundo con `start_date = '2026-10-28'` falla con `ERROR: conflicting key value violates exclusion constraint "ex_memberships_member_dates"` (SQLSTATE 23P01); con `start_date = '2026-10-29'` entra (adyacentes). Una `cancelled` no cuenta.
5. La identidad (23000): `UPDATE memberships.memberships SET agreed_price_cop = 1 WHERE id = '<id>';` falla con `memberships_identity: la identidad de la membresía no cambia`; lo mismo `id`, `created_at`, `created_by`, `member_id`, `plan_id`, `start_date` y `classes_total`. Sobre una `cancelled` falla cualquier cambio de estado, motivo, quién, cuándo, fin o clases restantes. `\set VERBOSITY verbose` muestra `CONSTRAINT NAME: memberships_identity`.
6. Sin borrado: `DELETE FROM memberships.memberships WHERE id = '<id>';` y el vaciado de la tabla fallan con `memberships_no_delete` (23000). También con `SET LOCAL session_replication_role = replica;` antes. Desde `0009` la tabla tiene una FK que la referencia (`membership_freezes`): el vaciado simple lo rechaza PostgreSQL con `0A000` antes del trigger; con `CASCADE` corre el trigger y da `memberships_no_delete`.
7. `ROLLBACK;`.

En el api la `EXCLUDE` es la red frente a la carrera: `sell` revisa antes en código (409 `membership_conflict` o `membership_overlap` con `existing_id`) y, si dos ventas del mismo socio llegaran a la vez sin el candado del socio, el 23P01 sale como 409 `membership_overlap` sin `existing_id`. El candado del socio (`pg_advisory_xact_lock(hashtextextended('<uuid>', 0))`) se ve en `pg_locks` con `locktype = 'advisory'` mientras dura la transacción de la venta.

### Vender (S3-B1)

- `POST /api/v1/members/{member_id}/memberships` (admin y coach) con `{"plan_id": "<uuid>", "start_date": "AAAA-MM-DD"}` (`start_date` opcional: hoy de Bogotá). Responde 201 con la membresía en `pending_payment` y el precio del plan copiado en `agreed_price_cop` (cambiar el precio del plan después no la cambia). `start_date` entre hoy menos `max_retroactive_days` (configuración de membresías, 7 por defecto) y hoy más 366 días; fuera da 422 `start_date_too_retroactive` o `start_date_too_far`.
- Límite: 30 ventas por minuto por usuario (`USER_WRITE_LIMIT_PER_MIN`, bucket `memberships-write`); la 31 da 429 `rate_limited` con `Retry-After`. El contador vive en memoria y se limpia con `up -d api`.
- `renew=true` renueva (sección "Renovar una membresía"); `first_payment` registra el primer pago en la misma operación (sección "Vender con primer pago y activación").

### Congelaciones append-only (`0009`, S3-B2)

`memberships.membership_freezes` guarda una fila por congelación (`frozen_from`, `frozen_to`, `days = (frozen_to - frozen_from) + 1`) y solo admite `INSERT`. Comprobación con psql sobre `apex-db-1` (`$DC exec -T db psql -U apex -d apex`), dentro de `BEGIN; ... ROLLBACK;`:

1. Estructura: `\d memberships.membership_freezes` muestra la FK a `memberships.memberships(id)`, los CHECK `ck_membership_freezes_dates_ordered` y `ck_membership_freezes_days_match`, la `EXCLUDE` `ex_membership_freezes_dates` (`USING gist (membership_id WITH =, daterange(frozen_from, frozen_to, '[]'::text) WITH &&)`, sin `WHERE`), el índice `ix_membership_freezes_membership` y, en "Triggers firing always", `membership_freezes_append_only` (`BEFORE DELETE OR UPDATE ... FOR EACH ROW`) y `membership_freezes_forbid_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`).
2. Siempre activos: `SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = 'memberships.membership_freezes'::regclass AND NOT tgisinternal;` da `A` en los dos. Una `O` se corrige con `ALTER TABLE memberships.membership_freezes ENABLE ALWAYS TRIGGER <nombre>`.
3. La función: `SELECT proname, prosecdef, proconfig FROM pg_proc WHERE pronamespace = 'memberships'::regnamespace;` da también `forbid_freeze_mutation` con `prosecdef = f` y `proconfig = {search_path=pg_catalog}`.
4. Append-only (23000, `CONSTRAINT NAME: membership_freezes_append_only` con `\set VERBOSITY verbose`): `UPDATE memberships.membership_freezes SET days = 1;` falla con `membership_freezes_append_only: una congelación no cambia ni se borra`; también un `UPDATE` que no cambia nada (`SET frozen_to = frozen_to`), el `DELETE` y el vaciado de la tabla, y todo eso también tras `SET LOCAL session_replication_role = replica;`. Con la tabla vacía el `UPDATE` y el `DELETE` no tocan filas y no fallan: la prueba se hace con una fila (la del smoke o un `INSERT` dentro de la transacción).
5. La `EXCLUDE` (23P01): dos `INSERT` de la misma `membership_id` que comparten un día fallan con `ex_membership_freezes_dates`; adyacentes (21 a 30 y 31 a 31) entran.
6. `ROLLBACK;`.

Una congelación mal registrada no se corrige editando la fila: no hay endpoint para quitarla (US-089 no lo pide). Si hiciera falta, es una decisión del dueño con volcado previo y queda en `DECISIONES.md`.

### Congelar (S3-B2)

- `POST /api/v1/memberships/{membership_id}/freeze` (admin y coach) con `{"frozen_from": "AAAA-MM-DD", "frozen_to": "AAAA-MM-DD"}`. Responde 200 con la membresía: el fin se corre los días de la ventana (también si es futura), `status` es `frozen` si la ventana contiene hoy y `freezes` lista todas las congelaciones. Comparte el límite `memberships-write` con la venta (30 por minuto por usuario).
- Rechazos, en este orden (D14): 409 `membership_not_freezable` (solo `active` o `expiring` por su estado efectivo: una `pending_payment`, `frozen`, vencida o anulada no se congela); 422 `validation_error` con `field = frozen_to` (fechas invertidas); 422 `freeze_too_retroactive` y `freeze_outside_validity` con `field = frozen_from`; 409 `freeze_already_scheduled` (hay una ventana que aún no termina), `freeze_limit_reached` y `freeze_days_exceeded` (el mensaje dice los días que quedan); 409 `overlaps_future_membership` si el fin corrido choca con otra membresía del socio.
- Límites en la configuración de membresías (`max_freeze_days_per_membership` 30, `max_freezes_per_membership` 2, `max_retroactive_days` 7 por defecto).
- Auditoría: una fila `insert` de `memberships.membership_freezes` (sin sujeto, US-106) y una `update` de `memberships.memberships` con `after = {end_date, status}` y el socio como sujeto.

### Pagos: la tabla `payments.payments` (`0010`, S3-B3)

Un pago nunca se edita ni se borra (regla de datos 5): un error se corrige anulándolo (S3-B5) y registrando uno nuevo. La tabla no tiene llaves foráneas hacia `memberships` (otro esquema) y la inmutabilidad en la base la ponen los triggers de `0011` (sección "Inmutabilidad de los pagos"). Comprobación con psql sobre `apex-db-1` (`$DC exec -T db psql -U apex -d apex`):

1. Estructura: `\d payments.payments` muestra las quince columnas, los cinco CHECK `ck_payments_amount_range` (1 a 1.000.000.000), `ck_payments_method` (`cash`, `nequi`, `breb`), `ck_payments_reference_length` (nula o de 1 a 64), `ck_payments_void_reason_length` (hasta 500) y `ck_payments_void_coherent` (las cuatro columnas de anulación van juntas y el motivo no puede ser vacío ni nulo), y los índices `ix_payments_paid_at`, `ix_payments_membership_id` e `ix_payments_member_paid`.
2. Dentro de `BEGIN; ... ROLLBACK;`, un `INSERT` con `method = 'tarjeta'` o `amount_cop = 0` falla con 23514 y el nombre del CHECK.
3. Rollback de `0010`: `$DC exec api alembic downgrade 0009_membership_freezes` borra índices y tabla (con pagos reales se pierden: volcado previo obligatorio, sección "Volcado y restauración").

### Registrar pago: reglas del servidor (S3-B3)

Desde S3-B4 la ruta `POST /api/v1/memberships/{membership_id}/payments` (admin y coach) aplica estas reglas con el candado real de la membresía. Las reglas, en el orden en que se aplican:

- La membresía se bloquea primero (`SELECT ... FOR UPDATE` de su fila): dos pagos de la misma membresía nunca se deciden a la vez. Membresía inexistente: 404 `membership_not_found`; anulada: 409 `membership_cancelled`. Las vencidas y congeladas sí reciben pagos.
- Fecha del pago (`paid_at`): si no viene, es ahora. Tiene que traer zona horaria y no puede ser anterior al 1 de enero de 2020 (422 `validation_error`, `field = paid_at`), ni pasar de ahora más 5 minutos (mismo código). El coach solo puede registrar hasta `max_retroactive_days` días atrás (configuración de membresías, 7 por defecto): más atrás da 422 `paid_at_too_retroactive`. El admin no tiene ese tope, solo el piso de 2020.
- Sobrepago: si el monto supera el saldo (precio pactado menos lo pagado y no anulado), da 409 `payment_exceeds_balance` (`field = amount_cop`) salvo que venga `confirm_overpayment: true`.
- Tope: una membresía admite como máximo 60 pagos no anulados; el 61 da 409 `payment_limit_reached` (los anulados no cuentan).
- Posible duplicado: si el mismo usuario registró en los últimos 120 segundos un pago no anulado de la misma membresía con el mismo monto, medio y referencia (dos referencias vacías cuentan como iguales), da 409 `payment_possible_duplicate` salvo que venga `confirm_duplicate: true`. Las confirmaciones no se guardan.
- Referencia: opcional, se recorta, vacía queda nula, hasta 64 caracteres, solo letras y números sin tilde, espacio y `. _ / # -`, empezando por letra o número. Es para el número de comprobante: frases, correos o teléfonos con nombre se rechazan (422 en `reference`).
- Cada pago registrado escribe una fila `insert` de auditoría con el socio como sujeto.

### Medios de pago (S3-B3, US-056)

- Los códigos son fijos: `cash`, `nequi` y `breb`, en ese orden. Solo cambia cómo se ven: `GET /api/v1/settings/payment_methods` (admin) y `PATCH` con `{"value": {"cash": {"label": "...", "hint": "..."}, "nequi": {...}, "breb": {...}}, "version": <la leída>}`. Etiqueta de 1 a 30 caracteres, pista hasta 120 (puede ir vacía), dos medios no pueden tener la misma etiqueta sin distinguir mayúsculas (422 en `value.<código>.label`), un código distinto de los tres da 422. Versión vieja: 409 `version_conflict`.
- `GET /api/v1/payments/methods` (admin y coach) responde `{"items": [{"code", "label", "hint"}, ...]}` en orden fijo, con las etiquetas guardadas o las por defecto (Efectivo, Nequi, Bre-B).
- Si la sección guardada deja de validar (por ejemplo, editada a mano en la base), `GET /payments/methods` responde las etiquetas por defecto y el log de `app.settings` deja el aviso "la sección guardada no valida" con solo la clave `payment_methods`. Se corrige guardando la sección completa de nuevo desde Configuración.
- Cambiar etiquetas no toca ningún pago guardado: los pagos guardan el código.

### Inmutabilidad de los pagos (`0011`, S3-B4)

Desde `0011_payments_immutability` la base hace cumplir la regla de datos 5. La función `payments.forbid_mutation()` (`plpgsql`, `SECURITY INVOKER`, `search_path = pg_catalog`) corre en dos triggers de `payments.payments`, los dos en `ENABLE ALWAYS`: `payments_forbid_mutation` (`BEFORE DELETE OR UPDATE ... FOR EACH ROW`) y `payments_forbid_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`). Solo deja pasar una cosa: la anulación completa de un pago vigente (`voided = true`, motivo con texto, `voided_by` y `voided_at`; `updated_at` puede cambiar). Cada rechazo es SQLSTATE 23000 con `CONSTRAINT NAME: payments_immutable` y el motivo en el mensaje, en este orden:

- `payments_immutable: truncate`: vaciar la tabla.
- `payments_immutable: delete`: borrar una fila (también una anulada).
- `payments_immutable: already_voided`: cualquier `UPDATE` sobre un pago ya anulado (anularlo otra vez, volver `voided` a `false`, cambiar el motivo o un `UPDATE` sin cambios).
- `payments_immutable: column`: el `UPDATE` cambia alguna de las diez columnas protegidas (`id`, `membership_id`, `member_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by`), aunque la misma sentencia también anule.
- `payments_immutable: incomplete_void`: cualquier otro `UPDATE` de un pago vigente (falta el motivo o es solo espacios, falta `voided_by` o `voided_at`, `voided = false`, o solo se toca `updated_at`).

Cómo probar el trigger con psql sobre `apex-db-1` (`$DC exec -T db psql -U apex -d apex`), siempre dentro de una transacción que se revierte, sobre un pago existente (`SELECT id FROM payments.payments LIMIT 1;`):

1. Estado: `SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = 'payments.payments'::regclass AND NOT tgisinternal;` da `A` en los dos. Una `O` (alguien corrió `ENABLE TRIGGER` sin `ALWAYS`) se corrige con `ALTER TABLE payments.payments ENABLE ALWAYS TRIGGER <nombre>`. `SELECT prosecdef, proconfig FROM pg_proc WHERE oid = 'payments.forbid_mutation'::regproc;` da `f` y `{search_path=pg_catalog}`.
2. `BEGIN; UPDATE payments.payments SET amount_cop = 1 WHERE id = '<id>'; ROLLBACK;` falla con `payments_immutable: column`.
3. `BEGIN; DELETE FROM payments.payments WHERE id = '<id>'; ROLLBACK;` falla con `payments_immutable: delete`.
4. `BEGIN; SET LOCAL session_replication_role = replica; UPDATE payments.payments SET amount_cop = 1 WHERE id = '<id>'; ROLLBACK;` también falla (`ENABLE ALWAYS`, M-6).
5. `\set VERBOSITY verbose` muestra `SQLSTATE 23000` y `CONSTRAINT NAME: payments_immutable`.

En el api la única escritura permitida es la anulación de S3-B5 (`void`); cualquier otra se nota como 500 con `payments_immutable` en el log. Un pago mal registrado nunca se corrige editando la fila: se anula y se registra uno nuevo.

Rollback de `0011`: `$DC exec api alembic downgrade 0010_payments` (o `downgrade -1` si `0011` es el head) borra los dos triggers y la función y **no toca ninguna fila**: los pagos quedan intactos pero editables hasta volver a `upgrade head`. Volcado previo en `docs/scratch/sprint-03-antes-0011_payments_immutability.dump` (P-MIG), del estado anterior a `0011` (sin la función ni los triggers). Restauración de los dos esquemas, solo desde Bash y en este orden: (1) con el api arriba, `$DC exec api alembic downgrade 0010_payments`; (2) `$DC stop api`; (3) `$DC exec -T db pg_restore -U apex -d apex --clean -n payments -n memberships < docs/scratch/sprint-03-antes-0011_payments_immutability.dump`; (4) `$DC start api`, que vuelve a aplicar `0011` sobre los datos restaurados; (5) `$DC exec api alembic current` da `0011_payments_immutability (head)`. Restaurar sin el paso 1 deja `alembic_version` en `0011` con los esquemas sin triggers. Restaurar es una decisión del dueño y queda en `DECISIONES.md`.

### Vender con primer pago y activación (S3-B4)

- `POST /api/v1/members/{member_id}/memberships` acepta `first_payment` (`{"amount_cop", "method", "reference", "paid_at", "confirm_overpayment"}`, los mismos campos y reglas que registrar pago). La venta y el pago son una sola unidad: si el pago se rechaza no queda ni membresía, ni pago, ni auditoría. Los errores del pago llevan el campo con prefijo (`first_payment.amount_cop`, `first_payment.paid_at`). El saldo de una venta nueva es el precio del plan: un pago mayor pide `confirm_overpayment: true` (409 `payment_exceeds_balance`). El duplicado no aplica a la venta (cada venta es una membresía nueva). La retroactividad de `paid_at` la decide el rol de quien vende (el coach tiene el tope de `max_retroactive_days`).
- La respuesta trae `status` ya calculado (`active` si el pago cubre el precio; `pending_payment` si no), `paid_cop` (suma de pagos no anulados) y `first_payment_id`.
- `POST /api/v1/memberships/{membership_id}/payments` (admin y coach) registra un pago con las reglas de la sección anterior y responde 201 con el pago. Límite propio: 30 pagos por minuto por usuario (`USER_WRITE_LIMIT_PER_MIN`, bucket `payments-write`, separado de `memberships-write`); el 31 da 429. La venta con `first_payment` gasta también esta cubeta (además de `memberships-write`): con ella agotada, vender con pago da 429 y vender sin pago sigue.
- Activación por cobertura: cada pago registrado relee la membresía con su candado y, si estaba `pending_payment` y la suma de los pagos no anulados alcanza el precio pactado, pasa al estado del día (`active`, `expiring` si faltan `expiring_days` o menos, `frozen` si una congelación contiene hoy, o `expired` si ya venció: "pagada y vencida"). Deja una fila `update` de auditoría (`before.status = pending_payment`) del usuario que pagó, con el socio como sujeto. Un pago sobre una membresía que no está pendiente no cambia su estado.
- Auditoría de una venta pagada completa: `insert` de la membresía, `insert` del pago y `update` de la membresía, las tres del mismo usuario y con el mismo `subject_member_id`.

### Anular un pago y revertir la activación (S3-B5)

- `POST /api/v1/payments/{payment_id}/void` con `{"reason": "..."}` responde 200 con el pago anulado (`voided = true`, `void_reason`, `voided_by` = quien anuló, `voided_at` = ahora). **Solo el admin anula**: el coach y el socio reciben 403. Límite por usuario `admin-write` (30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`, compartido con anular membresía desde S3-B6); el 31 da 429.
- El motivo es obligatorio: texto de una línea, recortado, sin caracteres de control ni invisibles (NUL, U+200B) y de hasta 500 caracteres. Si no cumple, 422 `validation_error` con `field = "reason"`; el mensaje no repite lo que se escribió. El motivo es para el equipo: no se escriben datos personales del socio ni del pago (documento, teléfono, número de cuenta).
- La anulación no borra ni edita nada más del pago: monto, medio, comprobante y fecha quedan como estaban. Deja una fila `update` de auditoría del admin, con el socio como sujeto y `before`/`after` de las cuatro columnas de anulación. Un pago mal digitado se corrige así: anular con motivo y registrar el correcto (las dos filas quedan; solo suma el nuevo).
- Anular un pago ya anulado da **409 `payment_already_voided`** y no cambia nada. Aunque el api no lo viera, la base lo rechaza: el trigger de `0011` responde `payments_immutable: already_voided` a todo `UPDATE` de un pago anulado, y el api lo traduce al mismo 409. Un pago que no existe da 404 `payment_not_found`.
- Pago de un mes anterior: anular un pago cuyo `paid_at` cae en un mes civil de Bogotá anterior al de hoy (por ejemplo, del 30 de septiembre a las 23:59 en Bogotá, anulado en octubre) se permite, pero deja en el log del api un `WARNING` `void of previous month` con solo `payment_id` y `membership_id` (sin motivo, monto ni comprobante). Sirve para revisar cierres de mes ya reportados: buscarlo con `$DC logs api | grep "void of previous month"`.
- Reversión de la activación: después de anular, la membresía del pago se relee con su candado. Si su estado del día es `active`, `expiring` o `frozen` y lo que queda pagado (pagos no anulados) ya no cubre el precio pactado, vuelve a `pending_payment`. Solo cambia el estado: el fin y las congelaciones quedan iguales, y un pago nuevo que cubra la devuelve al estado del día (por ejemplo `frozen` si la congelación sigue). Deja una fila `update` de auditoría del admin (`before.status` con el estado guardado, `after.status = pending_payment`). Si lo que queda cubre (por ejemplo se anula un sobrepago), no cambia. Una membresía `pending_payment`, `cancelled` o ya vencida nunca cambia: anular un pago de una membresía anulada da 200 y no la reactiva.
- Anulación y reversión son una sola unidad: si la reversión falla, el pago queda sin anular y sin auditoría. `register` y `void` toman los candados en el mismo orden (membresía y después pago), así que pagar y anular a la vez sobre la misma membresía se esperan en orden, sin interbloqueo; dos anulaciones simultáneas del mismo pago dan una 200 y una 409.
- Comprobar en psql tras una anulación: `SELECT status FROM memberships.memberships WHERE id = '<membresía>';` y `SELECT action, before, after FROM audit.audit_log WHERE table_name = 'memberships.memberships' AND record_id = '<membresía>' ORDER BY seq;`. Por el api, `GET /api/v1/memberships/{membership_id}` devuelve el estado efectivo (sección "Estado de las membresías, lista y resumen").

### Renovar una membresía (S3-B6, US-088)

- `GET /api/v1/members/{member_id}/memberships/renewal-preview?plan_id=<plan>` (admin y coach) responde 200 con `start_date`, `end_date`, `agreed_price_cop` y `current_end_date` (el fin de la vigente, o `null` si no hay). Es solo lectura: no escribe, no toma candados y no gasta cupo de ningún límite. Da los mismos errores que la renovación: 404 `member_not_found`, 422 `member_inactive`, `plan_invalid`, `plan_inactive` o `validation_error` con `field = "plan_id"` (falta o no es UUID) y 409 `future_membership_exists`.
- Renovar es la misma venta, `POST /api/v1/members/{member_id}/memberships`, con `"renew": true` (misma cubeta `memberships-write`; con `first_payment` gasta también `payments-write`). El `start_date` del cuerpo se descarta: la renovación **empieza el día siguiente al fin de la vigente**, y ese fin ya incluye la extensión por congelación (una vigente del 1 al 31 de octubre congelada 10 días termina el 10 de noviembre y su renovación empieza el 11). Sin vigente (sin membresías, solo canceladas o la última ya vencida) empieza hoy. Termina en inicio más los días del plan elegido, que puede ser otro plan (su precio y su duración). No aplican el tope de 366 días hacia adelante ni el límite retroactivo de una venta normal.
- La renovación nace `pending_payment` (o `active` con fecha futura si el primer pago la cubre; el estado del día se calcula al llegar su inicio). La vigente no cambia ni gana auditoría; la renovación deja una fila `insert` con el socio como sujeto.
- Solo una renovación por empezar: si el socio ya tiene una futura (`pending_payment` de cualquier fecha, o `active`/`expiring` que aún no empieza), renovar o pedir la vista previa da **409 `future_membership_exists`** con `existing_id` = la futura. Dos renovaciones a la vez del mismo socio: una gana y la otra recibe ese 409 con el id de la ganadora (las dos esperan el candado del socio).
- Vender sin `renew` con un `start_date` dentro de la vigente da 409 `membership_conflict` (ya hay una vigente; D8, revisión previa). La base lo impide aunque el api no lo viera: un `INSERT` solapado da `23P01` por `ex_memberships_member_dates`.

### Anular una membresía (S3-B6, US-090)

- `POST /api/v1/memberships/{membership_id}/cancel` con `{"reason": "..."}` responde 200 con la membresía anulada (`status = cancelled`, `cancel_reason`, `cancelled_at`, sus congelaciones). **Solo el admin anula**: el coach y el socio reciben 403. Límite por usuario `admin-write` (30 por minuto, compartido con anular un pago); el 31 da 429.
- El motivo es obligatorio: una línea, recortado, sin caracteres de control ni invisibles, de 5 a 500 caracteres. Si no cumple, 422 `validation_error` con `field = "reason"`; el mensaje no repite el texto. El motivo es para el equipo: no se escriben datos personales del socio (documento, teléfono, diagnósticos). Los eventos internos solo llevan su largo.
- La anulación cambia solo cuatro columnas (`status`, `cancel_reason`, `cancelled_by` = el admin, `cancelled_at` = ahora) y deja una fila `update` de auditoría del admin con el socio como sujeto. **Los pagos quedan intactos**: no se anulan ni se devuelven (si hay que devolver dinero, se anula cada pago por su ruta). Las congelaciones tampoco cambian. Toma solo el candado de la fila de la membresía.
- Anular una ya anulada da **409 `membership_already_cancelled`** sin cambios; una que no existe, 404 `membership_not_found`. Registrar un pago sobre una anulada da 409 `membership_cancelled`; anular uno de sus pagos sí se permite y no la reactiva.
- **Una anulada no se puede revivir.** El trigger `memberships.guard_identity` rechaza cualquier cambio posterior de estado, motivo, quién o cuándo (`23000 memberships_identity`), también por SQL directo. Si se anuló por error, se vende de nuevo (el rango de la anulada queda libre para la `EXCLUDE`).
- Comprobar en psql: `SELECT status, cancel_reason, cancelled_by, cancelled_at FROM memberships.memberships WHERE id = '<membresía>';` y `SELECT action, before, after FROM audit.audit_log WHERE table_name = 'memberships.memberships' AND record_id = '<membresía>' ORDER BY seq;`.

### Estado de las membresías, lista y resumen (S3-B7, US-091 y US-092)

- **El estado se calcula al leer; no hay job.** Lo guardado solo manda en `cancelled` y `pending_payment`. Para el resto, cada lectura deriva el estado de la fecha de hoy en Bogotá (D5): `frozen` si una congelación contiene hoy; `expired` si hoy pasó el fin o no quedan clases; `expiring` si al fin le faltan `expiring_days` días o menos (ajuste `memberships.expiring_days` de `/settings`, 7 por defecto); si no, `active`. Una membresía guardada `active` cuyo fin ya pasó se ve `expired` sin que nadie la cambie (en psql sigue diciendo `active`, y está bien). El job de vencimientos de US-094 (Sprint 4A) solo pondrá lo guardado al día.
- **Lista:** `GET /api/v1/memberships` (admin y coach) con `limit`/`offset`, `status` separado por comas (`active,pending_payment`; el estado EFECTIVO; sin `status` no salen las anuladas), `plan_id`, `member_id`, `ends_from`/`ends_to` (fin entre esas fechas, incluidas; cada una entre 2020-01-01 y hoy más 5 años, si no 422 con el `field` de la fecha; invertidas dan 422 en `ends_to`) y `q` (nombre, apellido o documento, también de socios dados de baja; nunca descifra). Orden por fin y luego id. Con `q` gasta la cubeta de búsquedas de personas (60 por minuto por usuario, la misma de `GET /members?q=`); sin `q` no gasta nada.
- **Detalle:** `GET /api/v1/memberships/{id}` da la membresía con sus congelaciones, lo pagado (`paid_cop`, sin anulados) y el estado efectivo; una anulada se ve con su motivo; 404 `membership_not_found` si no existe.
- **Resumen:** `GET /api/v1/memberships/summary` da cinco enteros (`active`, `expiring`, `expired`, `frozen`, `pending_payment`): cuántos socios NO dados de baja hay en cada estado. Cuenta socios, no membresías: de las no anuladas de cada socio decide una, en este orden: la vigente (empezó y no está vencida ni pendiente), la pendiente de pago, la vencida y la futura; entre dos de la misma clase, la de fin más tardío. Un socio sin membresías (o con solo anuladas) no suma en ninguno, así que la suma más esos socios es el total de socios vivos.
- **Caché del resumen:** cada proceso del api guarda el resumen 30 s por día y `expiring_days`. Se vacía en cuanto se confirma una venta, una renovación, un pago, una anulación de pago, una congelación, una activación, una anulación de membresía, la baja o la reactivación de un socio en ese proceso (nunca antes del commit). Cambiar `expiring_days` usa otra entrada al instante. Para descartarla a mano basta reiniciar el api.
- **Un solo proceso del api (S3-D53, ampliada en S3-D93):** la caché del resumen, los contadores de intentos y los cupos por usuario viven en la memoria del proceso. El api corre con un solo proceso de Uvicorn (sin `--workers`, como dice la sección 1); con más de uno, la invalidación solo ocurre en el proceso que confirma y los demás muestran el número anterior hasta 30 s, y cada proceso cuenta sus propios cupos. No subir `--workers` sin mover antes estas tres cosas a un almacén compartido.
- **Cuadrar el resumen en psql** (misma regla, hoy de Bogotá y `expiring_days` 7; cambiar el 7 si el ajuste es otro):

```sql
WITH hoy AS (SELECT (now() AT TIME ZONE 'America/Bogota')::date AS d),
efectivo AS (
  SELECT m.member_id, m.start_date, m.end_date,
    CASE
      WHEN m.status IN ('cancelled', 'pending_payment') THEN m.status
      WHEN EXISTS (SELECT 1 FROM memberships.membership_freezes f
                   WHERE f.membership_id = m.id AND (SELECT d FROM hoy) BETWEEN f.frozen_from AND f.frozen_to) THEN 'frozen'
      WHEN (SELECT d FROM hoy) > m.end_date OR m.classes_remaining = 0 THEN 'expired'
      WHEN m.end_date - (SELECT d FROM hoy) <= 7 THEN 'expiring'
      ELSE 'active'
    END AS estado
  FROM memberships.memberships m
  WHERE m.status <> 'cancelled'
    AND m.member_id IN (SELECT id FROM members.members WHERE deleted_at IS NULL)
),
decide AS (
  SELECT DISTINCT ON (member_id) member_id, estado
  FROM efectivo
  ORDER BY member_id,
    CASE WHEN estado = 'pending_payment' THEN 1 WHEN estado = 'expired' THEN 2
         WHEN start_date <= (SELECT d FROM hoy) THEN 0 ELSE 3 END,
    end_date DESC, start_date DESC
)
SELECT estado, count(*) FROM decide GROUP BY estado ORDER BY estado;
```

  Es una consulta de soporte, no del api (el api nunca cruza esquemas: pide los socios vivos a `members` y cuenta en `memberships` por lotes de 1.000 ids).

### Pagos: lista, detalle y resumen del mes (S3-B8, US-098 a US-100)

- **Lista:** `GET /api/v1/payments` (admin y coach) con `limit`/`offset` (hasta 200) y estos filtros, todos opcionales y combinables:
  - `from` y `to`: instantes con zona (`2026-10-01T05:00:00Z` o `2026-10-01T00:00:00-05:00`). El rango es `[from, to)`: incluye `from` y excluye `to`. Cada uno debe estar entre 2020-01-01 y hoy más 5 años; si no, 422 `validation_error` con `field` `from` o `to`. Invertidas dan 422 en `to`. Sin zona también es 422.
  - `method` (`cash`, `nequi`, `breb`), `registered_by` (id de usuario), `member_id`, `membership_id`.
  - `voided`: `true` solo anulados, `false` solo vigentes; sin el parámetro, todos.
  - `backdated`: `true` solo los registrados más de 24 h después de la fecha del pago (24 h exactas no cuentan).
  - `q`: la referencia completa sin importar mayúsculas (`neq-55` encuentra `NEQ-55`; no es búsqueda parcial) o el nombre, apellido o documento del socio, incluidos socios dados de baja. Nunca descifra: la búsqueda va por índice ciego. Con `q` gasta la cubeta de búsquedas de personas (60 por minuto por usuario, compartida con `GET /members?q=` y `GET /memberships?q=`). Sin `q` no gasta nada.
- Orden: del pago más reciente al más viejo (`paid_at` descendente y, en empate, id descendente).
- Cada fila trae nombre y apellido del socio, plan y fechas de la membresía, y quién registró como correo parcial (`l•••@dominio`). Nunca trae documento, teléfono ni correo del socio, ni el correo completo del usuario.
- **Detalle:** `GET /api/v1/payments/{id}` da la fila más `voided_by`, `voided_by_name` (también parcial), `voided_at` y `created_at`. Si no existe, 404 `payment_not_found`.
- **Resumen:** `GET /api/v1/payments/summary?month=AAAA-MM` (sin `month`, el mes actual de Bogotá) da `total_cop` y `by_method` (`cash`, `nequi`, `breb`; las tres claves siempre) solo de pagos vigentes, `payments_count` (vigentes) y `voided_count` (anulados). El mes es el mes civil de Bogotá según `paid_at`: octubre va de `2026-10-01T05:00Z` a `2026-11-01T05:00Z`. Un pago de septiembre anulado en octubre baja septiembre y no toca octubre. Un `month` que no sea `AAAA-MM`, con mes fuera de 01–12 o año fuera de 2020–2100, da 422 con `field` `month`.
- **Cuadre:** `total_cop` del resumen es igual a la suma de `amount_cop` de `GET /payments?from=<inicio>&to=<fin>&voided=false` del mismo mes, recorriendo todas las páginas. En psql, con el mismo rango:

```sql
SELECT method, sum(amount_cop) FILTER (WHERE NOT voided) AS vigente,
       count(*) FILTER (WHERE NOT voided) AS pagos,
       count(*) FILTER (WHERE voided) AS anulados
FROM payments.payments
WHERE paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00-05' AND paid_at < TIMESTAMPTZ '2026-11-01 00:00:00-05'
GROUP BY ROLLUP (method) ORDER BY method;
```

  La fila con `method` nulo es el total. Pagos retroactivos: `SELECT id, paid_at, created_at FROM payments.payments WHERE created_at - paid_at > interval '24 hours' ORDER BY paid_at DESC;`.
- Si una página de la lista sale 500 y el log muestra `payment without membership reference` con un `payment_id`, ese pago apunta a una membresía cuyo socio o plan no aparece. Es un problema de integridad, no de la consulta: revisar la fila en psql antes de tocar nada.

## 11. Worker, auditoría verificable y tablero (Sprint 4A)

Esqueletos que completan los slices del Sprint 4A (`docs/ddd/blueprints/sprint-04a-plan.md`). Lo que dice cada esqueleto ya es una decisión registrada en `docs/ddd/DECISIONES.md`, sección "Sprint 4A".

### Primera corrida del job de vencimientos (S4A-B2)

- La primera corrida sobre la base viva corrige el `status` guardado de las membresías vencidas o por vencer: deja decenas de filas `update` en `audit.audit_log` con `user_id = 00000000-0000-0000-0000-000000000001` (`SYSTEM_USER_ID`). Es el rastro correcto, no un error.
- Las lecturas ya derivan el estado (S4A-D1); el job solo alinea la columna espejo y emite `MembershipExpiring` y `MembershipExpired` (sin suscriptores en 4A). Un consumidor del Sprint 5 descarta eventos cuyo `on_date` no sea hoy ni ayer en Bogotá.
- Caché del resumen: el worker no invalida la caché del resumen de membresías del api (corre en otro proceso y S3-D93 la vacía solo al confirmar una escritura del propio api). No es un riesgo de datos: el resumen se deriva con `status_expr` y no depende de la columna que corrige el job; tras las 07:00 una lectura rancia dura como mucho `SUMMARY_CACHE_TTL_S` (el TTL la acota). Para descartarla al instante, reiniciar el api.
- Qué recalcula: solo las membresías guardadas en `active`, `expiring` o `frozen` cuyo estado efectivo de hoy (Bogotá) difiere de lo guardado; `pending_payment`, `cancelled` y `expired` no se tocan nunca. Una transacción por socio con el orden de candados de D3 (socio, fila, cadena); re-ejecutar el mismo día no cambia nada (cero filas `update` nuevas y cero eventos).
- Ocupación: un socio cuyo candado no llega a tiempo se reintenta dos veces (esperas de 0,5 s y 1 s, fuera de la transacción) y, si sigue ocupado, se omite (`busy_omitidos`); la corrida sigue y la del día siguiente (o una a mano) lo corrige. Un socio que falla por otra causa cuenta en `errores` y el log lleva solo el tipo del error (`membership recompute failed`, `error_type`), nunca ids, nombres ni el mensaje. Con `busy_omitidos + errores > 0` la fila de `worker.job_runs` queda en `error` y sale la alerta `job_failed`.
- A mano: `$DC run --rm tools recompute-memberships --as <email>` (con `ENV=production`, `--as` es obligatorio y `--db-timeouts off` se rechaza; S4A-D53). Las filas `update` quedan a nombre de quien va en `--as` (sin `--as`, del usuario técnico). Imprime una línea con los siete conteos (`revisados=... errores=...`), nunca ids ni nombres. Salida 0 sin errores, 1 con socios omitidos por ocupación o con error, 2 por argumento o `--as` inválido o una guarda incumplida. Sin `--simulate` no deja fila en `worker.job_runs`.
- Demo con fecha (S4A-D63): `pg_dump -Fc` de `apex` a `docs/scratch/`, `createdb apex_sim` y `pg_restore` en `db_test`, `$DC run --rm -e DATABASE_URL worker python -m app.worker.main --run-once expirations --date <fecha> --simulate` con `DATABASE_URL` apuntando a `apex_sim`, lectura con psql, `dropdb apex_sim` y borrar el volcado. `apex-db-1` nunca recibe una corrida con fecha.
- Lo mismo desde la CLI: `$DC run --rm -e DATABASE_URL tools recompute-memberships --date <fecha> --simulate` contra `apex_sim`. Exige `ENV=dev` y una base cuyo nombre termine en `_sim` (o `apex_test`); si no, sale con 2 sin conectar. La primera línea es `RELOJ SIMULADO: <fecha>`; la corrida pasa por el runner del worker (S4A-D89): reclama `expirations_sim` (nunca la fila real del día), la auditoría va a nombre del usuario técnico, por eso `--simulate` con `--as` sale con 2 ("--simulate no admite --as"), y sale con 3 si otra corrida simulada del mismo día sigue vigente. `--date` igual a hoy sin `--simulate` es una corrida normal.
- Regla de `on_date` (S4A-D48 punto 3) para los consumidores del Sprint 5: `MembershipExpiring` y `MembershipExpired` llevan el "hoy" de Bogotá de la corrida; Notifications descarta todo evento cuyo `on_date` no sea hoy ni ayer, así una corrida simulada o atrasada nunca avisa a un socio fuera de fecha.

### Verificar la cadena de auditoría (S4A-B3)

- Qué hace (US-104, US-105): recorre `audit.audit_log` de 1 a `max(seq)` (el `through_seq`) en lotes de 500 filas (cada uno por rango acotado de `seq`, S4A-D120), cediendo el event loop entre lotes, y se detiene en la primera ruptura. Una fila alterada rompe en su propio `seq`; una fila borrada, en el `seq` siguiente. Luego compara con el ancla (S4A-D43): la última verificación `ok` guardada; si la cadena ya no llega a su `through_seq` o esa fila no conserva su `through_hash`, el resultado es "rota" aunque la cadena sea internamente válida (una cola borrada o reescrita). Una verificación rota no mueve el ancla. Cada verificación deja una fila en `audit.verifications` (append-only) y una fila `verify` en la cadena (`table_name = audit.verifications`, `after` con `ok`, conteos, `through_seq`, `through_hash`, horas y `source`), que entra en la verificación siguiente. Nunca modifica filas existentes.
- Desde la pantalla o la API (admin): `POST /api/v1/audit/verify`. Hasta `SYNC_VERIFY_MAX_ROWS = 100.000` filas responde 200 con el resultado (`ok`, `rows_checked`, `through_seq`, `broken_at_seq`, horas, `triggered_by`, `source`; nunca `before`, `after` ni el hash). Por encima responde 202 `{status: "running", last}` (`last` es la última terminada) y la verificación sigue en una tarea del api: sondear `GET /api/v1/audit/verify/last` hasta que cambie. La tarea no sobrevive a un reinicio del api (se cancela en el apagado y suelta el candado; el `--reload` de desarrollo la mata): basta con repetir. 409 `verification_running` si ya corre otra. Cubetas por usuario `audit-verify` (`USER_AUDIT_VERIFY_LIMIT_PER_MIN`, 3) y `audit-verify-hour` (`USER_AUDIT_VERIFY_LIMIT_PER_HOUR`, 20): la 4.ª del minuto o la 21.ª de la hora dan 429. `GET /audit/verify/last` no tiene límite.
- Desde la CLI: `$DC run --rm tools verify-audit --as <email> [--wait-timeout 300]` (con `ENV=production`, `--as` es obligatorio y `--db-timeouts off` se rechaza; S4A-D53). Si otra verificación tiene el candado, reintenta cada 2 s hasta `--wait-timeout`. Imprime una sola línea: `Cadena íntegra: N registros verificados hasta el seq M.` (añade "sin verificación anterior que comparar" la primera vez) o `Cadena rota en el registro seq N.` (añade "no coincide con la verificación anterior" si la ruptura la da el ancla); nunca ids, hashes ni datos de `before`/`after`. Códigos: 0 íntegra, 1 rota, 2 por `--as` inválido, base que no responde (mensaje genérico, sin URL), `--wait-timeout` agotado o una guarda de producción. La fila y la entrada `verify` van a nombre de `--as` (sin `--as`, del usuario técnico).
- Candado: aviso de sesión `4_270_003` (`AUDIT_VERIFY_LOCK_KEY`), tomado en una conexión dedicada en `AUTOCOMMIT` (sin transacción abierta: `idle_in_transaction_session_timeout` no la corta durante una corrida larga, H-2) que se invalida (cierre físico) al terminar, aunque el `unlock` falle: el candado nunca vuelve al pool. Si parece quedar tomado, la conexión ya se cerró sola; comprobarlo con `$DC exec -T db psql -U apex -d apex -c "SELECT pid, state FROM pg_locks l JOIN pg_stat_activity a USING (pid) WHERE l.locktype = 'advisory' AND l.objid = 4270003"` (solo lectura) y, si hay una fila, reiniciar el api.
- Plazos: la rama síncrona tiene `SYNC_VERIFY_MAX_SECONDS = 45` (bajo los 60 s de Nginx); si vence, revierte lo que llevaba y sigue en segundo plano con el mismo candado (202, S4A-D100). La tarea 202 tiene `VERIFY_MAX_SECONDS = 900`; si vence, no deja fila, suelta el candado y el log lleva `audit verify failed` con solo `error_type` (`TimeoutError`). Igual con cualquier otro fallo de la tarea.
- Ancla externa: cada verificación `ok` hecha por la API escribe en el log del api la línea `audit anchor` con `through_seq` y `through_hash` (nunca `before`/`after`). `verify-audit` no la emite (la CLI no configura logging; evidencia de B3.14): el ancla de una corrida de la CLI se lee con `$DC exec -T db psql -U apex -d apex -c "SELECT through_seq, through_hash FROM audit.verifications WHERE ok ORDER BY finished_at DESC LIMIT 1"` (solo lectura). Copiar la última junto a cada respaldo: es la referencia externa hasta la firma de v0.3 (residual de S4A-D43: quien controle la base y el log podría rehacer ambos).
- Cubetas en memoria (S4A-D103): `audit-verify`, `audit-verify-hour` y `staff-read` viven en el único proceso de Uvicorn, como las demás por usuario; un reinicio del api las vacía. No subir a varios procesos sin un almacén compartido.
- Deuda con dueño (S4A-D98): los triggers de `audit.audit_log` de `0002` no tienen `ENABLE ALWAYS`; bajo `session_replication_role = replica` no disparan. La verificación lo detectaría como "rota". Lo corrige `0014_audit_log_triggers_always` en el Sprint 4B.
- Si `verify-audit` contra `apex-db-1` da "rota": parar, no tocar la tabla, guardar la salida y escalar (cuarta parada del plan).

### Consultar la auditoría y el tablero (S4A-B4, S4A-B8)

- `GET /audit`, `GET /audit/{seq}`, `GET /members/{id}/audit` y `GET /dashboard` consumen la cubeta `staff-read`; `offset` hasta 100.000. La lectura de la auditoría no se audita: el log de acceso del api es el único rastro.
- Filtros de `GET /audit` (solo admin, `seq` descendente): `from` (incluido) y `to` (excluido), con zona horaria, entre `2020-01-01T00:00Z` y ahora más un día, y `from < to` (si no, 422 `validation_error` con `field` `from` o `to`); `user_id`; `table` como `esquema.tabla`, una de las nueve tablas auditadas (por ejemplo `memberships.memberships`; otra da 422 `field="table"`); `record_id`, que exige `table` (sin ella, 422 `field="record_id"`: así el conteo usa el índice `(table_name, record_id)`, S4A-D106); `subject_member_id`; `action`. Un `offset` mayor que 100.000 da 422 con `field="offset"`. `total` se satura en 100.001 (el conteo está acotado, S4A-D106).
- `q`: si es un UUID y llega `table`, filtra `record_id` (sin `table` se ignora; si además llega `record_id`, manda este, S4A-D104 y S4A-D106); otro texto busca el correo de quien actuó, parcial, sin mayúsculas ni tildes, y `%` y `_` son literales. Sin coincidencias, la página sale vacía con `total = 0`.
- Cada fila trae `user_email` y `user_name` (parte local del correo; `Sistema` para el usuario técnico); son nulos si el usuario ya no está en `auth.users`. La lista nunca trae `before` ni `after`.
- El detalle `GET /audit/{seq}` (`seq` entre 1 y `2**63 - 1`; fuera de rango, 422; inexistente, 404 `audit_entry_not_found`) trae `before`, `after`, `changes`, `prev_hash` y `hash`. Nunca descifra: todo valor que contiene `apx1.` sale como `{"encrypted": true, "key_id", "alg"}`, y uno mal formado con `key_id` y `alg` nulos; más de 32 niveles de anidación salen como `{"truncated": true}` (S4A-D52, S4A-D105, S4A-D107). Comprobación rápida: `grep -c apx1.` sobre el cuerpo debe dar 0.
- Por qué no se audita la lectura (S4A-D61 c): escribir una fila por consulta haría crecer la cadena con cada vistazo del admin y cada recarga del front, y una lectura no cambia datos; el rastro de quién consultó es el log de acceso del api, y el abuso lo frena `staff-read` (`USER_READ_LIMIT_PER_MIN`, 120 por minuto por usuario por defecto, compartida entre lista y detalle; `GET /audit/verify/last` no la consume).
- El tablero excluye al usuario del sistema en los últimos movimientos.

### Tablero de inicio (S4A-B8, US-108 a US-110)

- `GET /api/v1/dashboard` (admin y coach; mismo cuerpo salvo las finanzas, ver abajo; cubeta `staff-read`; `Cache-Control: no-store`; sin parámetros). El módulo `dashboard` no tiene tablas ni ejecuta SQL: solo compone los services de `memberships`, `payments`, `audit`, `members` y `auth`.
- De dónde sale cada número:
  - `today`: el día de Bogotá del reloj del api (`current_clock().today_bogota()`).
  - `members_active`, `members_expiring`, `members_expired`, `members_frozen` y `members_pending_payment`: los mismos cinco conteos de `GET /memberships/summary` con ese `today` (socios no dados de baja por el estado resuelto de su membresía). Comprobación: deben coincidir con ese endpoint.
  - `income_month` (`AAAA-MM` de `today`) e `income_month_cop`: para el admin, el `total_cop` de `GET /payments/summary?month=<income_month>` (pagos no anulados del mes de Bogotá; un pago de las 22:00 del 31 en Bogotá cuenta en ese mes aunque en UTC ya sea el día 1).
  - `last_movements`: hasta 10 frases de `audit.service.recent` sobre `members.members`, `memberships.memberships` y `payments.payments`, solo `insert`, `update` y `delete` (nunca `reveal`, `login`, `export` ni `verify`), una consulta por tabla con el índice `(table_name, seq DESC)` y la más reciente primero. La frase sale del catálogo de S4A-D28 con el actor como parte local del correo (nunca el correo), el socio como "Nombre I." y el monto como `$ 120.000`; la vista reducida solo lleva `member_id`, `plan_id`, `membership_id`, `amount_cop`, `voided`, `deleted_at` y `status` (nunca blobs `apx1.`, `reference` ni `void_reason`). Socio o plan sin nombre: "un socio" o "un plan"; actor inexistente: "Alguien".
  - `notifications_today`, `members_without_consent`, `attendance_week`, `sessions_today` y `wod_today`: siempre presentes y `null` en v0.1 (llegan en v0.2, v0.4 y v0.5).
- Caché de 30 s: los conteos de membresías vienen de la caché de proceso del resumen (`SUMMARY_CACHE_TTL_S = 30`), que se invalida con cada venta, pago, anulación o congelamiento en ese mismo proceso; con varios procesos, otro puede servir su copia hasta que venza. Ingresos y movimientos se leen en cada llamada.
- Solo el admin ve finanzas (S4A-D118): para el coach `income_month_cop` llega `null` (no se consulta `payments`) y las frases de pagos no llevan monto ("registró un pago de Laura G."). Los ingresos no tienen caché (S4A-D119 a): cada llamada del admin suma los pagos del mes por el índice `paid_at DESC`, y `staff-read` acota a 120 por minuto por usuario.
- Por qué el sistema no aparece en los movimientos (`exclude_user_ids=(SYSTEM_USER_ID,)`, Q10 y US-110): el job de vencimientos, el seed y la importación escriben como el usuario técnico y taparían lo que hace recepción; el filtro se aplica antes del límite de 10, así que las 10 frases son siempre de personas. Lo del sistema sigue en `GET /audit` con `user_id` del sistema.
- Comprobación rápida: `grep -c apx1.` sobre el cuerpo da 0 y ninguna frase empieza con `Sistema`.

### Limpieza P2-1 de planes de prueba (S4A-B7 y V12)

- Los planes `E2E-tope-*` y los de las specs se retiran por la API (`DELETE /plans/{id}`) con un admin desechable, respetando el tope de `admin-write` (30 por minuto); nunca por SQL. El 409 `plan_has_active_memberships` solo da el conteo: esos planes se desactivan y quedan.
- Procedimiento:
  1. Listar los candidatos: `GET /api/v1/plans?q=E2E-tope-&limit=200` (y `offset` hasta cubrir `total`), más los nombres que crean las specs del front; guardar los ids en un archivo del scratchpad.
  2. Por cada plan, buscar sus membresías `pending_payment` (`GET /api/v1/memberships?plan_id=<id>&status=pending_payment`) y anularlas con `POST /api/v1/memberships/{id}/cancel`.
  3. `DELETE /api/v1/plans/{id}`: 204 lo retira; 409 `plan_has_active_memberships` (quedan activas pagadas) → `POST /api/v1/plans/{id}/deactivate` y el plan se queda.
  4. Ritmo: todas las escrituras (anular, borrar, desactivar) cuentan en `admin-write`; el script del scratchpad espera 2 s entre llamadas (30 por minuto) y ante un 429 respeta `Retry-After`.
  5. Al cerrar, dar de baja el admin desechable, como en la validación final del Sprint 3 (sección 8: nunca se resetea la contraseña del admin real).
