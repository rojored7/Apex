# US-178 · Como coach quiero registrar el peso y las medidas corporales de un socio cifradas para seguir su evolución sin exponer datos de salud

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (esquema `athletes`, módulo `athletes`)
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Atleta_Perfil` (`/socios/:id/atleta`, subpestaña Medidas)

## Historia

Como coach
quiero registrar el peso, la estatura y el porcentaje de grasa de un socio en una fecha
para mostrarle su evolución corporal sin que esos datos de salud queden en claro en la base

## Contexto de dominio

- **Aggregate / entidades:** raíz lógica `Member`; entidad `BodyMetric` (`member_id`, `measured_at`, `weight_kg`, `height_cm`, `body_fat_pct`, `notes`, `recorded_by`).
- **Reglas que aplica:** RN-13 (medidas corporales cifradas por clase de dato), Q21 (todas las medidas de `body_metrics` bajo `athlete.metric`; solo `measured_at` y `member_id` en claro), RN-15 (rol por endpoint), RN-14 (las medidas no se borran por API).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `athletes.validate_metric(weight_kg, height_cm, body_fat_pct) -> None | MetricError`

## Alcance

- **Backend:** modelo `BodyMetric` con columnas `Encrypted("athlete.metric")` para `weight_kg`, `height_cm`, `body_fat_pct` y `notes`; `athletes.service.add_metric(member_id, data, by)` y `list_metrics(member_id, limit, offset)`; valida que el socio exista y no esté dado de baja vía `members.service`.
- **Front:** subpestaña Medidas de `Atleta_Perfil` con lista paginada (valores enmascarados con `MaskedValue`) y formulario en `SidePanel` para registrar una medición.

## Criterios de aceptación

1. `POST /api/v1/athletes/{member_id}/metrics` con rol admin o coach crea un `BodyMetric` y responde 201 con `id`, `measured_at` y los campos de medida enmascarados.
2. `weight_kg`, `height_cm`, `body_fat_pct` y `notes` se guardan como blob `apx1.*` con `data_class = athlete.metric` y `aad = id` del registro; `SELECT weight_kg FROM athletes.body_metrics` no devuelve ningún número en claro (prueba de arquitectura).
3. Solo `id`, `member_id`, `measured_at` y las columnas comunes quedan en claro.
4. `measured_at` se recibe y se devuelve en ISO 8601 UTC con zona; no se acepta una fecha futura respecto a `now()` (422 con `field = measured_at`).
5. Validación: `weight_kg` entre 20 y 400, `height_cm` entre 50 y 250, `body_fat_pct` entre 1 y 75; al menos uno de los tres presente; fuera de rango o todos vacíos devuelve 422 con `field`.
6. `GET /api/v1/athletes/{member_id}/metrics` pagina con `limit` (1 a 200, por defecto 25) y `offset`, ordena por `measured_at` descendente y responde `{ items, total, limit, offset }` con valores enmascarados; listar no descifra ni audita.
7. Un socio inexistente o dado de baja devuelve 404 en ambos endpoints.
8. Un usuario con rol `member` recibe 403 en ambos endpoints (su acceso es por `/me/metrics`, US-191); sin token, 401.
9. `body_metrics` está marcada `__audited__ = True`; el alta deja una fila de auditoría `insert` donde los campos de medida aparecen como blob, nunca en claro.
10. No existe endpoint de borrado ni edición de medidas; una corrección es una medición nueva.
11. Cada cifrado deja una fila en `crypto_ops` con verbo `encrypt` y `data_class = athlete.metric`.

## Escenarios BDD

```gherkin
# language: es
Característica: Registrar medidas corporales cifradas

  Antecedentes:
    Dado que existe la socia "Laura Gómez" activa
    Y que la coach "Ana" inició sesión

  Escenario: La coach registra una medición completa
    Cuando registra para "Laura Gómez" peso 62,5 kg, estatura 165 cm y grasa 24 % con fecha de hoy
    Entonces la medición aparece en la subpestaña Medidas con los valores enmascarados
    Y la base guarda peso, estatura y grasa como blobs cifrados con la clase "athlete.metric"
    Y la auditoría registra el alta sin valores en claro

  Escenario: Medición con peso fuera de rango
    Cuando registra para "Laura Gómez" un peso de 900 kg
    Entonces el sistema rechaza la medición con el error en el campo "weight_kg"
    Y no se guarda ninguna medición
```

## Endpoints

- `POST /api/v1/athletes/{member_id}/metrics` — rol(es): admin, coach — entrada: `{ measured_at, weight_kg?, height_cm?, body_fat_pct?, notes? }` — salida: `BodyMetricOut` enmascarado — códigos: 201, 401, 403, 404, 422
- `GET /api/v1/athletes/{member_id}/metrics?limit&offset` — rol(es): admin, coach — salida: página de `BodyMetricOut` enmascarados — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Atleta_Perfil`, subpestaña Medidas: tabla de mediciones con fecha en hora de Bogotá, valores con `MaskedValue`, botón "Registrar medición" que abre `SidePanel`. Estados de carga, vacío ("Aún no hay mediciones") y error.

## Notas técnicas

- **Migración:** sí; esquema `athletes` y tabla `body_metrics` con columnas cifradas de texto, índice por (`member_id`, `measured_at`).
- **Trigger / restricciones:** sin `DELETE` desde la aplicación; no se requiere trigger de inmutabilidad (no está en la lista de `04_architecture_decision.md` sección 7).
- **Funciones puras a probar:** `validate_metric` con límites inferiores y superiores exactos y con los tres campos vacíos.
- **Pruebas:** pura; service con base real (blob en base, AAD, crypto_ops, auditoría); router (roles, 404, 422); arquitectura (columna sin claro); Vitest del formulario y la tabla.
- **Archivos principales:** `api/src/app/modules/athletes/{models,schemas,service,router}.py`, `web/src/features/athletes/`.

## Supuestos

- Supuesto: los rangos válidos de peso (20 a 400 kg), estatura (50 a 250 cm) y grasa (1 a 75 %) no están definidos en el dominio; se fijan para validar entrada.
- Supuesto: los valores se guardan como decimales en texto antes de cifrar (el cifrado opera sobre bytes); RN-01 aplica solo a dinero.

## Dependencias

- US-028 · Tipos de columna Encrypted y BlindIndexed (cifrado por `athlete.metric`)
- US-073 · Ver ficha del socio (contenedor donde vive la pestaña Atleta)

## INVEST

- **Independiente:** solo requiere el bus y la ficha; no depende de resultados.
- **Negociable:** los rangos y los campos visibles se pueden ajustar.
- **Valiosa:** el coach muestra progreso al socio, motivo principal de renovación.
- **Estimable:** un modelo, dos endpoints y una subpestaña.
- **Pequeña:** cabe en un sprint.
- **Testeable:** blob en base, 422 por rango, 403 por rol.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
