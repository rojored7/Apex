# US-115 · Como administrador quiero que el sistema verifique cada mañana que el último backup existe, es reciente y se puede descifrar para enterarme a tiempo si los respaldos dejaron de funcionar

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno propio; job `worker/jobs/backup_check.py`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front; el resultado se ve en `/health` y en los logs)

## Historia

Como administrador
quiero que el job `backup_check` revise a las 7:00 el último backup
para saber si tengo un respaldo válido de las últimas 24 horas

## Contexto de dominio

- **Aggregate / entidades:** ninguno; lee el manifiesto `latest.json` del volumen `backups` y registra el resultado en `worker.job_runs`.
- **Reglas que aplica:** criterio de EP-13 "backup_check marca error si el último backup tiene más de 24 horas"; Q28 (`today_bogota()` y reloj del worker).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `backup_check.evaluate(manifest, now_utc, file_exists, sha256_ok, decrypt_ok) -> BackupStatus` con estados `ok`, `stale`, `missing`, `corrupt`, `undecryptable`.

## Alcance

- **Backend:** job registrado en el worker (US-113) que lee `latest.json`, verifica que el archivo existe, que su `created_at` tiene menos de 24 horas, que el `sha256` coincide y que se puede descifrar con la identidad de verificación `BACKUP_AGE_VERIFY_IDENTITY_PATH` (montada solo en el worker y solo si el operador la provee); si no hay identidad de verificación, comprueba solo existencia, edad e integridad y lo reporta como `ok_unverified`. Guarda el último resultado en `worker.job_runs` y lo expone como campo `backup` en `GET /health` (sin detalles sensibles). Log JSON de nivel `error` si el estado no es `ok`.
- **Front:** No aplica.

## Criterios de aceptación

1. Con un backup de hace 3 horas, íntegro y descifrable, el job registra `ok`.
2. Con un backup de hace 25 horas, el job registra `stale` y `GET /health` responde `backup: "stale"` (el código HTTP de `/health` sigue siendo 200, porque el API funciona).
3. Sin manifiesto o sin el archivo que nombra, el job registra `missing`.
4. Si el `sha256` del archivo no coincide con el manifiesto, el job registra `corrupt`.
5. Si se configuró identidad de verificación y el descifrado falla, el job registra `undecryptable`.
6. Sin identidad de verificación, el estado máximo es `ok_unverified` y nunca `ok`.
7. El descifrado de prueba se hace en streaming y no escribe el contenido en claro en disco.
8. El job usa la hora UTC del reloj (`Clock`) para la edad y es probado con `FrozenClock`.
9. Ejecutar el job dos veces el mismo día deja dos registros de verificación y el último es el que expone `/health`.

## Escenarios BDD

```gherkin
# language: es
Característica: Verificación diaria del backup

  Escenario: Backup reciente y válido
    Dado un backup creado el "2026-10-21T07:00:00Z" con sha256 correcto
    Y el reloj en "2026-10-21T12:00:00Z"
    Cuando corre "backup_check"
    Entonces el resultado es "ok"

  Escenario: Backup de más de 24 horas
    Dado un backup creado el "2026-10-20T07:00:00Z"
    Y el reloj en "2026-10-21T12:00:00Z"
    Cuando corre "backup_check"
    Entonces el resultado es "stale"
    Y "/health" informa "backup" como "stale"

  Escenario: Archivo alterado
    Dado un backup cuyo sha256 no coincide con el manifiesto
    Cuando corre "backup_check"
    Entonces el resultado es "corrupt"

  Escenario: Sin backups
    Dado que el volumen "backups" está vacío
    Cuando corre "backup_check"
    Entonces el resultado es "missing"
```

## Endpoints

- `GET /api/v1/health` — rol: público (lista blanca) — salida: agrega `backup: "ok" | "ok_unverified" | "stale" | "missing" | "corrupt" | "undecryptable" | "unknown"` — códigos: 200 con la base arriba.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (usa `worker.job_runs` de US-113, columna `result` y un JSON `details`; si `details` no existe en US-113, se agrega aquí con su migración).
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `evaluate` con los seis estados y el borde exacto de 24 horas (24 h 0 s es `stale`).
- **Pruebas:** puras; job con `FrozenClock` y archivos de prueba en un directorio temporal; router de `/health`.
- **Archivos principales:** `api/src/app/worker/jobs/backup_check.py`, `api/src/app/main.py` (health), `api/tests/worker/test_backup_check.py`.

## Supuestos

- Supuesto: el estado del backup se expone en `/health` como campo informativo sin cambiar el código 200; los documentos no dicen dónde se ve el resultado.
- Supuesto: el descifrado de prueba requiere que el operador monte una identidad `age` de verificación; si no la monta, el estado es `ok_unverified`.

## Dependencias

- US-114 · Backup nocturno cifrado (manifiesto y archivos).
- US-113 · Proceso worker programado (registro del job y `job_runs`).
- US-020 · /health (esta historia agrega el campo backup; agregado en consolidación)

## INVEST

- **Independiente:** solo lee archivos y el reloj.
- **Negociable:** dónde se muestra el estado se puede ampliar.
- **Valiosa:** detecta el fallo silencioso más común de los respaldos.
- **Estimable:** reglas claras de edad e integridad.
- **Pequeña:** un job y un campo de health.
- **Testeable:** función pura con estados enumerados.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y del job en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router de `/health`
- [ ] Front (no aplica)
- [ ] Migración aplicada y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría (no aplica)
- [ ] Revisión de PR aprobada
