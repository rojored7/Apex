# US-023 · Como equipo quiero un puerto KeyProvider con un proveedor local de KEK para envolver las llaves de datos sin atar el código a un custodio concreto

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/`, esquema `crypto`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero un puerto `KeyProvider` con la implementación `LocalFileProvider` y el comando `cli init-keys`
para envolver y desenvolver las DEK con una KEK guardada fuera del repositorio y poder cambiar a OpenBao en v0.2 sin tocar ningún módulo

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (consumidor del proveedor); puerto `KeyProvider` (`core/crypto/provider.py`).
- **Reglas que aplica:** RN-13 (datos sensibles cifrados por clase de dato); `CLAUDE.md` bus de criptografía puntos 3 y 6 (envelope, KEK en archivo 600 fuera del repo); `04_architecture_decision.md` sección 6 (llaves por volumen o `.env`, nunca en imagen).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna (las operaciones son de I/O y primitivas)

## Alcance

- **Backend:** `Protocol` `KeyProvider` con `wrap(dek) -> bytes`, `unwrap(wrapped) -> bytes`, `sign(key_ref, data) -> bytes`, `verify(key_ref, data, signature) -> bool`, `rotate(key_ref) -> KeyInfo`, `key_info(key_ref) -> KeyInfo`. `LocalFileProvider` lee una KEK de 32 bytes desde `CRYPTO_LOCAL_KEK_PATH` y envuelve con AES-256-GCM (AES Key Wrap aceptable si se documenta); llave de firma Ed25519 en archivo aparte. `cli init-keys` crea la KEK y la llave de firma con permisos 600 si no existen, y nunca sobrescribe una existente. Selección por `CRYPTO_PROVIDER=local`.
- **Front:** No aplica

## Criterios de aceptación

1. Existe `core/crypto/provider.py` con el `Protocol` `KeyProvider` y los seis métodos; `mypy --strict` lo valida.
2. `LocalFileProvider.unwrap(LocalFileProvider.wrap(dek)) == dek` para una DEK aleatoria de 32 bytes.
3. Un `wrapped` alterado en un byte hace fallar `unwrap` con un error de dominio (`CryptoError`), nunca devuelve bytes basura.
4. `cli init-keys` crea la KEK de exactamente 32 bytes con permisos `0o600` en la ruta configurada; si el archivo ya existe termina con código distinto de 0 y mensaje "la KEK ya existe", sin modificarlo.
5. Si `CRYPTO_LOCAL_KEK_PATH` no existe o tiene permisos más abiertos que 600, el arranque del API falla con mensaje explícito (sin imprimir el contenido).
6. La KEK vive en el volumen nombrado `keys` de Compose (US-005), nunca dentro de la imagen ni del repositorio; `.gitignore` y `.dockerignore` la excluyen.
7. `sign`/`verify` con la llave Ed25519 local: una firma válida verifica y una firma sobre datos alterados no verifica.
8. Ningún método del proveedor escribe la KEK ni una DEK en claro en logs (prueba que captura la salida de log).
9. El proveedor se obtiene por fábrica según `CRYPTO_PROVIDER`; un valor desconocido falla al arrancar.

## Escenarios BDD

```gherkin
# language: es
Característica: Proveedor local de llaves

  Antecedentes:
    Dado que CRYPTO_PROVIDER es "local"

  Escenario: Inicializar llaves en un servidor nuevo
    Dado que no existe archivo en CRYPTO_LOCAL_KEK_PATH
    Cuando el operador ejecuta "cli init-keys"
    Entonces se crea una KEK de 32 bytes con permisos 600
    Y se crea la llave de firma Ed25519 con permisos 600
    Y el comando termina con código 0

  Escenario: Envolver y desenvolver una DEK
    Dado una KEK local inicializada
    Cuando el bus envuelve una DEK aleatoria y luego la desenvuelve
    Entonces obtiene exactamente la misma DEK

  Escenario: No sobrescribir una KEK existente
    Dado que ya existe una KEK en CRYPTO_LOCAL_KEK_PATH
    Cuando el operador ejecuta "cli init-keys"
    Entonces el comando termina con código distinto de 0
    Y el archivo de la KEK no cambia

  Escenario: KEK con permisos inseguros
    Dado que la KEK tiene permisos 644
    Cuando arranca el API
    Entonces el arranque falla con el mensaje "permisos de la KEK inseguros"
    Y el contenido de la KEK no aparece en la salida

  Escenario: DEK envuelta alterada
    Dado una DEK envuelta con un byte cambiado
    Cuando el bus intenta desenvolverla
    Entonces recibe un CryptoError
```

## Endpoints

- Ninguno. Comando: `uv run python -m app.cli init-keys`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** no hay; pruebas de ida y vuelta, alteración, permisos.
- **Pruebas:** unitarias con directorio temporal; prueba de permisos con `os.stat`; prueba de log sin secretos; prueba de fábrica por `CRYPTO_PROVIDER`.
- **Archivos principales:** `api/src/app/core/crypto/provider.py`, `api/src/app/core/crypto/local_provider.py`, `api/src/app/cli.py`, `api/tests/crypto/test_local_provider.py`.
- **Riesgo:** perder la KEK equivale a perder todos los datos cifrados; el procedimiento de respaldo fuera del servidor lo cubre US-116. En Windows/WSL2 los permisos 600 no se respetan sobre NTFS: por eso el volumen nombrado de Docker.

## Supuestos

- Supuesto: la envoltura local usa AES-256-GCM con nonce aleatorio y la KEK como llave (el documento no fija el algoritmo de wrap); el algoritmo queda registrado en `crypto_keys.algorithm` de la llave envuelta.

## Dependencias

- US-011 · Configuración desde .env (rutas y `CRYPTO_PROVIDER`)
- US-005 · Dockerfile del api y Compose (volumen nombrado `keys`)

## INVEST

- **Independiente:** solo requiere configuración y el volumen; no depende de tablas.
- **Negociable:** el algoritmo exacto de wrap local se puede discutir; el puerto no.
- **Valiosa:** sin KEK no hay cifrado de datos personales (RN-13).
- **Estimable:** interfaz acotada y una implementación.
- **Pequeña:** un archivo de puerto, uno de proveedor y un comando.
- **Testeable:** ida y vuelta, alteración y permisos son verificables.

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
