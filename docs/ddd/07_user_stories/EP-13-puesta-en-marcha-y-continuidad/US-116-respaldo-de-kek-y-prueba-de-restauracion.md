# US-116 · Como administrador quiero un procedimiento probado para respaldar la KEK y restaurar un backup para que el respaldo sirva de verdad el día que lo necesite

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** Crypto (KEK local) y contenedor `backup`; documentación en `docs/operacion/`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero un procedimiento escrito y una prueba automatizada que restaure un backup en una base vacía usando la KEK respaldada
para estar seguro de que puedo recuperar los datos cifrados de los socios

## Contexto de dominio

- **Aggregate / entidades:** CryptoKey (DEK envueltas en `crypto.crypto_keys`), KEK del `LocalFileProvider`.
- **Reglas que aplica:** RN-13; riesgo de EP-02 y EP-13 "perder la KEK equivale a perder todos los datos cifrados"; `CLAUDE.md` (KEK en archivo 600 fuera del repo; nada de secretos en imágenes).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** comando `cli export-kek --out <ruta>` que copia la KEK local a un archivo cifrado con una frase de paso (formato `age` con passphrase) para guardarlo fuera del servidor, y `cli verify-kek-backup <archivo>` que confirma, sin escribir nada, que la KEK respaldada desenvuelve las DEK registradas. Script `infra/backup/restore.sh` que restaura un `.sql.age` en una base vacía. Prueba automatizada en CI: base con socios cifrados → backup → base nueva vacía → restaurar → arrancar api con la KEK respaldada → leer un socio en claro con `reveal`. Documento `docs/operacion/respaldo-y-restauracion.md` paso a paso, en lenguaje simple, con dónde guardar la KEK (dos copias fuera del servidor) y la identidad `age`.
- **Front:** No aplica.

## Criterios de aceptación

1. `cli export-kek` pide la frase de paso por entrada interactiva (o `--passphrase-file`), nunca por argumento de línea de comandos, y produce un archivo que no contiene los 32 bytes de la KEK en claro.
2. `cli export-kek` y `cli verify-kek-backup` dejan una fila en `crypto_ops` (verbos `export` y `verify`) y en auditoría, sin material de llave.
3. `cli verify-kek-backup` termina con código 0 si la KEK del archivo desenvuelve todas las DEK `active` y `decrypt_only`, y con código distinto de 0 si alguna falla.
4. La prueba de restauración en CI restaura un backup en una base vacía y, con la KEK respaldada, el api arranca y descifra el documento de un socio de prueba; con una KEK distinta, el api no arranca y lo reporta en el log (sin imprimir la llave).
5. `restore.sh` se niega a restaurar sobre una base que tenga tablas de APEX con datos, salvo `--i-know-this-overwrites`.
6. El documento de operación existe, explica el procedimiento en pasos numerados y fue seguido una vez por alguien distinto de quien lo escribió (registro en el PR).
7. Ningún log, reporte ni salida de consola muestra la KEK, la frase de paso ni la identidad `age`.

## Escenarios BDD

```gherkin
# language: es
Característica: Respaldo de la KEK y restauración

  Escenario: Restaurar con la KEK respaldada
    Dado una base con el socio "Ana Pérez" de documento cifrado
    Y un backup "apex-20261021.sql.age"
    Y la KEK exportada con "cli export-kek"
    Cuando restauro el backup en una base vacía
    Y arranco el api con la KEK respaldada
    Entonces puedo mostrar en claro el documento de "Ana Pérez"

  Escenario: KEK equivocada
    Dado un backup restaurado en una base vacía
    Cuando arranco el api con una KEK distinta
    Entonces el api no arranca
    Y el log indica "no se pudo desenvolver la DEK" sin mostrar la llave

  Escenario: Verificar un respaldo de KEK inválido
    Dado un archivo de KEK respaldada de otra instalación
    Cuando ejecuto "cli verify-kek-backup kek.age"
    Entonces el comando termina con un código distinto de 0

  Escenario: Restaurar sobre una base con datos
    Dado una base con socios
    Cuando ejecuto "restore.sh" sin "--i-know-this-overwrites"
    Entonces el script se niega y no modifica la base
```

## Endpoints

- Ninguno. Comandos `cli export-kek`, `cli verify-kek-backup` y script `infra/backup/restore.sh`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** `crypto_ops` es append-only (US-024).
- **Funciones puras a probar:** ninguna; la lógica vive en `core/crypto` (export y verify usan el `KeyProvider`, no primitivas fuera de `core/crypto`).
- **Pruebas:** integración en CI de punta a punta (backup, restauración, arranque, reveal); prueba de que `export-kek` rechaza `--passphrase` en argumentos.
- **Archivos principales:** `api/src/app/cli.py`, `api/src/app/core/crypto/local_provider.py`, `infra/backup/restore.sh`, `docs/operacion/respaldo-y-restauracion.md`.

## Supuestos

- Supuesto: los comandos `export-kek` y `verify-kek-backup` y los verbos `export` y `verify` de `crypto_ops` no están en el catálogo de `02_domain_model.md` 2.13 (verbos: encrypt, decrypt, index, sign, verify, wrap, unwrap, rotate); se agrega `export` al enum. Requiere confirmación.
- Supuesto: la KEK exportada se cifra con passphrase `age` para que el respaldo fuera del servidor no sea la llave en claro.

## Dependencias

- US-114 · Backup nocturno cifrado.
- US-023 · KeyProvider y proveedor local (KEK y desenvoltura de DEK).
- US-074 · reveal (la prueba de restauración termina mostrando un documento en claro; agregado en consolidación)

## INVEST

- **Independiente:** usa el proveedor y el backup existentes.
- **Negociable:** el medio de respaldo de la KEK lo decide el gimnasio.
- **Valiosa:** convierte el backup en recuperable; sin esto, el backup no sirve.
- **Estimable:** pasos conocidos.
- **Pequeña:** dos comandos, un script y un documento.
- **Testeable:** prueba de punta a punta en CI.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Prueba de restauración de punta a punta en verde en CI
- [ ] Pruebas de router (no aplica)
- [ ] Front (no aplica)
- [ ] Migración (no aplica, salvo el valor `export` del enum de verbos si es enum de base)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría verificada para `export-kek` y `verify-kek-backup`
- [ ] Revisión de PR aprobada
