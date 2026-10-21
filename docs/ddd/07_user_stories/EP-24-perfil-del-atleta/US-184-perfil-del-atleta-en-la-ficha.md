# US-184 · Como coach quiero ver el perfil del atleta en la ficha del socio con resumen, medidas, RMs, récords y benchmarks para tener toda su historia en un solo lugar

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (módulo `athletes`)
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Atleta_Perfil` (`/socios/:id/atleta`, pestaña Atleta de `Socio_Ficha`)

## Historia

Como coach
quiero abrir la pestaña Atleta de un socio y ver su resumen y sus subpestañas
para conversar con él sobre su progreso sin buscar en varias pantallas

## Contexto de dominio

- **Aggregate / entidades:** `BodyMetric`, `PersonalRecord`, lectura de resultados.
- **Reglas que aplica:** RN-13 (medidas enmascaradas por defecto), RN-15, Q21.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `athletes.summary(metrics, records) -> AthleteSummary` (última medición, variación de peso enmascarada, número de RMs vigentes, últimos 3 récords)

## Alcance

- **Backend:** `GET /athletes/{id}/summary` que compone los datos de las subpestañas sin descifrar medidas; `GET /athletes/{id}/rms` como vista de RMs vigentes por movimiento (ruta de `ROUTES.md`).
- **Front:** pestaña Atleta con `Tabs` (Resumen, Medidas, RMs, Récords, Benchmarks) que monta las vistas de US-178, US-180 y US-183; ruta `/socios/:id/atleta`.

## Criterios de aceptación

1. `GET /api/v1/athletes/{member_id}/summary` con rol admin o coach devuelve fecha de la última medición, número de RMs vigentes, últimos tres récords (valor, movimiento o benchmark, origen, fecha) y número de benchmarks con intentos; las medidas vienen enmascaradas.
2. `GET /api/v1/athletes/{member_id}/rms` devuelve un ítem por movimiento con su RM vigente (valor en kg, origen manual o derivado, fecha), paginado con `limit` y `offset`.
3. Abrir la pestaña no descifra ninguna medida ni deja filas `reveal` en auditoría.
4. Las subpestañas conservan la selección en la URL (`?tab=medidas`).
5. Un socio dado de baja muestra la pestaña en solo lectura (sin botones de registrar) y la API responde 404 a los POST de medidas y récords.
6. Rol `member` recibe 403 en ambos endpoints; sin token, 401.
7. La pestaña cumple controles de 44 px, foco visible y el estado vigente y el origen se indican con texto, no solo color.

## Escenarios BDD

```gherkin
# language: es
Característica: Perfil del atleta en la ficha

  Escenario: El coach abre el perfil de un atleta con historia
    Dado que "Juan Ríos" tiene dos mediciones, tres RMs vigentes y un benchmark con intentos
    Cuando el coach abre la pestaña Atleta de "Juan Ríos"
    Entonces ve el resumen con la última medición enmascarada y 3 RMs vigentes
    Y puede cambiar a las subpestañas Medidas, RMs, Récords y Benchmarks
    Y no se registra ningún reveal en la auditoría

  Escenario: Socio sin datos de atleta
    Dado que "Marta Díaz" no tiene mediciones ni récords
    Cuando el coach abre su pestaña Atleta
    Entonces ve el estado vacío con la acción "Registrar medición"
```

## Endpoints

- `GET /api/v1/athletes/{member_id}/summary` — rol(es): admin, coach — salida: `AthleteSummaryOut` — códigos: 200, 401, 403, 404
- `GET /api/v1/athletes/{member_id}/rms?limit&offset` — rol(es): admin, coach — salida: página de RMs vigentes — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Atleta_Perfil` dentro de `Socio_Ficha`: resumen con `KpiCard` y `MaskedValue`, subpestañas con `Tabs`. Estados de carga, vacío y error por subpestaña.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `summary` con y sin datos.
- **Pruebas:** pura; service; router; Vitest de la pestaña; capturas en 768, 1024 y 1440 claro y oscuro; Playwright: abrir ficha, pestaña Atleta, registrar medición, revelar peso.
- **Archivos principales:** `web/src/features/athletes/pages/AthleteProfile.tsx`, `api/src/app/modules/athletes/router.py`.

## Supuestos

- Supuesto: `GET /athletes/{id}/summary` no está en la épica; se agrega para que el resumen no haga cuatro llamadas.

## Dependencias

- US-178 · Registrar medidas corporales cifradas
- US-180 · Registrar récords manuales
- US-183 · Comparar benchmarks

## INVEST

- **Independiente:** compone vistas ya construidas.
- **Negociable:** contenido del resumen.
- **Valiosa:** toda la historia del atleta en un lugar.
- **Estimable:** dos endpoints de lectura y una pestaña.
- **Pequeña:** cabe en un sprint.
- **Testeable:** sin reveal al abrir, 403 por rol.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
