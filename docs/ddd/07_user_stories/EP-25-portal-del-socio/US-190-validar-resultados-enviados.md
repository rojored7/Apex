# US-190 · Como coach quiero validar los resultados que envían los socios desde una bandeja para que entren al leaderboard y a sus récords

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Training (módulo `results`)
- **Versión:** v1.0
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Resultados_Registro` (`/clases/:id/resultados`) y `WOD_Detalle` (`/wods/:id`), bandeja "Por validar"

## Historia

Como coach
quiero ver los resultados pendientes de un WOD y validarlos con un toque
para que las marcas de los socios cuenten en el leaderboard y en sus récords sin volver a digitarlas

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` (`status`, `validated_by`, `validated_at`).
- **Reglas que aplica:** RN-11 (pending hasta que un coach valide), `validate` solo coach o admin, RN-12 (al validar puede derivar récord), RN-14 (no se borra), trigger que solo permite `UPDATE` de columnas de validación e `is_current`.
- **Eventos que emite:** `WodResultValidated`
- **Eventos que consume:** ninguno
- **Funciones puras:** `results.can_validate(result) -> bool` (solo `pending` e `is_current`)

## Alcance

- **Backend:** `POST /results/{id}/validate` llama a `results.service.validate(id, by)`; `GET /wods/{id}/results?status=pending` para la bandeja.
- **Front:** contador y lista "Por validar" en `WOD_Detalle` y en `Resultados_Registro`, con acciones "Validar" y "Corregir" (corregir usa US-170, que crea un resultado validado que reemplaza al pendiente).

## Criterios de aceptación

1. `POST /api/v1/results/{id}/validate` con rol admin o coach cambia `status` de `pending` a `validated`, fija `validated_by` y `validated_at` (UTC) y responde 200.
2. En la misma transacción se emite `WodResultValidated`; el handler de Athletes (US-181, US-182) puede crear el récord derivado; si el handler falla, la validación se revierte.
3. Validar un resultado ya `validated` o no vigente (`is_current = false`) devuelve 409.
4. Rol member recibe 403; sin token, 401; resultado inexistente, 404.
5. `GET /api/v1/wods/{id}/results?status=pending&limit&offset` lista los pendientes vigentes del WOD, paginado (`limit` 1 a 200, por defecto 25).
6. Tras validar, el resultado aparece en `GET /wods/{id}/leaderboard` y en `GET /tv/today` (antes no).
7. El cambio queda auditado como `update` con antes y después de `status`; el trigger rechaza cualquier otro `UPDATE` sobre `wod_results`.
8. La bandeja muestra el número de pendientes con texto, y el botón "Validar" tiene 56 px en la tablet (`GymLayout`).

## Escenarios BDD

```gherkin
# language: es
Característica: Validar resultados enviados por socios

  Escenario: El coach valida un resultado que supera el RM
    Dado que "Juan" envió desde el portal 100 kg en el WOD de carga de hoy con "Deadlift" como principal
    Y que su RM vigente en "Deadlift" es 95 kg
    Cuando el coach pulsa "Validar" en la bandeja "Por validar"
    Entonces el resultado aparece en el leaderboard del día
    Y "Juan" tiene un RM vigente de 100 kg en "Deadlift"

  Escenario: Validar dos veces
    Dado que el resultado de "Juan" ya está validado
    Cuando el coach intenta validarlo otra vez
    Entonces el sistema responde con conflicto
```

## Endpoints

- `POST /api/v1/results/{id}/validate` — rol(es): admin, coach — salida: `WodResultOut` — códigos: 200, 401, 403, 404, 409
- `GET /api/v1/wods/{id}/results?status&limit&offset` — rol(es): admin, coach — códigos: 200, 401, 403, 404, 422

## Pantalla

- `WOD_Detalle` y `Resultados_Registro`: sección "Por validar" con nombre, marca, nivel y acciones; estados de carga, vacío ("Nada por validar") y error. `// DESIGN-GAP:` si el diseño no trae la bandeja.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** confirmar que el trigger de `wod_results` (US-169) permite `status`, `validated_by`, `validated_at` e `is_current`, y nada más.
- **Funciones puras a probar:** `can_validate`.
- **Pruebas:** pura; service con evento y derivación; prueba de reversión; router; Vitest de la bandeja; E2E: socio envía, coach valida, aparece en leaderboard.
- **Archivos principales:** `api/src/app/modules/results/`, `web/src/features/results/components/PendingInbox.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-189 · Mis WODs y enviar resultado (existen pendientes)
- US-181 · Récord derivado por carga (efecto de la validación)

## INVEST

- **Independiente:** una transición de estado.
- **Negociable:** dónde vive la bandeja.
- **Valiosa:** cierra el ciclo del resultado enviado.
- **Estimable:** un endpoint, un filtro y un componente.
- **Pequeña:** cabe en un sprint.
- **Testeable:** 409, evento, aparición en leaderboard.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
