# US-117 · Como administrador quiero actualizar el sistema con un solo comando que respalda antes y verifica después para no quedar con el gimnasio sin sistema por una actualización fallida

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno; `infra/deploy.sh`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero ejecutar `infra/deploy.sh` para actualizar
para que se haga un `pg_dump` previo, se bajen las imágenes nuevas, se levanten y se verifique `/health`, abortando si algo falla

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** regla de datos 7 (migraciones de Alembic, nunca editar una aplicada; el api corre `alembic upgrade head` al arrancar), `CLAUDE.md` (detenerse antes de decisiones irreversibles), criterio de EP-13 "deploy.sh aborta si /health no responde y deja el pg_dump previo disponible".
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** script `infra/deploy.sh` con `set -euo pipefail` que: verifica que existan `.env` y la KEK; ejecuta un `pg_dump` previo cifrado con `age` en `backups/pre-deploy-<fecha>.sql.age`; registra las etiquetas de imagen actuales; hace `docker compose pull`; `docker compose up -d`; espera hasta 120 s a que `/health` responda 200 con `db: "ok"`; si no responde, imprime los últimos logs de `api`, deja el dump previo y las etiquetas anteriores en un archivo `rollback-<fecha>.txt` con el comando para volver, y termina con código distinto de 0. Documento corto en `docs/operacion/actualizar.md`.
- **Front:** No aplica.

## Criterios de aceptación

1. El script no hace nada (código distinto de 0) si falta `.env` o el archivo de KEK.
2. Antes de cambiar imágenes siempre existe un `pre-deploy-<fecha>.sql.age` nuevo y legible por la identidad `age`; si el `pg_dump` falla, el script aborta sin hacer `pull` ni `up`.
3. Si `/health` responde 200 dentro de 120 s, el script termina con código 0 e imprime la versión desplegada.
4. Si `/health` no responde 200 en 120 s, el script termina con código distinto de 0, conserva el dump previo, escribe `rollback-<fecha>.txt` con las etiquetas de imagen anteriores y el comando para volver a ellas, e imprime los últimos 100 renglones del log del api.
5. El script nunca ejecuta `docker compose down -v` ni borra volúmenes.
6. El script no restaura la base automáticamente (la restauración es manual, EP-13 fuera de alcance) y lo dice en su salida.
7. El script no imprime secretos del `.env`.

## Escenarios BDD

```gherkin
# language: es
Característica: Despliegue seguro

  Escenario: Actualización exitosa
    Dado un sistema en marcha con la versión "0.1.0"
    Cuando ejecuto "infra/deploy.sh" con imágenes "0.1.1"
    Entonces existe un "pre-deploy-*.sql.age" nuevo
    Y "/health" responde 200
    Y el script termina con código 0

  Escenario: La nueva versión no arranca
    Dado imágenes nuevas cuyo api falla al arrancar
    Cuando ejecuto "infra/deploy.sh"
    Entonces el script termina con un código distinto de 0
    Y existe "rollback-*.txt" con las etiquetas anteriores
    Y el dump previo sigue disponible

  Escenario: Falla el dump previo
    Dado que la base no responde al "pg_dump"
    Cuando ejecuto "infra/deploy.sh"
    Entonces el script aborta sin descargar imágenes

  Escenario: Falta la KEK
    Dado que el archivo de KEK no existe
    Cuando ejecuto "infra/deploy.sh"
    Entonces el script termina con un código distinto de 0 sin tocar los contenedores
```

## Endpoints

- `GET /api/v1/health` (consumido, público).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna; `shellcheck` y prueba en CI con un api de prueba que falla al arrancar.
- **Pruebas:** integración en CI con Compose (camino feliz y api roto).
- **Archivos principales:** `infra/deploy.sh`, `docs/operacion/actualizar.md`.

## Supuestos

- Supuesto: el tiempo de espera de `/health` es 120 s y el dump previo usa la misma identidad `age` del backup nocturno.

## Dependencias

- US-114 · Backup nocturno cifrado (identidad `age`, volumen `backups`).
- US-020 · create_app, migraciones y health.

## INVEST

- **Independiente:** solo orquesta Compose.
- **Negociable:** tiempos y mensajes ajustables.
- **Valiosa:** evita quedar sin sistema tras una actualización.
- **Estimable:** script acotado.
- **Pequeña:** un script y un documento.
- **Testeable:** dos caminos probados en CI.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `shellcheck` en verde
- [ ] Pruebas de integración del despliegue en CI en verde
- [ ] Pruebas de router (no aplica)
- [ ] Front (no aplica)
- [ ] Migración (no aplica)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría (no aplica)
- [ ] Revisión de PR aprobada
