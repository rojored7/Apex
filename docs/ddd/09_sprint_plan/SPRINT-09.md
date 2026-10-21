# Sprint 9 · v0.6: perfil del atleta

- Versión: v0.6.
- Épica: EP-24 (perfil del atleta).
- Tamaño: 7 historias, 26 puntos y 109 h relativas.
- Nivel de detalle: bloques en orden de ejecución, sin slices. Se refina al llegar.
- Historias del sprint: US-178, US-179, US-180, US-181, US-182, US-183, US-184.

## Objetivo

Que la ficha del socio tenga un perfil de atleta con:
- medidas corporales cifradas bajo `athlete.metric` (Q21), que solo se ven en claro con un `reveal` auditado;
- récords personales manuales;
- RM derivados automáticamente del movimiento principal en WODs de carga (RN-12, Q19);
- récords de benchmark (Q20, N-46);
- la comparación de benchmarks en el tiempo.

## Demo al final del sprint

1. **Medidas.** Registrar peso, estatura y porcentaje de grasa de un socio. En la base, las cuatro columnas son blobs `apx1.`; solo `measured_at` y `member_id` quedan en claro. "Mostrar" el peso deja una fila `reveal` y otra `decrypt`.
2. **RM derivado por carga.**
   - Validar un resultado de 100 kg en un WOD con `score_type = load` crea un RM derivado sobre el movimiento principal.
   - Un resultado `scaled` no deriva (N-45).
   - Corregir ese resultado marca el RM como `invalidated_at` y no lo borra (refinamiento de US-181).
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
- **Wave 0:** paso de despliegue de v0.6. `init-keys --data-class athlete.metric` corre antes de la primera alta, con una prueba de arranque que verifica las `data_class` registradas.
- **Waves 3a y 3b:** los bloques A, B y C, en ese orden.
- **Waves 5a y 5b:** `Atleta_Perfil` y la pestaña Atleta de `Socio_Ficha`, con cinco subpestañas.

## Migraciones que aplica

En orden ascendente:
- `0085_athletes_schema_body_metrics` (US-178).
- `0086_athletes_personal_records` (US-180).
- `0087_athletes_personal_records_invalidated` (US-181).

## Endpoints que expone

Todos con el prefijo `/api/v1/athletes/{member_id}`:
- `POST` y `GET /metrics`.
- `POST /metrics/{metric_id}/reveal`.
- `POST` y `GET /records`.
- `GET /rms`.
- `GET /benchmarks`.
- `GET /summary`.

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- `test_no_plaintext_at_rest.py`, ampliada a `athlete.metric`.
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
- E2E:
  - registrar una medida y revelarla;
  - validar un resultado de carga y ver el RM;
  - corregir el resultado y ver el RM invalidado.
- Seguridad, revisada por `security-reviewer`:
  - todas las medidas cifradas;
  - `reveal` auditado con el campo;
  - listas sin valores descifrados.
- `verify-delivery`.
