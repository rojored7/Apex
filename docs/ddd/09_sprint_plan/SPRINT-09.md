# Sprint 9 · v0.6: perfil del atleta

- Versión: v0.6.
- Épica: EP-24 (perfil del atleta).
- Tamaño: 7 historias, 26 puntos y 109 h relativas.
- Nivel de detalle: 29 slices con su plan en `docs/ddd/blueprints/sprint-09-plan.md` (decisiones S9-D1 a D42 en `DECISIONES.md`, bloque «Sprint 9»). Las enmiendas de la sección 10 del plan mandan.
- Historias del sprint: US-178, US-179, US-180, US-181, US-182, US-183, US-184.

## Objetivo

Que la ficha del socio tenga un perfil de atleta con:
- medidas corporales cifradas bajo `athlete.metric` (Q21), que solo se ven en claro con un `reveal` auditado;
- récords personales manuales;
- RM derivados automáticamente del movimiento principal en WODs de carga (RN-12, Q19);
- récords de benchmark (Q20, N-46);
- la comparación de benchmarks en el tiempo.

## Demo al final del sprint

1. **Medidas.** Registrar peso (gramos), estatura (cm) y porcentaje de grasa de un socio, con la fecha `measured_on`. Sin autorización de datos del socio, el alta da 409 `consent_required` (S9-D29). En la base, las cuatro columnas (`weight_g`, `height_cm`, `body_fat_pct`, `notes`) son blobs `apx1.`; solo `measured_on` y `member_id` quedan en claro. "Mostrar" el peso deja una fila `reveal` y otra `decrypt`.
2. **RM derivado por carga.**
   - Validar un resultado de 100 kg en un WOD con `score_type = load` crea un RM derivado sobre el movimiento principal.
   - Un resultado `scaled` no deriva (N-45).
   - Corregir o anular ese resultado marca el RM como `invalidated_at` y no lo borra (refinamiento de US-181; se repone el mejor que quede, S9-D11).
3. **Benchmark.** Un mejor tiempo en "Fran" crea un `PersonalRecord(kind = benchmark)`, agrupado por `benchmark_id`. La comparación muestra la serie del socio.
4. **Ficha.** La pestaña Atleta tiene cinco subpestañas, con el resumen y los RM vigentes. Ninguna de ellas descifra medidas para listarlas.

## Dependencias de sprints anteriores

- **Sprint 8:**
  - US-165 (movimientos con `unit`);
  - US-166 (WOD, principal y catálogo de benchmarks);
  - US-169 y US-170 (`WodResultValidated` con su payload y la corrección);
  - US-171 (`leaderboard_order`).
- **Sprint 3:** US-073 (ficha y pestañas) y US-074 (patrón de `reveal` auditado).
- **Sprint 2:** US-107 (acción `reveal` en la auditoría).
- **Sprint 1:** US-023, US-025 y US-028 (`init-keys`, registro de `data_class` y tipos `Encrypted`).

## Historias en orden de ejecución (por bloques)

1. **Bloque A · Medidas.**
   - US-178 · Registrar medidas cifradas, con los rangos de N-45.
   - US-179 · Mostrar una medida en claro, con auditoría (Q6).
2. **Bloque B · Récords.**
   - US-180 · Récords manuales: el de benchmark usa `benchmark_id`.
   - US-181 · RM derivado por carga: `WodResultSuperseded` llena `invalidated_at`. Toca US-170.
   - US-182 · Récord derivado de benchmark: mismo handler, agrupado por `benchmark_id`.
   - US-183 · Comparar benchmarks: lee `results.service.member_results`.
3. **Bloque C · Perfil.**
   - US-184 · Perfil del atleta en la ficha: resumen y RM vigentes, sin descifrar.

Waves:
- **Wave 0:** documentos y decisiones (W0-1), cubeta `athletes-write` y línea base (W0-2), claves de alerta, prueba de arranque de las clases de dato y alerta por volumen de `reveal` (W0-3). No hay paso `init-keys`: el api crea la DEK de `athlete.metric` al arrancar (S9-D5).
- **Waves 3a y 3b:** los bloques A (A1 a A3), B y C (B1 a B6, C1, C2), en ese orden.
- **Wave D:** deuda de v0.5 (X1 WhatsApp con teléfono, X2 inactividad del quiosco, X3 TV en tiempo real).
- **Waves 5a y 5b:** `Atleta_Perfil` y la pestaña Atleta de `Socio_Ficha`, con cinco subpestañas.

## Migraciones que aplica

En orden ascendente:
- `0042_athletes_body_metrics` (US-178): crea el esquema `athletes`, la tabla y sus guardas.
- `0043_athletes_personal_records` (US-180 a US-182): tabla, guardas e invalidación en una sola migración.

Los números `0085` a `0089` del plan original quedan sin usar (S9-D2). La revisión de Fase 4 añadió `0044_body_metrics_time_checks` (V7b, L1): dos CHECK de orden temporal en `athletes.body_metrics` (S9-D70).

## Endpoints que expone

11 rutas, todas con el prefijo `/api/v1/athletes/{member_id}`, solo admin y coach, `Cache-Control: no-store`:
- `POST` y `GET /metrics`.
- `POST /metrics/{metric_id}/reveal` (cubetas de `members-reveal`, compartidas con la ficha).
- `POST /metrics/{metric_id}/void` (S9-D13).
- `POST` y `GET /records`.
- `POST /records/{record_id}/invalidate` (S9-D13).
- `GET /rms`.
- `GET /benchmarks` y `GET /benchmarks/{benchmark_id}` (la serie).
- `GET /summary`.

Cubeta nueva `athletes-write` (30/min; `USER_ATHLETES_WRITE_LIMIT_PER_MIN`): 28 cubetas y 27 variables `USER_*` (S9-D17). Comando nuevo: `derive-records` (S9-D21).

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- `test_no_plaintext_at_rest.py`, ampliada a `athlete.metric`.
- `test_reveal_single_door.py` (tres puertas de `reveal`), `test_audited_tables.py`, `test_service_import_graph.py` (cuatro aristas nuevas), `test_no_cross_schema_sql.py` (suma `athletes`).
- `test_no_cross_models.py`: `athletes` lee `results` y `wods` solo por sus services.
- `test_banned_imports.py`.
- `test_every_route_has_role.py`.

## Riesgos y mitigación

1. [MEDIUM] Un error de digitación en la tablet (1000 kg en lugar de 100) crea un RM que nunca se borra (RN-14).
   - Mitigación: `invalidated_at` cuando se corrige el resultado (US-181).
2. [MEDIUM] Si la DEK de `athlete.metric` no existe, el alta falla con 503.
   - Mitigación: el paso de despliegue de la Wave 0 y la prueba de arranque.
3. [MEDIUM] Volumen de descifrados en la gráfica de peso y en `/me/metrics` (v1.0).
   - Mitigación: paginación y `crypto_ops.count` por lote (N-05).
4. [LOW] Unidades: un RM manual sobre un movimiento cuya `unit` no es kg.
   - Mitigación: responde 422; los movimientos de gimnasia no tienen RM en v0.6.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E (`web/tests/e2e/stack/`):
  - registrar una medida y revelarla;
  - validar un resultado de carga y ver el RM;
  - corregir el resultado y ver el RM invalidado.
- Seguridad, revisada por `security-reviewer`:
  - todas las medidas cifradas;
  - `reveal` auditado con el campo;
  - listas sin valores descifrados.
- `verify-delivery`.
