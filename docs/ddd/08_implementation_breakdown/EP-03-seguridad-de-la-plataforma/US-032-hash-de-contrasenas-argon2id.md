# US-032 · Hash de contraseñas con argon2id — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-032-hash-de-contrasenas-argon2id.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core/security, transversal (`api/src/app/core/security.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Las tres funciones, la política mínima y el lugar del código están definidos. DECISIONES N-10 cierra el único supuesto de la historia (12 caracteres) y agrega la lista corta de contraseñas comunes, que no cambia ningún contrato HTTP. No hay tablas ni endpoints.

## Resumen

Wrapper sobre `argon2-cffi` (`PasswordHasher` tipo `ID`) en `core/security.py` con `hash_password`, `verify_password` y `needs_rehash`, más la validación de política (`WeakPasswordError`). Los parámetros vienen de `Settings` con los valores por defecto de la librería. `argon2` solo se importa aquí (regla banned-api). Auth (US-041, US-042, US-045, US-048) es el único consumidor y traduce `WeakPasswordError` a 422.

## Correcciones aplicadas por DECISIONES.md

- La historia valida solo longitud mínima de 12 → además de los 12 caracteres, se rechaza una contraseña que esté en una lista corta de contraseñas comunes (comparación sin distinguir mayúsculas), sin otras reglas de composición: corregido por DECISIONES N-10.

## Validación contra el dominio

- Aggregate `User`: el campo `password_hash` (argon2id) lo persiste Auth; esta historia solo produce y verifica el valor. Coincide con `02_domain_model.md` 2.11.
- No hay invariantes RN-xx directas; apoya RN-15 indirectamente (sin credenciales robustas no hay control de acceso).
- Eventos emitidos y consumidos: ninguno.
- Funciones puras: `hash_password(plain) -> str`, `verify_password(hash, plain) -> bool`, `needs_rehash(hash) -> bool` y `validate_password_policy(plain) -> None` (lanza `WeakPasswordError`). Son puras salvo la sal aleatoria, y se prueban sin base.

## Validación contra la arquitectura

- Dueño: `core/security.py` (shared kernel restringido). Ningún módulo hashea por su cuenta.
- banned-api: `argon2` permitido solo en `core/security` y `core/crypto`; la prueba de imports prohibidos (US-002) debe seguir verde.
- Sin llamadas service a service, sin eventos, sin bus de criptografía (no es cifrado reversible), sin tablas ni `__audited__`.
- Rol y paginación: no aplican.
- Costo de CPU: el service de auth debe envolver `hash_password` y `verify_password` en `anyio.to_thread.run_sync` para no bloquear el event loop; se documenta en el docstring.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · En `api/src/app/core/config.py` agregar `ARGON2_TIME_COST: int = 3`, `ARGON2_MEMORY_COST_KIB: int = 65536`, `ARGON2_PARALLELISM: int = 4` (valores por defecto de argon2-cffi) y `PASSWORD_MIN_LENGTH: int = 12`, con validadores de rango (mayores que 0) y entradas en `.env.example` — 1 h
- [ ] T2 · En `api/src/app/core/security.py`: `WeakPasswordError(reason: Literal["too_short", "too_common"])`, `validate_password_policy(plain: str) -> None`, `hash_password(plain: str) -> str` (valida política y usa `PasswordHasher(type=Type.ID, ...)` construido desde `Settings`), `verify_password(hash: str, plain: str) -> bool` (captura `VerifyMismatchError`, `InvalidHashError` y `VerificationError` y devuelve `False`), `needs_rehash(hash: str) -> bool` (delegado a `check_needs_rehash`; hash malformado devuelve `True`) — 2 h
- [ ] T3 · Lista corta de contraseñas comunes en `api/src/app/core/common_passwords.txt` (unas 200 entradas de 12 caracteres o más, por ejemplo `contraseña123`, `123456789012`, `qwertyuiopas`, `apexcrossfit1`), cargada una vez en un `frozenset` en minúsculas; incluida en el paquete por `pyproject.toml` — 0,5 h
- [ ] T4 · Ayuda para US-042: `dummy_verify(plain: str) -> None` que verifica contra un hash ficticio precalculado al importar, para que un correo inexistente tarde lo mismo que uno real — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `api/tests/core/test_passwords.py` con parámetros bajos por fixture (`time_cost=1`, `memory_cost=8`): hash empieza por `$argon2id$`; dos hashes distintos; verificar correcta, incorrecta por mayúscula y hash malformado (`"no-es-un-hash"`, cadena vacía) sin excepción; `needs_rehash` verdadero con hash de memoria menor; 11 caracteres lanza `WeakPasswordError("too_short")`; contraseña común en otra capitalización lanza `"too_common"`; 12 caracteres no comunes pasa — 2 h
- [ ] T6 · Prueba de captura de log (`caplog`) que hashea y verifica y comprueba que ni la contraseña ni el hash aparecen en ningún registro, ni siquiera en el mensaje de `WeakPasswordError` — 0,5 h

### Tests de service con PostgreSQL
- No aplica (sin base; la persistencia del hash se prueba en US-041).

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T7 · Confirmar que `api/tests/architecture/test_banned_imports.py` (US-002) sigue verde y agregar un caso que falla si `argon2` aparece en `app/modules/**` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T8 · Verificar que `argon2-cffi` (MIT) pasa `pip-licenses` y que `common_passwords.txt` queda dentro de la imagen del api — 0,5 h

### Seguridad
- [ ] T9 · Revisión: mensaje de `WeakPasswordError` sin eco de la contraseña; parámetros nunca por debajo de los valores por defecto en producción (validador que lo impide salvo `ENV=test`); el hash nunca sale en `repr` de modelos ni en auditoría (lo cubre US-041 con `"***"`) — 0,5 h

## Orden de ejecución
1. T5 (pruebas puras en rojo)
2. T6
3. T1
4. T3
5. T2
6. T4
7. T7
8. T8
9. T9

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: lint banned-api y entorno de pruebas.
- US-011 · Configuración desde .env: los parámetros de argon2 viven en `Settings`.

## Endpoints
- Ninguno.

## Riesgos
- Parámetros de memoria altos en el servidor del gimnasio: un login tarda demasiado o agota memoria con varios intentos simultáneos — mitigación: valores por defecto de la librería (64 MiB, 3 iteraciones), el rate limit de US-036 y ejecución en hilo aparte.
- Contraseñas enormes (varios MB) cuestan CPU al hashear — mitigación: Nginx limita el cuerpo a 5 MB y los schemas de EP-04 deben fijar un `max_length` de la contraseña (se propone 128).
- Lista de comunes demasiado corta o en inglés — mitigación: incluir variantes locales (nombre del gimnasio, `colombia`, años) y revisarla en el PR.

## Estimación
- Backend: 4 h
- Front: 0 h
- Pruebas: 3 h
- DevOps / seguridad: 1 h
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_passwords.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run python -c "from app.core.security import hash_password; print(hash_password('Secreta-1234-x')[:10])"` imprime `$argon2id$`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.security --cov-fail-under=80`
