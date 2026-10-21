# US-144 · Como administrador quiero consultar la bitácora de operaciones criptográficas y el progreso de los trabajos para saber quién usó cada llave y cómo va una rotación

- **Épica:** EP-18 · Administración de llaves de cifrado
- **Bounded context:** Crypto (`core/crypto/router.py`, esquema `crypto`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Llaves` (`/sistema/llaves`, pestañas Bitácora y Trabajos)

## Historia

Como administrador
quiero consultar la bitácora de operaciones criptográficas y el progreso de los trabajos de rotación y migración
para saber quién usó cada llave, sobre qué registro, y si una rotación terminó o falló

## Contexto de dominio

- **Aggregate / entidades:** `CryptoOp` (append-only: `at`, `user_id`, `verb`, `data_class`, `key_id`, `key_version`, `record_id`, `result`, `batch_id`), `CryptoJob` (`kind`, `data_class`, `status`, `total`, `done`, `started_at`, `finished_at`, `error`).
- **Reglas que aplica:** `crypto_ops` es inmutable (sin `UPDATE` ni `DELETE`); RN-14 (llaves y su bitácora nunca se borran); RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `GET /api/v1/crypto/ops` paginado con filtros; `GET /api/v1/crypto/jobs` paginado con porcentaje de avance calculado.
- **Front:** pestañas "Bitácora" (tabla filtrable) y "Trabajos" (lista con barra de progreso que se refresca mientras haya trabajos `running`).

## Criterios de aceptación

1. Ambos endpoints exigen rol `admin`; coach y socio reciben 403; sin token, 401.
2. `GET /crypto/ops` acepta `from`, `to` (ISO 8601 UTC), `verb`, `data_class`, `key_id`, `user_id`, `result`, `batch_id`, `limit` (1 a 200, por defecto 25) y `offset`; responde `{ items, total, limit, offset }` ordenado por `at` descendente.
3. `GET /crypto/jobs` acepta `status`, `kind`, `data_class`, `limit`, `offset`; cada trabajo trae `total`, `done`, `percent` (entero de 0 a 100, `done * 100 // total`, 0 si `total = 0`), fechas en UTC y `error` si falló.
4. Ninguna respuesta contiene material de llave ni valores descifrados; `record_id` es solo el UUID.
5. La pestaña Trabajos refresca cada 5 segundos mientras exista al menos un trabajo `running` y deja de refrescar cuando no hay ninguno.
6. Un `limit` fuera de rango o una fecha mal formada devuelve 422 con `field`.

## Escenarios BDD

```gherkin
# language: es
Característica: Bitácora y trabajos criptográficos

  Escenario: El administrador sigue una rotación en curso
    Dado que inicié sesión como administrador
    Y existe un trabajo "rotate" de "member.phone" con total 1200 y done 500 en estado "running"
    Cuando abro la pestaña Trabajos de la pantalla de llaves
    Entonces veo el trabajo con 41 % de avance
    Y la barra se actualiza sola mientras el trabajo siga en curso

  Escenario: Filtro de bitácora con fecha inválida
    Dado que inicié sesión como administrador
    Cuando pido GET /api/v1/crypto/ops?from=ayer
    Entonces recibo 422 con field "from"
```

## Endpoints

- `GET /api/v1/crypto/ops` — rol(es): admin — entrada: filtros y `limit`/`offset` — salida: `{ items: CryptoOpOut[], total, limit, offset }` — códigos: 200, 401, 403, 422
- `GET /api/v1/crypto/jobs` — rol(es): admin — entrada: `status?`, `kind?`, `data_class?`, `limit`, `offset` — salida: `{ items: CryptoJobOut[], total, limit, offset }` — códigos: 200, 401, 403, 422

## Pantalla

- `Llaves` en `/sistema/llaves`, pestañas Bitácora y Trabajos. Estados de carga, vacío y error; barra de progreso con texto del porcentaje.

## Notas técnicas

- **Migración:** no; verificar índice sobre `crypto_ops(at)` y `crypto_ops(batch_id)` (si falta, una migración de índices).
- **Trigger / restricciones:** sin cambios; el trigger append-only de `crypto_ops` (US-024) se mantiene.
- **Funciones puras a probar:** cálculo de `percent` (total 0, total 1200 done 500 = 41, done = total = 100).
- **Pruebas:** router (rol, filtros, paginación), service con base real, front (refresco condicionado con temporizador simulado).
- **Archivos principales:** `api/src/app/core/crypto/router.py`, `api/src/app/core/crypto/service.py`, `web/src/features/system/components/CryptoJobs.tsx`.

## Supuestos

- Supuesto: el intervalo de refresco de la pestaña Trabajos es de 5 segundos (ningún documento lo fija).

## Dependencias

- US-143 · Inventario de llaves (pantalla y router base)

## INVEST

- **Independiente:** lectura de tablas existentes.
- **Negociable:** filtros e intervalo de refresco.
- **Valiosa:** evidencia de uso de llaves y control de rotaciones.
- **Estimable:** dos endpoints de lectura y dos pestañas.
- **Pequeña:** sí.
- **Testeable:** porcentajes y filtros son verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
