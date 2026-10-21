# US-011 · Configuración desde `.env` validada al arrancar — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-011-configuracion-desde-env.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/config.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El contrato está completo: campos tipados, validador de proveedor y KEK, secretos ocultos y caché. Hay un ajuste técnico que no cambia el alcance. El `.env` compartido de US-007 trae variables que solo usa Compose (`POSTGRES_*`) o el CLI (`SEED_ADMIN_*`). Con `extra="forbid"` puro, el api no arrancaría en desarrollo. Se resuelve con una lista explícita de variables ajenas al api y se mantiene el rechazo de cualquier otra variable desconocida.

## Resumen

Se crea `core/config.py` con `Settings` de pydantic-settings, `get_settings()` con caché y un error de arranque legible que nombra la variable y nunca su valor. `DATABASE_URL` también se trata como secreto, porque lleva la contraseña de la base. Hay pruebas puras con `monkeypatch` y dos pruebas de arquitectura: nadie lee `os.environ` fuera de `config.py`, y `.env.example` cubre todos los campos obligatorios.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Ajuste técnico, no de DECISIONES: `DATABASE_URL` se declara `SecretStr` con validación de DSN `postgresql+asyncpg`. Un `PostgresDsn` muestra la contraseña en `repr`, y eso incumpliría el criterio 5.

## Validación contra el dominio

- No toca aggregates, invariantes RN ni eventos.
- Sostiene la regla "Seguridad" de `CLAUDE.md`: nada de secretos en el código, todo por `.env`.
- Función pura: `validate_crypto_provider(provider, kek_path) -> None`. Lanza un error si `provider == "local"` y `kek_path is None`.

## Validación contra la arquitectura

- Módulo dueño: `core/`. No depende de ningún módulo de negocio.
- Lint `banned-api`: no aplica, porque no usa primitivas criptográficas.
- Models cruzados, rol, paginación y auditoría: no aplican.
- `TZ_DISPLAY` queda como dato informativo. El "hoy" de negocio no se calcula con esta variable: lo calcula `core/clock.py` con `America/Bogota` fija (Q28, US-013).
- Los campos de otras historias se agregan en esas historias, cada una con su prueba: JWT (US-033), `TRUSTED_PROXIES` (US-036), OpenBao (US-133), `FRONT_BASE_URL` (US-047) y `APP_VERSION` (US-020).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `core/config.py`: `class Settings(BaseSettings)` con `DATABASE_URL: SecretStr` (validador que parsea con `PostgresDsn` y exige el esquema `postgresql+asyncpg`), `JWT_PRIVATE_KEY_PATH: FilePath`, `JWT_PUBLIC_KEY_PATH: FilePath`, `CRYPTO_PROVIDER: Literal["local", "openbao"]`, `CRYPTO_LOCAL_KEK_PATH: Path | None = None`, `TZ_DISPLAY: str = "America/Bogota"`, `UPLOADS_DIR: Path`, `CORS_ORIGINS: list[AnyHttpUrl]`, `LOG_LEVEL: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"`, y `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")`; ningún secreto ni `DATABASE_URL` lleva valor por defecto — 2 h
- [ ] T2 · Función pura `validate_crypto_provider(provider: str, kek_path: Path | None) -> None` y `model_validator(mode="after")` que la invoca — 1 h
- [ ] T3 · Constante `NON_API_ENV_VARS = frozenset({"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD"})` y `settings_customise_sources` que quita esas claves del origen dotenv antes de validar; cualquier otra clave desconocida del `.env` sigue fallando por `extra="forbid"` — 1 h
- [ ] T4 · `get_settings() -> Settings` con `functools.lru_cache(maxsize=1)`, `reset_settings_cache()` solo para pruebas y `ConfigError(missing: list[str], invalid: list[str])`, que convierte `ValidationError` a partir de `loc` y `type` (nunca de `input`) para que el mensaje nombre la variable sin mostrar su valor — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `tests/core/test_config.py`:
  - `.env` completo da campos tipados (criterio 1);
  - falta `DATABASE_URL` da un `ConfigError` que la menciona (criterio 2);
  - `local` sin KEK falla (criterio 3);
  - `CRYPTO_PROVIDER=aws` falla con mensaje claro (criterio 4);
  - `repr` y `str` de `Settings` no contienen la contraseña de la base (criterio 5);
  - introspección de `Settings.model_fields`: los `SecretStr` y `DATABASE_URL` no tienen valor por defecto (criterio 6);
  - `POSTGRES_PASSWORD` en el `.env` se acepta y una clave desconocida `FOO=1` falla.
  
  — 1,5 h
- [ ] T6 · `tests/core/test_config_error_message.py`: un DSN inválido con contraseña produce un `ConfigError` cuyo texto no contiene la contraseña — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica. El criterio 2 en la creación de la app (ningún socket abierto) se verifica en US-020, porque `create_app()` llama a `get_settings()` antes de montar nada.

### Tests de arquitectura
- [ ] T7 · `api/tests/architecture/test_no_os_environ.py`: búsqueda con `ast` de `os.environ`, `os.getenv` y `os.putenv` en `src/app/**` fuera de `core/config.py`; falla nombrando archivo y línea. También debe seguir verde `test_banned_imports.py` (US-002) — 1 h

### Front
- No aplica.

### DevOps
- [ ] T8 · `tests/core/test_env_example.py`: parsea `.env.example` (US-007) y verifica que contiene cada campo obligatorio de `Settings`. Así el ejemplo no se queda atrás cuando una historia agrega un campo — 1 h

### Seguridad
- [ ] T9 · Revisión:
  - `SecretStr` en `DATABASE_URL` y en cada secreto;
  - ningún secreto con valor por defecto;
  - el mensaje de `ConfigError` sin `input_value`;
  - `Settings` nunca se pasa entero a un log (lo refuerza US-018).
  
  — 0,5 h

## Orden de ejecución
1. T5 y T6 (pruebas en rojo)
2. T2 (función pura)
3. T1
4. T3
5. T4
6. T7
7. T8
8. T9

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: entorno, mypy estricto y `test_banned_imports.py`.
- US-007 · `.env.example` y README: T8 valida ese archivo.
- US-020 · create_app, migraciones y health: verifica el criterio 2 en el arranque real.

## Endpoints
- Ninguno.

## Riesgos
- Variables de Compose o del CLI en el mismo `.env`: con `extra="forbid"` puro, el api no arranca en desarrollo — mitigación: `NON_API_ENV_VARS` (T3), con una prueba para cada caso.
- Fuga de la contraseña en errores de validación: pydantic incluye `input_value` en el texto — mitigación: `ConfigError` construido solo con `loc` y `type` (T4, T6).
- `FilePath` exige que el archivo exista: si exportar OpenAPI (US-021) o un test construyen `Settings` sin llaves, fallan — mitigación: `create_app(settings=...)` acepta una configuración inyectada (US-020 y US-021).

## Estimación
- Backend: 5 h
- Front: 0 h
- Pruebas: 3,5 h
- DevOps / seguridad: 1,5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_config.py tests/core/test_config_error_message.py tests/core/test_env_example.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && env -u DATABASE_URL uv run python -c "from app.core.config import get_settings; get_settings()"` termina con un error que menciona `DATABASE_URL` y no muestra ningún valor
- [ ] `cd api && uv run python -c "from app.core.config import get_settings; print(get_settings())"` muestra `**********` en lugar de los secretos
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.config --cov-fail-under=80`
