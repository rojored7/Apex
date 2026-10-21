# EP-13 · Puesta en marcha y continuidad operativa

- **Versión del plan:** v0.1 (Tarea 9 puntos 2 y 3, Tarea 10 puntos 2 y 5, Tarea 11 punto 1, Tarea 12 punto 1).
- **Bounded context:** ninguno de negocio propio. Usa los services de Members, Plans, Memberships y Payments, y el contenedor `backup`.
- **Estimación relativa:** M.

## Objetivo de negocio

Que el gimnasio pueda pasar del cuaderno y el Excel al sistema en un día, y que si el servidor se daña no pierda la información. Incluye cargar los socios que ya existen, tener datos de prueba para capacitar al equipo, un respaldo nocturno cifrado y una forma segura de actualizar el sistema.

## Actores

- Administrador u operador del servidor: importa socios, corre el seed, actualiza el sistema.
- Worker: corre los jobs programados.
- Contenedor `backup`: hace el respaldo nocturno.

## Capacidades incluidas

- `cli seed --demo`: 3 planes, 30 socios ficticios, membresías en todos los estados y pagos, usando los services de cada módulo (nunca SQL directo).
- `cli import-members archivo.xlsx`: importación idempotente por documento (índice ciego), con reporte de filas rechazadas y auditada (regla de datos 8: las migraciones de datos son comandos de `cli.py`, no Alembic).
- `worker/main.py` con APScheduler a las 7:00 America/Bogota, como proceso aparte de la misma imagen, que registra los jobs de cada épica (EP-09 vencimientos, EP-14 avisos, EP-17 firma de auditoría).
- Servicio `backup` en Compose: `pg_dump` nocturno cifrado con `age` y subido con `rclone` al destino que diga `.env` (P3: si no hay destino, queda local); volumen `backups`.
- Job `backup_check.py`: verifica que el último backup exista, sea de las últimas 24 horas y se pueda descifrar.
- Procedimiento documentado de respaldo de la KEK local fuera del servidor (sin ella, el backup no sirve).
- `infra/deploy.sh`: `pg_dump` previo, pull, up y verificación de `/health`.
- Arranque ordenado: `api` corre `alembic upgrade head` antes de aceptar tráfico; `web` y `worker` dependen de `api` sano.
- ADR iniciales en `docs/adr/`: `ADR-001-monolito-modular.md`, `ADR-002-bus-de-criptografia.md`, `ADR-003-pagos-inmutables.md`.

## Fuera de alcance

- Firma de backups con ML-DSA (EP-26).
- Restauración automática; se documenta el procedimiento manual.
- Monitoreo externo o alertas por fuera del sistema.

## Criterios de éxito medibles

- Base limpia, `alembic upgrade head` y `seed --demo` dejan el sistema usable (criterio de salida de la Tarea 9).
- `docker compose up` desde cero deja `/health` en verde y el seed cargado (criterio de salida de la Tarea 10).
- Correr `import-members` dos veces con el mismo archivo no crea duplicados; el reporte lista cada fila rechazada con su motivo.
- Un backup restaurado en una base vacía, con la KEK respaldada, permite leer los datos cifrados (prueba de restauración documentada).
- `backup_check` marca error si el último backup tiene más de 24 horas.
- `deploy.sh` aborta si `/health` no responde después de actualizar y deja el `pg_dump` previo disponible.

## Dependencias

- EP-00 Cimientos (Compose, Dockerfile).
- EP-07, EP-08, EP-09 y EP-10 (services que usan el seed y la importación).
- EP-02 Bus de criptografía (la importación cifra e indexa; el respaldo de la KEK).

## Riesgos

- El formato del Excel de origen es desconocido; la importación puede requerir un mapeo de columnas (ver preguntas abiertas).
- Respaldar la base sin respaldar la KEK es equivalente a no respaldar; es el error operativo más probable.
- `rclone` y `age` son binarios del contenedor de backup: hay que verificar sus licencias (MIT y BSD) en el chequeo de licencias.

## Pantallas del diseño que habilita

- Ninguna. Habilita la operación del sistema completo.
