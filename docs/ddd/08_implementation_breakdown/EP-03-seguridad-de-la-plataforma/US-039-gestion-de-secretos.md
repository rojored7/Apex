# US-039 · Gestión de secretos y validación al arrancar — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-039-gestion-de-secretos.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core/config e infraestructura (`api/src/app/core/config.py`, `api/.dockerignore`, `.env.example`, `.github/workflows/ci.yml`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Están definidas las variables sensibles, los archivos de llave que se verifican, las exclusiones de la imagen y el escaneo en CI. El único supuesto, la herramienta de escaneo, se resuelve con una de licencia permitida (gitleaks, MIT) sin cambiar nada del sistema. DECISIONES Q12 y N-15 refuerzan la historia sin contradecirla.

## Resumen

`missing_secrets(settings)` es una función pura que devuelve los nombres de variable cuyo valor o archivo falta: `JWT_PRIVATE_KEY_PATH` siempre, `CRYPTO_LOCAL_KEK_PATH` cuando `CRYPTO_PROVIDER=local` y la contraseña de `DATABASE_URL`. El lifespan de `create_app()` y el arranque del worker la llaman y abortan con la lista de nombres, nunca con valores. Los campos sensibles son `SecretStr`. `api/.dockerignore` excluye `.env*` (salvo `.env.example`), `*.pem`, `*.key` y `keys/`. En CI, gitleaks escanea el repositorio y el sistema de archivos exportado de la imagen del api, y una prueba lista la imagen buscando `.env`, llaves privadas y la KEK. Otra prueba verifica que cada campo de `Settings` aparece en `.env.example`.

## Correcciones aplicadas por DECISIONES.md

- La historia habla de "credenciales" sin decir dónde viven las de los canales de aviso → los secretos de SMTP, Telegram y VAPID van solo en `.env` y nunca en la base; `settings.channels` guarda solo lo no secreto. Esta historia deja el mecanismo (`SecretStr` y `missing_secrets` condicionado al canal habilitado) para que EP-14 solo agregue los campos: corregido por DECISIONES Q12.
- La historia no menciona actores técnicos → no existe `SYSTEM_ACTOR_ID` ni contraseña para el usuario técnico. `SYSTEM_USER_ID` es una constante de código, no un secreto ni una variable de `.env`. El seed del admin inicial usa una variable de un solo uso: corregido por DECISIONES N-15.

## Validación contra el dominio

- Sin aggregates, eventos ni RN-xx de negocio. Protege la KEK de la que depende RN-13 y la llave JWT de la que depende RN-15.
- Función pura: `missing_secrets(settings: Settings) -> list[str]`, que usa una función de existencia de archivo inyectable para la prueba.

## Validación contra la arquitectura

- Coincide con `CLAUDE.md` (nada de secretos en código ni en imágenes; `.env.example` versionado) y con `04_architecture_decision.md` sección 6 (llaves por volumen o `.env`).
- `core/config.py` no importa primitivas criptográficas: solo comprueba que el archivo existe y se puede leer, y que su modo no es más abierto que 600 (aviso, no error, porque en Windows o WSL los modos no siempre se respetan en desarrollo). Cargar la llave es trabajo de US-033 y de US-023.
- Criterio 3 ("la imagen no contiene archivos `.pem` ni `.key`"): la imagen base y `certifi` (que llega con httpx) traen certificados públicos de CA con extensión `.pem` (`/etc/ssl/certs/*.pem`, `site-packages/certifi/cacert.pem`). Un certificado público de CA no es un secreto. La prueba busca **llaves privadas por contenido** (`-----BEGIN .*PRIVATE KEY-----`) en toda la imagen y **cualquier** `.pem` o `.key` dentro de `/app`, con una lista de exclusión explícita y comentada para los paquetes de CA. Es una precisión del criterio, no un cambio de alcance.
- Sin tablas, sin rol, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · En `api/src/app/core/config.py`: marcar como `SecretStr` `POSTGRES_PASSWORD`, `SEED_ADMIN_PASSWORD` y todo campo futuro con sufijo `_PASSWORD`, `_TOKEN` o `_SECRET` (un validador de clase falla si un campo con esos sufijos no es `SecretStr`); `DATABASE_URL` como `PostgresDsn`, con la contraseña oculta en `repr` mediante un `__repr_args__` propio — 1 h
- [ ] T2 · Función pura `missing_secrets(settings, exists=Path.is_file) -> list[str]` y `check_secrets_or_exit(settings)`, que lanza `StartupError("Faltan secretos: JWT_PRIVATE_KEY_PATH, ...")` con nombres ordenados; se llama en el lifespan de `create_app()` (US-020) antes de cargar llaves, y en `worker/main.py` — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/core/test_config_secrets.py`: `missing_secrets` con todo presente → `[]`; sin archivo JWT → `["JWT_PRIVATE_KEY_PATH"]`; proveedor `local` sin KEK → incluye `CRYPTO_LOCAL_KEK_PATH`; proveedor `openbao` sin KEK → no la pide; `repr(settings)` y `settings.model_dump_json()` no contienen la contraseña de prueba y sí `**********`; el mensaje de `StartupError` no contiene valores — 1,5 h
- [ ] T4 · `api/tests/core/test_env_example.py`: parsea `.env.example` y exige que cada campo de `Settings.model_fields` aparezca como clave (criterio 5), y que ningún valor de ejemplo parezca real: ningún PEM, ningún valor de 32 bytes en base64 o más; los secretos dicen `cambiar-esto` — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T5 · Prueba de log en `api/tests/core/test_config_secrets.py`: arrancar `create_app()` con `caplog` no deja en los registros el valor de ningún `SecretStr` ni el contenido de los archivos de llave — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T6 · `api/.dockerignore` (US-005): `.env`, `.env.*`, `!.env.example`, `*.pem`, `*.key`, `keys/`, `secrets/`, `**/__pycache__`; y la raíz `.gitignore` con las mismas llaves y `.env` — 0,5 h
- [ ] T7 · `scripts/ci/check-image-secrets.sh <imagen>`: `docker create`, `docker export | tar -x` en un directorio temporal; falla si existe algún `.env`, si un archivo contiene `-----BEGIN .*PRIVATE KEY-----` o si hay `.pem` o `.key` bajo `app/`; excluye de forma explícita `etc/ssl/certs`, `usr/share/ca-certificates` y `**/certifi/cacert.pem`; termina con `gitleaks dir` sobre el mismo directorio — 2 h
- [ ] T8 · `.github/workflows/ci.yml`: job `secrets-scan` con `gitleaks git` sobre todo el historial del PR (configuración `.gitleaks.toml` con la regla de llaves privadas activa y una lista permitida solo para los fixtures de prueba generados en tiempo de ejecución) y el paso `check-image-secrets.sh` después del build de la imagen del api; documentar la licencia MIT de gitleaks en `NOTICE` como herramienta de CI — 1,5 h
- [ ] T9 · PR de control (en la descripción del PR): agregar `tests/fixtures/leak.pem` con una llave Ed25519 recién generada debe hacer fallar `secrets-scan` (criterio 4); después se descarta la rama — 0,5 h

### Seguridad
- [ ] T10 · Revisión: ningún `print` ni log de `settings` completo; `infra/compose.yml` monta `keys` como volumen de solo lectura en `api` y `worker`; el `.env` de producción no se copia en ninguna etapa del `Dockerfile` (revisar `COPY . .`) — 0,5 h

## Orden de ejecución
1. T3 (pruebas puras en rojo)
2. T4
3. T1
4. T2
5. T5
6. T6
7. T7
8. T8
9. T9
10. T10

## Dependencias técnicas
- US-011 · Configuración desde .env: `Settings`, `SecretStr` y `extra="forbid"`.
- US-005 · Dockerfile del api y Compose: imagen, `.dockerignore` y volumen `keys`.
- US-007 · .env.example y README: archivo que valida T4.
- US-003 · Pipeline de CI: jobs donde se agregan el escaneo y la inspección.
- US-004 · Chequeo de licencias: gitleaks como herramienta de CI con licencia permitida.
- US-033 y US-023: cargan los archivos de llave cuya presencia se valida aquí.

## Endpoints
- Ninguno.

## Riesgos
- Falsos positivos de gitleaks en fixtures o en la documentación (por ejemplo, ejemplos de PEM en `docs/`) — mitigación: los fixtures de llaves se generan en tiempo de prueba y nunca se versionan; la lista permitida de `.gitleaks.toml` es explícita y revisada.
- Discrepancia de nombres entre historias: US-007 usa `SEED_ADMIN_EMAIL` y `SEED_ADMIN_PASSWORD`, y US-041 usa `APEX_SEED_ADMIN_EMAIL` y `APEX_SEED_ADMIN_PASSWORD` — mitigación: T4 obliga a que `.env.example` y `Settings` coincidan; hay que fijar un solo nombre (se propone el de US-007, sin prefijo, coherente con el resto de variables).
- Modos de archivo en WSL o Windows no fiables — mitigación: un modo más abierto que 600 es solo un aviso en el log de arranque (no bloquea); el modo correcto lo garantiza `cli init-keys` (US-023) y el volumen de US-005.

## Estimación
- Backend: 2 h
- Front: 0 h
- Pruebas: 3 h
- DevOps / seguridad: 5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_config_secrets.py tests/core/test_env_example.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker build -t apex-api:ci api && bash scripts/ci/check-image-secrets.sh apex-api:ci` termina con código 0
- [ ] Arrancar el API sin el archivo de `JWT_PRIVATE_KEY_PATH` termina con código distinto de 0 y el mensaje contiene `JWT_PRIVATE_KEY_PATH` y ningún valor
- [ ] El PR de control de T9 falla en `secrets-scan`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.config --cov-fail-under=80`
