# US-036 · Como equipo quiero limitar a 5 intentos por minuto por IP el login y la recuperación para frenar la adivinación de contraseñas desde la LAN

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core/ratelimit`
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (el front de Login muestra el mensaje en US-042)

## Historia

Como equipo
quiero un limitador de 5 peticiones por minuto por IP en `POST /auth/login` y `POST /auth/forgot`
para que un atacante en la red del gimnasio no pueda probar contraseñas ni enumerar correos a gran velocidad

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `CLAUDE.md` Seguridad (rate limit en login); `04_architecture_decision.md` sección 6 (5 por minuto por IP en login y forgot, `slowapi` MIT o contador en memoria).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `ratelimit.allow(history, now, limit=5, window_s=60) -> bool` (ventana deslizante)

## Alcance

- **Backend:** contador en memoria con ventana deslizante por (IP, ruta), usando `Clock` para pruebas; la IP real se toma de `X-Forwarded-For` solo si la petición viene del proxy de confianza (Nginx, configurado por `TRUSTED_PROXIES`). Respuesta 429 con envelope `error.code = "rate_limited"` y cabecera `Retry-After`.
- **Front:** No aplica

## Criterios de aceptación

1. Cinco `POST /api/v1/auth/login` en 60 segundos desde la misma IP se procesan; el sexto recibe 429 con `error.code = "rate_limited"` y `Retry-After`.
2. Pasados 60 segundos desde el primer intento (con `FrozenClock` avanzado), un nuevo intento se procesa.
3. Los contadores de login y forgot son independientes entre sí y entre IPs.
4. Una cabecera `X-Forwarded-For` enviada directamente por un cliente (no por el proxy de confianza) se ignora.
5. El límite cuenta intentos exitosos y fallidos por igual.
6. El 429 no revela si el correo existe.

## Escenarios BDD

```gherkin
# language: es
Característica: Límite de intentos de acceso

  Escenario: Intentos dentro del límite
    Dado una IP sin intentos previos
    Cuando hace 5 intentos de login en un minuto
    Entonces los 5 reciben respuesta del login

  Escenario: Sexto intento bloqueado
    Dado una IP con 5 intentos de login en los últimos 60 segundos
    Cuando hace un sexto intento
    Entonces recibe 429 con error.code "rate_limited"
    Y la respuesta trae la cabecera Retry-After

  Escenario: La ventana se libera
    Dado una IP bloqueada
    Cuando pasan 61 segundos
    Entonces el siguiente intento se procesa

  Escenario: Cabecera falsificada
    Dado un cliente que envía X-Forwarded-For sin pasar por el proxy
    Cuando excede el límite
    Entonces se le bloquea por su IP real
```

## Endpoints

- `POST /api/v1/auth/login` — público — límite 5/min/IP — códigos: 429 adicional.
- `POST /api/v1/auth/forgot` — público — límite 5/min/IP — códigos: 429 adicional.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `allow` con historiales en el borde de la ventana.
- **Pruebas:** pura y de router con `FrozenClock`.
- **Archivos principales:** `api/src/app/core/ratelimit.py`, `api/tests/core/test_ratelimit.py`.
- **Riesgo aceptado:** el contador en memoria se reinicia con el proceso y no se comparte entre réplicas; hay un solo proceso.

## Supuestos

- Supuesto: variable `TRUSTED_PROXIES` para decidir cuándo confiar en `X-Forwarded-For` (N-14; se declara en US-011 y en `.env.example`, US-007).

## Dependencias

- US-020 · create_app, migraciones y health

## INVEST

- **Independiente:** se prueba con rutas de prueba antes de que exista Auth.
- **Negociable:** implementación propia o `slowapi`.
- **Valiosa:** frena fuerza bruta.
- **Estimable:** una función y un middleware.
- **Pequeña:** un día.
- **Testeable:** sexto intento 429.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
