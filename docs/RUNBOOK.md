# APEX · Runbook de operación

Procedimientos y valores de operación del api que no viven en el código. Alias usado en todo
el documento:

```
DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"
```

En producción se omite `-f infra/compose.dev.yml`.

## Sesión: login, refresh y logout (S2-B2)

### Capas del límite de intentos

Cada capa responde 429 `rate_limited` con `Retry-After`, el mismo cuerpo para cualquier correo
(no enumera cuentas). Los valores por defecto son los de producción; se cambian en `.env`.

1. **Borde (Nginx).** `limit_req` de `/api/v1/auth/`: 60 por minuto por IP con ráfaga de 30
   (`infra/nginx/default.conf`). Fijo para todos los entornos.
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
- El bloqueo persistente (capa 5) está en la base: lo levanta `cli unlock-user`, que llega en
  S2-B5 y limpia `locked_at`, `failed_login_count` y los contadores en memoria de esa cuenta.
  Mientras tanto, `up -d api` limpia solo la memoria; el bloqueo sigue.
- Perfil E2E (E5): durante la validación V4 el `.env` sube los topes (por ejemplo
  `LOGIN_IP_LIMIT=1000`), se aplica con `up -d api` y se restaura al terminar.

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

### Primer admin

`ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` van en `.env.seed` (solo lo lee el servicio `tools`):
`$DC run --rm tools seed`. El admin sembrado debe cambiar la contraseña al entrar
(`must_change_password`); `--no-force-change` solo se acepta con `ENV=dev`. Una segunda corrida
dice "omitido". Borrar `.env.seed` después del primer seed. Tras cambiar `cli.py` hay que
reconstruir la imagen (`$DC build api`) antes de usar `tools`.
