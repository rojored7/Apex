# US-196 · Como administrador quiero que cada backup quede firmado con ML-DSA y se verifique antes de restaurarlo para saber que nadie lo alteró

- **Épica:** EP-26 · Cierre criptográfico post-cuántico
- **Bounded context:** Crypto (`core/crypto`, data_class `backup.signature`) y contenedor `backup`
- **Versión:** v1.0
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que el respaldo nocturno salga firmado y que la verificación diaria y la restauración comprueben esa firma
para poder confiar en que el backup que voy a restaurar es el que hizo el sistema

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey(purpose = sign, data_class = backup.signature, algorithm = ML-DSA-65, provider = openbao)`, `CryptoOp`.
- **Reglas que aplica:** único acceso a primitivas por el bus (`sign`, `verify`), el algoritmo lo decide la llave registrada (Q27 aplicado al backup: si OpenBao no ofrece ML-DSA, Ed25519 y rotación posterior), la llave privada nunca sale de OpenBao.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `backup.manifest(file_path) -> Manifest` (nombre, tamaño, SHA-256, fecha)

## Alcance

- **Backend:** tras `pg_dump` + `age`, el servicio `backup` calcula el SHA-256 del archivo cifrado y pide la firma al API o a un comando de la misma imagen (`cli sign-backup <archivo>`) que llama a `bus.sign("backup.signature", manifest)`; guarda `<archivo>.sig.json` junto al backup y lo sube con rclone. `backup_check` (US-115) y el procedimiento de restauración llaman a `cli verify-backup <archivo>`.
- **Front:** No aplica.

## Criterios de aceptación

1. Cada backup nocturno produce `<archivo>.sig.json` con `sha256`, `size_bytes`, `created_at` (UTC), `key_id`, `algorithm` y `signature`.
2. La firma se hace con `bus.sign("backup.signature", ...)`; ningún contenedor distinto del api o de su CLI tiene acceso a OpenBao, y la llave privada no existe en disco.
3. `cli verify-backup <archivo>` devuelve código 0 si el SHA-256 coincide y la firma verifica con la llave indicada en `key_id`, y código distinto de 0 en cualquier otro caso.
4. Alterar un solo byte del backup hace fallar la verificación y `backup_check` reporta error con el nombre del archivo.
5. Un backup sin `.sig.json` hace fallar `backup_check` (a partir de v1.0; los backups anteriores se listan como "sin firma" sin fallar).
6. El procedimiento documentado de restauración exige `verify-backup` en verde antes de `pg_restore`.
7. Cada firma y verificación deja fila en `crypto_ops` con verbo `sign` o `verify` y `data_class = backup.signature`.
8. Si OpenBao está sellado al firmar, el backup se conserva, la firma se reintenta en la siguiente ejecución de `backup_check` y el estado queda visible en `/health`.

## Escenarios BDD

```gherkin
# language: es
Característica: Firma de backups

  Escenario: Backup firmado y verificado
    Dado que el backup nocturno terminó
    Cuando corre la verificación diaria
    Entonces el backup tiene su archivo de firma
    Y la verificación de firma resulta válida

  Escenario: Backup alterado
    Dado que un byte del backup de anoche fue modificado
    Cuando corre la verificación diaria
    Entonces la verificación falla indicando el archivo alterado
```

## Endpoints

- Ninguno. Comandos: `cli sign-backup <archivo>`, `cli verify-backup <archivo>`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no; la llave `backup.signature` se registra en `crypto_keys` con `cli init-keys` o un comando idempotente.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `manifest` (SHA-256 de un archivo de prueba conocido).
- **Pruebas:** integración contra OpenBao de `compose.dev.yml`; prueba de alteración de un byte; `backup_check` con y sin firma.
- **Archivos principales:** `infra/backup/`, `api/src/app/cli.py`, `api/src/app/worker/jobs/backup_check.py`, `docs/` procedimiento de restauración.

## Supuestos

- Supuesto: el contenedor `backup` no habla con OpenBao; la firma la hace el CLI del api sobre el archivo en el volumen compartido `backups`.
- Supuesto: los backups previos a v1.0 no se firman retroactivamente.

## Dependencias

- US-114 · Backup nocturno cifrado
- US-115 · Verificación de backup
- US-134 · Proveedor OpenBao (firma en Transit)
- US-027 · firma en el bus (agregado en consolidación)

## INVEST

- **Independiente:** agrega un paso al backup existente.
- **Negociable:** dónde se ejecuta la firma.
- **Valiosa:** evidencia de integridad del respaldo.
- **Estimable:** dos comandos y un ajuste al job.
- **Pequeña:** cabe en un sprint.
- **Testeable:** un byte alterado falla.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de integración con OpenBao real en verde; cobertura de 80 % o más en lo tocado
- [ ] Procedimiento de restauración actualizado
- [ ] Revisión de PR aprobada
