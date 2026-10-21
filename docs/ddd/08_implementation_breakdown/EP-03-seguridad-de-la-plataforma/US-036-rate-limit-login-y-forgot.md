# US-036 · Rate limit de login y forgot — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-036-rate-limit-login-y-forgot.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core/ratelimit, transversal (`api/src/app/core/ratelimit.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Hay límite (5 por 60 s), clave (IP y ruta), algoritmo (ventana deslizante en memoria), código de error y forma de obtener la IP real. DECISIONES N-14 acepta `TRUSTED_PROXIES`. No hay tablas. Los endpoints que se limitan son de EP-04 y solo declaran la dependencia.

## Resumen

`core/ratelimit.py` trae la función pura `allow(history, now, limit, window_s)`, un almacén en memoria acotado de marcas de tiempo por (bucket, IP), `client_ip(request, trusted_proxies)` y la fábrica de dependencias `rate_limit(bucket, limit=5, window_s=60)`. La dependencia corre antes del handler, así que el login no evalúa la contraseña cuando hay 429 (US-042, criterio 5). Responde 429 con el envelope `rate_limited` y `Retry-After`. Los tiempos vienen del `Clock` (US-013). La misma fábrica sirve para la TV en v0.5 (12 por minuto, N-44).

## Correcciones aplicadas por DECISIONES.md

- Supuesto: "variable `TRUSTED_PROXIES` para decidir cuándo confiar en `X-Forwarded-For`" → aceptado. Se agrega a `Settings` y a `.env.example` como lista de CIDR: corregido por DECISIONES N-14 (aceptado).
- Login fallido con un correo que no existe → solo log y rate limit, no auditoría. El limitador lo cuenta igual que cualquier intento: corregido por DECISIONES N-31 (aplica a US-042 y US-107).

## Validación contra el dominio

- Sin aggregates ni invariantes de negocio. Protege `User` contra fuerza bruta (RN-15, indirecto).
- Eventos: ninguno.
- Función pura: `allow(history: Sequence[float], now: float, limit: int = 5, window_s: int = 60) -> tuple[bool, int]`. Devuelve si se permite y los segundos de `Retry-After` (`ceil(history[0] + window_s - now)` cuando se rechaza). La ventana es deslizante: cuentan los intentos con `now - t < window_s`.

## Validación contra la arquitectura

- `core/ratelimit.py` aparece en el árbol de `05_service_design.md` sección 2; no importa módulos.
- Es una dependencia por ruta y no un middleware global. Así solo afecta a las rutas que la declaran, corre antes del cuerpo del handler y es visible en el árbol de dependencias. La historia dice "middleware" en INVEST; el comportamiento observable es el mismo.
- IP real: si `request.client.host` está en `TRUSTED_PROXIES`, se recorre `X-Forwarded-For` de derecha a izquierda y se toma la primera IP que no sea de confianza. Si no, se usa `request.client.host` y se ignora la cabecera (criterio 4). Funciona con Nginx solo (v0.1) y con Caddy delante (v0.3).
- Error con el envelope de US-017: `TooManyRequestsError(code="rate_limited", status=429)`, subclase de `DomainError`, más la cabecera `Retry-After`.
- Un solo proceso: Uvicorn con `--workers 1` (riesgo aceptado en la épica).
- Sin tablas, sin auditoría, sin bus, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · En `api/src/app/core/config.py`: `TRUSTED_PROXIES: list[IPv4Network | IPv6Network]`, separada por comas, por defecto vacía (no confiar en nadie), con la red de Docker de `infra/compose.yml` (por ejemplo `172.16.0.0/12`) documentada en `.env.example`; `RATE_LIMIT_MAX_KEYS: int = 10000` — 1 h
- [ ] T2 · Función pura `allow(...)` en `api/src/app/core/ratelimit.py` — 1 h
- [ ] T3 · `client_ip(request, trusted_proxies) -> str` (pura sobre `client.host` y la cabecera) — 1 h
- [ ] T4 · `SlidingWindowStore`: `dict[(bucket, ip), deque[float]]` con poda de marcas viejas en cada acceso, tope `RATE_LIMIT_MAX_KEYS` (expulsa la clave con la marca más antigua) y `asyncio.Lock`; método `hit(key, now, limit, window_s) -> tuple[bool, int]`, que registra todo intento procesado, exitoso o fallido (criterio 5); el intento rechazado con 429 no se registra, para que la ventana se libere 60 s después del primer intento como piden el criterio 2 y el escenario "La ventana se libera" — 1,5 h
- [ ] T5 · Fábrica `rate_limit(bucket: str, limit: int = 5, window_s: int = 60)` que devuelve una dependencia de FastAPI que lee el `Clock` de la app y lanza `TooManyRequestsError` con `Retry-After`; mensaje genérico "Demasiados intentos. Espera un momento." (criterio 6) — 1 h
- [ ] T6 · Declarar la dependencia en `POST /api/v1/auth/login` (bucket `login`) y `POST /api/v1/auth/forgot` (bucket `forgot`) cuando existan US-042 y US-048. Es una línea en `modules/auth/router.py`; si esta historia se cierra antes, se prueba con rutas sintéticas — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica (ver T6).

### Tests unitarios puros
- [ ] T7 · `api/tests/core/test_ratelimit.py`: `allow` con 0, 4, 5 y 6 marcas; marca justo en `now - 60` (fuera) y en `now - 59,999` (dentro); `Retry-After` correcto y mayor o igual a 1; `client_ip` sin proxy y con cabecera falsa → IP del socket; proxy de confianza con `X-Forwarded-For: 1.2.3.4, 10.0.0.5` (10.0.0.5 de confianza) → `1.2.3.4`; cabecera mal formada → IP del socket — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- [ ] T8 · Con app de prueba, `FrozenClock` y `httpx.AsyncClient` (`ASGITransport(client=("10.1.1.1", 1234))`): 5 POST → procesados, el sexto → 429 `rate_limited` con `Retry-After`; avanzar el reloj 61 s → procesado; `login` y `forgot` con contadores independientes; dos IP independientes; cliente no confiable con `X-Forwarded-For` rotando → bloqueado por su IP real; el 429 es idéntico para un correo existente y uno inexistente — 1,5 h

### Tests de arquitectura
- [ ] T9 · Agregar a `test_every_route_has_role.py` (US-035) una comprobación de que `POST /api/v1/auth/login` y `POST /api/v1/auth/forgot` tienen en su árbol una dependencia de `rate_limit` (marca `__apex_rate_limit__`), para que el límite no se pierda en un refactor — 0,5 h

### Front
- No aplica (el mensaje en Login es de US-042).

### DevOps
- [ ] T10 · Verificar que `infra/nginx/default.conf` (US-006) fija `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` y que el comando del api en `api/Dockerfile` o `compose.yml` usa `--workers 1`; `TRUSTED_PROXIES` en el `.env` de `compose.yml` con la red interna — 0,5 h

### Seguridad
- [ ] T11 · Revisión: la memoria del almacén está acotada (no hay DoS por IP falsas, porque las falsas no se aceptan sin proxy de confianza); el log del 429 registra la IP y el bucket, nunca el correo; un `TRUSTED_PROXIES` vacío por defecto falla cerrado (todo sale de la IP del proxy y el límite se vuelve global, más restrictivo, no más abierto) — 0,5 h

## Orden de ejecución
1. T7 (pruebas puras en rojo)
2. T2
3. T3
4. T1
5. T4
6. T8 (en rojo)
7. T5
8. T6
9. T9
10. T10
11. T11

## Dependencias técnicas
- US-020 · create_app: app y `Clock` inyectado.
- US-013 · Reloj: `FrozenClock` para la ventana.
- US-017 · Envelope de errores: `DomainError` para el 429.
- US-006 · Nginx: cabecera `X-Forwarded-For`.
- US-042 y US-048 (consumidores): declaran la dependencia en login y forgot; US-048 ya depende de esta historia.

## Endpoints
- `POST /api/v1/auth/login` — roles: público (lista blanca), límite 5 por minuto por IP
- `POST /api/v1/auth/forgot` — roles: público (lista blanca), límite 5 por minuto por IP

## Riesgos
- Con `TRUSTED_PROXIES` mal configurado, todas las peticiones parecen venir de Nginx y el límite pasa a ser global, de modo que cinco errores de cualquiera bloquean a todos — mitigación: valor documentado en `.env.example`, prueba de humo que hace 6 intentos desde dos contenedores distintos y log de arranque que muestra las redes de confianza.
- El contador se reinicia con el proceso y no se comparte entre réplicas — mitigación: riesgo aceptado en la épica; un solo proceso.
- Estimación de 11 h, 1 h por encima de la banda de 2 puntos, por el algoritmo de proxies de confianza y el almacén acotado: impacto menor en el sprint — mitigación: se acepta el desvío y queda declarado.
- La recepción del gimnasio comparte IP pública o NAT con los socios — impacto bajo porque el API está en la LAN; mitigación: el límite es por IP local.

## Estimación
- Backend: 6 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 1 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_ratelimit.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Con el stack levantado: `for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"x@y.co","password":"nada-nada-nada"}'; done` imprime cinco `401` y un `429`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.ratelimit --cov-fail-under=80`
