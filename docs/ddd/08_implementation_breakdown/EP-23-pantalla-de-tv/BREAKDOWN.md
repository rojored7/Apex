# EP-23 · Pantalla de TV del box — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-23-pantalla-de-tv.md`
- **Versión:** v0.5
- **Historias:** US-175 a US-177 (3 historias, 8 puntos)

## Resumen

La TV muestra el WOD del día y el leaderboard en la pared del box sin sesión de usuario. Tres piezas: la sección `tv` de Settings con un token de dispositivo que se genera y se guarda solo como hash (US-175); el módulo de lectura `tv`, sin models, con `GET /tv/today` en la lista blanca de rutas sin rol, protegido por el token en la cabecera `X-Device-Token`, rate limit y proyección que solo deja nombre con inicial del apellido, nivel y marca (US-176); y la página `/tv` en `TvLayout` que refresca cada `refresh_seconds` (US-177).

## Correcciones aplicadas por DECISIONES.md

- US-176 acepta el token por cabecera `X-Device-Token` o por parámetro `?token=` → el API solo lo acepta en la cabecera `X-Device-Token`; un `?token=` en la llamada al API se ignora y responde 401 si no viene la cabecera: corregido por DECISIONES N-44.
- US-177 guarda el token en memoria → la página lee `?token=` una sola vez, lo guarda en `localStorage`, limpia la query con `history.replaceState` y desde ahí lo envía en `X-Device-Token`; si no hay query usa el de `localStorage`: corregido por DECISIONES N-44.
- US-176: Nginx no debe registrar la query string → no se registran query strings de `/api/v1/tv/`: confirmado por DECISIONES N-44. Además, como la URL de la página `/tv?token=…` también pasa por Nginx una vez, se aplica el mismo formato de log sin query a `location = /tv` (extensión mínima del mismo control; ver Riesgos).
- US-175 y US-176: hash del token, rate limit de 12 por minuto por IP y `display_name` con nombre e inicial del apellido: supuestos aceptados por DECISIONES N-44.
- US-176: socios con sexo nulo entran al leaderboard de la TV porque usa el filtro "Todos": confirmado por DECISIONES Q22. "Hoy" es `today_bogota()`: DECISIONES Q28.
- US-175: el token se genera con el generador seguro de `core/security` y su hash se calcula ahí; `settings` y `tv` no importan `hashlib` ni `hmac` (solo `core/security` lo hace) (restricción dura y N-06).

## Validación contra el dominio y la arquitectura

- Dominio: invariante de Settings "`tv.device_token` se genera, no se escribe" (`02_domain_model.md` 2.14). No hay aggregate nuevo. El dispositivo TV es un actor sin usuario (`01_product_discovery.md` sección 3).
- Módulo `settings` (dueño de la sección `tv`): esquema Pydantic de la sección con `device_token_hash`, `token_last4`, `rotated_at`, `refresh_seconds` (10 a 300, por defecto 30); `validate_section("tv", value)` rechaza `device_token` y `device_token_hash` en `PATCH`. La sección deja de responder 404 `section_not_available` en v0.5 (US-054). Control de concurrencia por `version` (N-17).
- `core/security`: se usan (o se agregan si US-041 no los dejó genéricos) `generate_token(nbytes=32) -> str` (base64url), `hash_token(token) -> str` y `token_matches(token, token_hash) -> bool` en tiempo constante. Son los mismos que usan los `OneTimeToken` de EP-04; es una función genérica del núcleo, no de un dominio.
- Módulo `tv`: `router.py`, `schemas.py`, `service.py`, sin `models.py` (mapa de contextos 1.16). Composición de solo lectura permitida: `settings.service.verify_tv_token`, `wods.service.today()` y `results.service.leaderboard(wod_id, level=None, sex=None, limit=50, offset=0)`. No importa models de nadie.
- Proyección: `tv.to_public_board(wod, leaderboard) -> TvBoard` es pura y construye la respuesta desde una lista blanca de campos (`date`, `wod.title`, `wod.score_type`, `wod.time_cap_s`, `movements[].name/reps/load_rx_m_kg/load_rx_f_kg`, `leaderboard[].position/display_name/level/score`); `member_id`, sexo y cualquier otro campo nunca salen. El esquema Pydantic de salida usa `extra = "forbid"`.
- Seguridad de ruta: `GET /api/v1/tv/today` ya está en la lista blanca exacta de `test_every_route_has_role.py` (US-035); se agrega una aserción de que es la única ruta de la lista blanca con la dependencia `require_device_token`.
- Rate limit: `core/ratelimit.py` con clave por IP real (`TRUSTED_PROXIES`, N-14), 12 por minuto; responde 429 con el envelope de error.
- Sin bus de cifrado: la TV no ve campos cifrados.
- Auditoría: la regeneración del token queda auditada en `settings.settings_sections` con el hash en `before`/`after`, nunca el token.

## Tablas y migraciones

- No hay migraciones. La sección `tv` vive en `settings.settings_sections` (JSON validado, `0005_settings`). El rango 0080 a 0084 queda libre.

## Services y eventos

- `settings.service.tv_regenerate_token(by) -> {token, url}`: genera con `core.security.generate_token`, guarda `hash_token(token)`, `token_last4` y `rotated_at` (UTC), sube `version`, audita y devuelve el token en claro una única vez; `url = <FRONT_BASE_URL>/tv?token=<token>`.
- `settings.service.verify_tv_token(token) -> bool`: lee la sección sin caché y compara con `core.security.token_matches`.
- `settings.service.get_section("tv")` devuelve solo `token_last4`, `rotated_at`, `refresh_seconds`.
- `tv.service.today(token) -> TvBoard`: verifica el token (401 genérico `invalid_device_token` si falla, sin revelar si existió), pide `wods.service.today()` y, si hay WOD, `results.service.leaderboard` con todos los niveles y sexos, máximo 50 filas; devuelve `to_public_board(...)`. Sin WOD: `wod = null`, `leaderboard = []`.
- Funciones puras: `tv.to_public_board(wod, leaderboard)`, `tv.display_name(first_name, last_name) -> "Ana P."`.
- Dependencia FastAPI `require_device_token` en `tv/router.py` que lee `X-Device-Token`.
- Eventos: ninguno emitido ni consumido.

## Endpoints

- `GET /api/v1/settings/tv` — roles: admin
- `PATCH /api/v1/settings/tv` — roles: admin
- `POST /api/v1/settings/tv/regenerate-token` — roles: admin
- `GET /api/v1/tv/today` — roles: ninguno (lista blanca), token de dispositivo obligatorio en `X-Device-Token`

## Componentes de front

- `web/src/features/system/components/TvTokenPanel.tsx` en la pestaña TV de `ConfigPage.tsx`: `token_last4`, `rotated_at` en hora de Bogotá, `refresh_seconds`, botón "Regenerar token" con `ConfirmModal`, enlace copiable que solo existe en la respuesta de la regeneración; hooks `useTvSettings` y `useRegenerateTvToken` en `web/src/features/system/api.ts`.
- `web/src/features/tv/`: `api.ts` (`useTvBoard` con TanStack Query, `refetchInterval = refresh_seconds`, tras 401 pasa a 5 minutos, con error de red conserva los últimos datos), `lib/deviceToken.ts` (lee la query una vez, guarda en `localStorage` con try/catch, limpia la URL con `history.replaceState`), `pages/TvPage.tsx` en `web/src/layouts/TvLayout.tsx` (1920 × 1080, solo oscuro, sin elementos interactivos, cursor oculto, texto mínimo de 28 px, rotación de páginas de 15 filas por refresco), estados "Sin WOD publicado", "Token inválido. Pide un enlace nuevo en Configuración" y "Sin conexión, mostrando la última información".
- `formatScore` compartido con resultados (`web/src/features/results/lib/formatScore.ts`): `4:05`, `5 + 12`, `150 reps`, `100 kg`, marca de time cap.
- Ruta pública `/tv` en `web/src/routes.tsx` fuera de las guardas de sesión; la página no usa el cliente con refresh de sesión del panel.
- Pruebas: Vitest de `TvPage` con respuestas simuladas (200, 401, red caída, `wod: null`) y de `deviceToken`; Playwright con captura en 1920 × 1080 y prueba de memoria de 12 horas con reloj acelerado (`web/tests/e2e/tv-soak.spec.ts`).

## Worker, CLI e infraestructura

- `infra/nginx/default.conf`: `log_format apex_noquery` que registra `$uri` en vez de `$request_uri`, aplicado a `location /api/v1/tv/` (N-44) y a `location = /tv`; prueba de configuración con `nginx -t` y una petición de prueba que verifica que el log no contiene `token=`.
- La cabecera `X-Device-Token` no se registra en los logs JSON del API (`core/logging.py` ya filtra cabeceras sensibles; se agrega esta).
- Worker y CLI: nada.

## Dependencias

- EP-22 · US-168 (`wods.service.today`) y US-171 (`results.service.leaderboard` y `leaderboard_order`).
- EP-05 · US-054 (secciones validadas, `version`, `section_not_available`).
- EP-03 · US-035 (lista blanca de rutas), rate limit de `core/ratelimit.py` (US-036 o la que lo creó), `TRUSTED_PROXIES` (N-14).
- EP-04 · US-041 (generador y hash de tokens en `core/security`).
- EP-06 · US-062 (`TvLayout`), `ConfirmModal`.
- EP-20 (TLS) no es requisito: la TV funciona en la LAN (riesgo aceptado en `04_architecture_decision.md` sección 8).

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, sale US-177 completa y el panel de la pestaña TV.
- Token filtrado muestra nombres con inicial y marcas: riesgo aceptado por la arquitectura — mitigación: rotación inmediata desde Configuración sin caché.
- La URL `/tv?token=…` queda en el historial del navegador de la TV y pasaba por el log de Nginx de la página: N-44 solo nombra `/api/v1/tv/` — mitigación: mismo formato sin query en `location = /tv` y limpieza de la query en el front.
- `localStorage` puede no estar disponible (modo kiosco con almacenamiento bloqueado) — mitigación: si falla, el token se mantiene en memoria mientras la página esté abierta y se muestra "Token inválido" tras un reinicio.
- Sin TLS hasta EP-20 el token viaja en claro por la LAN — mitigación: riesgo aceptado; rotación periódica.
- Prueba de 12 horas lenta en CI — mitigación: reloj acelerado y ejecución en job nocturno separado.

## Estado y estimación por historia

- US-175 · Token de dispositivo de TV — **READY** — 8 h — Sección `tv` con hash del token por `core/security`, regeneración auditada sin el token en claro (N-44).
- US-176 · Endpoint público de TV — **READY** — 13 h — Módulo `tv` sin models; token solo en `X-Device-Token`, rate limit 12/min y proyección de lista blanca (N-44, Q22).
- US-177 · Pantalla de TV — **READY** — 14 h — Página en `TvLayout` con token en `localStorage` y query limpia (N-44), refresco, estados y prueba de 12 h.

## Total de la épica

- **Total: 35 h**
