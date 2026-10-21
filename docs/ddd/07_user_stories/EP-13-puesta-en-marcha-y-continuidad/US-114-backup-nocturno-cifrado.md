# US-114 · Como administrador quiero un respaldo nocturno cifrado de la base y los adjuntos para no perder la información si el servidor se daña

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno; contenedor `backup` en `infra/backup/`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que cada noche se haga un `pg_dump` cifrado con `age` y se suba con `rclone` al destino configurado
para tener una copia recuperable y protegida de los datos del gimnasio fuera del servidor

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** RN-13 (los datos sensibles ya van cifrados por campo; el backup además se cifra completo), P3 (destino S3 compatible por `.env`; si no hay destino, el backup queda local en el volumen `backups`), restricción no funcional "sin servicios en la nube obligatorios".
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `backup_name(now_utc) -> "apex-AAAAMMDD-HHMMSS.sql.age"` y `retention_to_delete(files, keep_days)` en el script.

## Alcance

- **Backend:** `infra/backup/Dockerfile` (imagen mínima con `pg_dump` 16, `age` y `rclone`), script `infra/backup/run.sh` con `set -euo pipefail` que: hace `pg_dump --format=custom` de toda la base, empaqueta también el volumen `uploads` (desde v0.3 tiene adjuntos), cifra con la llave pública `age` de `BACKUP_AGE_RECIPIENT`, guarda en el volumen `backups`, sube con `rclone` a `BACKUP_RCLONE_REMOTE` si está definido, aplica retención local de `BACKUP_KEEP_DAYS` (por defecto 14) y escribe un manifiesto `latest.json` (nombre, tamaño, sha256, fecha UTC, resultado de la subida). Programación nocturna a las 02:00 America/Bogota con cron dentro del contenedor. Variables nuevas en `.env.example`.
- **Front:** No aplica.

## Criterios de aceptación

1. El servicio `backup` existe en `infra/compose.yml`, monta el volumen `backups` y el volumen `uploads` en solo lectura, y no expone puertos.
2. Cada ejecución produce un archivo `apex-AAAAMMDD-HHMMSS.sql.age` (fecha en UTC) que no se puede leer sin la identidad privada `age`; la llave privada nunca está en el servidor ni en la imagen, solo la pública (`BACKUP_AGE_RECIPIENT`).
3. Si `BACKUP_RCLONE_REMOTE` está vacío, el backup queda solo en el volumen `backups` y el manifiesto marca `upload: "skipped"` (P3); si está definido y la subida falla, el archivo local se conserva y el manifiesto marca `upload: "failed"` con el error.
4. El script termina con código distinto de 0 si `pg_dump` o `age` fallan y en ese caso no deja un archivo parcial con nombre final.
5. La retención borra solo archivos locales con más de `BACKUP_KEEP_DAYS` días y nunca el último backup exitoso.
6. El manifiesto `latest.json` contiene nombre, tamaño en bytes, `sha256`, `created_at` en UTC y estado de subida.
7. Ningún secreto (contraseña de la base, credenciales de rclone) aparece en los logs del contenedor; las credenciales de rclone entran por archivo montado o `.env`, nunca en la imagen.
8. Las licencias de `age` (BSD-3) y `rclone` (MIT) quedan registradas en `NOTICE` y pasan el chequeo de licencias.
9. Ejecutar el script a mano (`docker compose run --rm backup run.sh`) produce el mismo resultado que la ejecución programada.

## Escenarios BDD

```gherkin
# language: es
Característica: Backup nocturno cifrado

  Escenario: Backup local y subido
    Dado "BACKUP_RCLONE_REMOTE" configurado con un bucket S3 compatible de prueba
    Cuando corre el backup de las 2:00
    Entonces existe un archivo "apex-*.sql.age" en el volumen "backups"
    Y el mismo archivo existe en el bucket
    Y "latest.json" marca "upload" como "ok"

  Escenario: Sin destino externo el backup queda local
    Dado "BACKUP_RCLONE_REMOTE" vacío
    Cuando corre el backup
    Entonces el archivo queda en el volumen "backups"
    Y "latest.json" marca "upload" como "skipped"

  Escenario: Falla de pg_dump no deja archivo parcial
    Dado que la base de datos no responde
    Cuando corre el backup
    Entonces el script termina con un código distinto de 0
    Y no hay archivo nuevo con nombre final en "backups"

  Escenario: El archivo no se lee sin la identidad privada
    Dado un backup generado
    Cuando intento restaurarlo sin la identidad "age"
    Entonces el descifrado falla
```

## Endpoints

- Ninguno. Script `infra/backup/run.sh` en el contenedor `backup`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** nombre del archivo y selección de retención (pruebas con `bats` o script de prueba en CI).
- **Pruebas:** prueba de integración en CI con Postgres y MinIO (Apache 2.0, solo en pruebas) como remoto rclone; prueba de falla de base.
- **Archivos principales:** `infra/backup/Dockerfile`, `infra/backup/run.sh`, `infra/compose.yml`, `.env.example`, `NOTICE`.

## Supuestos

- Supuesto: la hora del backup es 02:00 America/Bogota (el plan solo dice "nocturno"); queda configurable por `BACKUP_CRON`.
- Supuesto: retención local por defecto de 14 días (`BACKUP_KEEP_DAYS`); la retención remota la gestiona el destino.
- Supuesto: el volumen `uploads` entra en el backup desde v0.1 aunque esté vacío, para no olvidarlo cuando llegue EP-19.

## Dependencias

- US-005 · Dockerfile del api y Compose (volúmenes y red).

## INVEST

- **Independiente:** contenedor aparte; solo necesita la base arriba.
- **Negociable:** hora, retención y formato del manifiesto ajustables.
- **Valiosa:** sin backup, un daño del disco es pérdida total.
- **Estimable:** herramientas conocidas.
- **Pequeña:** un Dockerfile y un script.
- **Testeable:** archivos y manifiesto verificables en CI.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde (no aplica: shell; `shellcheck` en verde)
- [ ] Pruebas de integración del backup en CI en verde
- [ ] Pruebas de router (no aplica)
- [ ] Front (no aplica)
- [ ] Migración (no aplica)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Licencias registradas en `NOTICE`
- [ ] Revisión de PR aprobada
