# US-191 · Como socio quiero ver mis récords, RMs, benchmarks y peso y registrar mi peso para seguir mi progreso desde el celular

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Conformist de Athletes
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Progreso` (`/mi/progreso`)

## Historia

Como socio
quiero ver mis récords, mis RMs, mis benchmarks y la evolución de mi peso, y anotar mi peso
para ver que estoy progresando y tener motivos para seguir entrenando

## Contexto de dominio

- **Aggregate / entidades:** `PersonalRecord`, `BodyMetric`, resultados de benchmarks.
- **Reglas que aplica:** RN-13 y Q21 (medidas cifradas), Q6 (el socio ve sus propios datos sin enmascarar y eso se audita), RN-15, RN-14.
- **Eventos que emite:** `SensitiveFieldRevealed` (por cada lectura en claro de medidas propias)
- **Eventos que consume:** ninguno
- **Funciones puras:** reutiliza `athletes.summary`, `athletes.benchmark_series`, `athletes.validate_metric`

## Alcance

- **Backend:** rutas `/me/records`, `/me/rms`, `/me/benchmarks`, `/me/metrics` (GET y POST) que delegan en `athletes.service` con el `member_id` de la sesión.
- **Front:** `Portal_Progreso` con secciones Récords, RMs, Benchmarks y Peso (gráfica), y formulario "Registrar mi peso".

## Criterios de aceptación

1. `GET /api/v1/me/records`, `GET /api/v1/me/rms` y `GET /api/v1/me/benchmarks` devuelven solo datos del socio de la sesión con la misma forma que las rutas de US-180, US-184 y US-183; las listas paginan con `limit` (1 a 200, por defecto 25) y `offset`.
2. `GET /api/v1/me/metrics` devuelve las mediciones del socio descifradas (sin enmascarar, Q6) y deja una única fila de auditoría `reveal` por petición con el usuario socio, `table_name = body_metrics` y el número de registros revelados.
3. `POST /api/v1/me/metrics` con `{ measured_at, weight_kg }` crea un `BodyMetric` cifrado con `athlete.metric` y `recorded_by` igual al usuario socio; aplica `validate_metric` (422 fuera de rango o fecha futura).
4. El socio solo puede registrar `weight_kg` (y `notes`); enviar `height_cm` o `body_fat_pct` devuelve 422.
5. Ninguna ruta acepta `member_id`; anti IDOR probado por ruta (US-186).
6. Admin y coach reciben 403; sin token, 401.
7. Los valores no aparecen en logs; la base guarda solo blobs.

## Escenarios BDD

```gherkin
# language: es
Característica: Mi progreso

  Escenario: El socio registra su peso
    Dado que "Laura" está en "Mi progreso"
    Cuando registra un peso de 61,8 kg con fecha de hoy
    Entonces la gráfica de peso muestra el nuevo punto
    Y la base guarda el peso cifrado
    Y la auditoría registra que "Laura" vio sus propias medidas

  Escenario: Peso fuera de rango
    Cuando "Laura" registra un peso de 5 kg
    Entonces el sistema rechaza el registro con error en "weight_kg"
```

## Endpoints

- `GET /api/v1/me/records?kind&limit&offset` — rol(es): member — códigos: 200, 401, 403, 422
- `GET /api/v1/me/rms?limit&offset` — rol(es): member — códigos: 200, 401, 403, 422
- `GET /api/v1/me/benchmarks?wod&limit&offset` — rol(es): member — códigos: 200, 401, 403, 404, 422
- `GET /api/v1/me/metrics?limit&offset` — rol(es): member — códigos: 200, 401, 403, 422
- `POST /api/v1/me/metrics` — rol(es): member — entrada: `{ measured_at, weight_kg, notes? }` — códigos: 201, 401, 403, 422

## Pantalla

- `Portal_Progreso`: secciones con listas y gráfica de peso con tokens de color; formulario con controles de 44 px; estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ya cubiertas en EP-24; agregar la restricción de campos permitidos al socio.
- **Pruebas:** service (auditoría `reveal` por petición, blob); router con anti IDOR; Vitest de la página; captura 390 × 844.
- **Archivos principales:** `api/src/app/modules/portal/router.py`, `web/src/features/portal/pages/PortalProgress.tsx`.

## Supuestos

- Supuesto: una lectura de `/me/metrics` deja una sola fila `reveal` por petición (no una por campo) para no inflar la auditoría.
- Supuesto: el socio solo registra peso, no estatura ni grasa (`ROUTES.md` dice "Registrar peso").

## Dependencias

- US-186 · Autorización propia en rutas me
- US-184 · Perfil del atleta en la ficha (consultas de athletes)
- US-179 · patrón de medida en claro auditada (agregado en consolidación)

## INVEST

- **Independiente:** delega en services existentes.
- **Negociable:** qué medidas registra el socio.
- **Valiosa:** motivación del socio.
- **Estimable:** cinco rutas delegadas y una pantalla.
- **Pequeña:** cabe en un sprint.
- **Testeable:** reveal auditado, 422 por campo no permitido.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR, validación y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
