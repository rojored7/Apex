# US-011 · Como equipo quiero toda la configuración en `Settings` leída desde `.env` y validada al arrancar para que el sistema nunca arranque a medias con una variable faltante

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/config.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero una clase `Settings` de pydantic-settings que lea todo desde `.env` y falle al arrancar si falta una variable obligatoria o tiene un valor inválido
para que un error de configuración se vea en el primer segundo y no a mitad de una venta

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** "Seguridad" de `CLAUDE.md` (nada de secretos en el código; todo por `.env`); estructura `core/config.py`.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `core/config.py` con `Settings(BaseSettings)` y `model_config = SettingsConfigDict(env_file=".env", extra="forbid")`; campos tipados (`DATABASE_URL: SecretStr`, `JWT_PRIVATE_KEY_PATH: FilePath`, `JWT_PUBLIC_KEY_PATH: FilePath | None = None` (opcional; si falta, se deriva de la privada), `CRYPTO_PROVIDER: Literal["local", "openbao"]`, `CRYPTO_LOCAL_KEK_PATH: Path`, `TZ_DISPLAY: str = "America/Bogota"`, `UPLOADS_DIR: Path`, `CORS_ORIGINS: list[str]`, `LOG_LEVEL`, `ENV`, `TRUSTED_PROXIES`, `COOKIE_SECURE`, `FRONT_BASE_URL`); lista `NON_API_ENV_VARS` (variables que la API no lee y que `extra="forbid"` no debe rechazar: `WEB_PORT` (A-4), `POSTGRES_*`, `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`, que consume la CLI); validador que exige `CRYPTO_LOCAL_KEK_PATH` cuando el proveedor es `local`; función `get_settings()` con caché; secretos como `SecretStr` para que `repr` no los muestre.
- **Front:** No aplica.

## Criterios de aceptación

1. Con un `.env` completo, `get_settings()` devuelve un objeto con todos los campos tipados.
2. Si falta una variable obligatoria, la creación de la app falla con un error que nombra la variable y ningún socket queda abierto.
3. Si `CRYPTO_PROVIDER=local` y falta `CRYPTO_LOCAL_KEK_PATH`, el arranque falla.
4. Un valor inválido (por ejemplo `CRYPTO_PROVIDER=aws`) falla con mensaje claro.
5. Ningún valor secreto aparece al imprimir o loguear `Settings` (se muestran como `**********`).
6. No hay valores por defecto para secretos ni para `DATABASE_URL`.
7. Una variable de `NON_API_ENV_VARS` (por ejemplo `WEB_PORT`) no hace fallar el arranque; una variable desconocida sí.

## Escenarios BDD

```gherkin
# language: es
Característica: Configuración validada al arrancar

  Escenario: Configuración completa
    Dado un ".env" con todas las variables obligatorias
    Cuando arranca el api
    Entonces Settings expone los valores tipados
    Y el arranque continúa

  Escenario: Variable obligatoria faltante
    Dado un ".env" sin "DATABASE_URL"
    Cuando arranca el api
    Entonces el proceso termina con un error que menciona "DATABASE_URL"

  Escenario: Secretos ocultos en la representación
    Dado Settings cargado con una contraseña de base de datos
    Cuando se imprime el objeto
    Entonces la contraseña no aparece en el texto
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** validador de proveedor y KEK.
- **Pruebas:** `tests/core/test_config.py` con `monkeypatch` de variables de entorno.
- **Archivos principales:** `api/src/app/core/config.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest.

## INVEST

- **Independiente:** no depende de base de datos.
- **Negociable:** nombres y agrupación de campos.
- **Valiosa:** evita arranques silenciosamente rotos.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** pruebas con variables de entorno.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas en verde; cobertura de 80 % o más en lo tocado
- [ ] `.env.example` actualizado (US-007)
- [ ] Revisión de PR aprobada
