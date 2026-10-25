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
7. [Imágenes base por digest y su renovación](#7-imágenes-base-por-digest-y-su-renovación-s3-d62)
8. [Primer admin sin `.env.seed`](#8-primer-admin-sin-envseed-s3-d64)
9. [Tiempos de espera de la base y 503 `busy`](#9-tiempos-de-espera-de-la-base-y-503-busy-s3-w0-2)
10. [Membresías y pagos](#10-membresías-y-pagos-sprint-3)

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
- Pruebas de rendimiento (marcador `perf`; 1.000 socios, búsqueda por documento bajo 500 ms con `EXPLAIN` del único parcial, y L-11 de 20 logins fallidos concurrentes con p95 bajo 2 s): `cd api && uv run pytest -m perf -q -s` (con `TEST_DATABASE_URL`). No son gate (S2-D27, revisión de Fase 4): `run-gates.sh` y el job `api` de la CI corren `-m "not perf"`, y la CI las corre en un paso aparte que informa sin bloquear (`continue-on-error`, 10 minutos). Se corrieron en el gate de B8 y en V5.

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
- **`0008_memberships`:** `downgrade 0007_plans` borra los tres triggers, las dos funciones, los índices y `memberships.memberships` (con sus filas: antes, el volcado de la sección 10). El esquema `memberships` y `btree_gist` quedan. Se revierte el checkpoint de S3-B1 (y los posteriores que usen la tabla). La auditoría de las ventas queda en `audit.audit_log` (append-only).
- **`0009_membership_freezes`:** `downgrade 0008_memberships` borra los dos triggers, la función `memberships.forbid_freeze_mutation()`, el índice y `memberships.membership_freezes` (con sus filas: antes, el volcado de la sección 10). Las membresías conservan el `end_date` ya corrido y el `status` guardado; sin la tabla, `compute_status` deja de ver las ventanas (una `frozen` guardada se lee por fecha). Quedan `memberships.memberships`, sus dos funciones, el esquema y `btree_gist`. Se revierte el checkpoint de S3-B2. La auditoría de las congelaciones queda en `audit.audit_log`.
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

### CLI, worker y migraciones (E7)

- `rotate-key`, `sign-audit`, `seed`, `issue-reset-link`, `unlock-user` y los jobs del worker (Sprint 4A) usan `create_engine_from` y heredan los tres tiempos. Un comando corto que choca con un candado falla con el `DBAPIError` del SQLSTATE (sin traducir: no es una petición HTTP) y se reintenta.
- Los comandos largos (`rotate-key` sobre muchas filas, `sign-audit`, la importación de US-112) se corren con la opción global, antes del comando: `$DC run --rm tools --db-timeouts off rotate-key ...`. `--db-timeouts` solo acepta `on` (por defecto) u `off`; otro valor sale con código 2. `off` vale solo para esa invocación del CLI y se aplica sobre una copia del `Settings`; el api no tiene forma de activarlo.
- Las migraciones de Alembic no reciben los tiempos: `migrations/env.py` arma su propio engine sin `server_settings` (no usa `create_engine_from`; lo vigila `tests/core/test_db_timeouts.py`). Una migración larga no se corta por `statement_timeout`.

## 10. Membresías y pagos (Sprint 3)

Lo completan S3-B1 a S3-B5; cada slice agrega su parte (B1 la venta y `0008`, B2 las congelaciones y `0009`).

### Volcado y restauración (P-MIG)

- Volcado previo a cada migración del sprint (`0008` a `0011`), solo desde Bash y solo de los dos esquemas que el sprint toca (S3-D58, E11): `$DC exec -T db pg_dump -U apex -Fc -n memberships -n payments apex > docs/scratch/sprint-03-antes-<rev>.dump && chmod 600 docs/scratch/sprint-03-antes-<rev>.dump`. `-T` es obligatorio (sin él `exec` asigna una TTY y corrompe el binario); en PowerShell la redirección también lo corrompe. `*.dump` y `*.sql.gz` están en `.gitignore`; los volcados se borran al cerrar el sprint.
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
- `renew` y `first_payment` todavía no están: `renew=true` y cualquier `first_payment` dan 422 `validation_error` (con `field`) hasta S3-B6 y S3-B4.

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

Pendiente de S3-B3 a S3-B5: triggers de `payments.payments` (`UPDATE payments.payments SET amount_cop = 1` debe fallar con `payments_immutable`) y rollback de `0010` y `0011`.
