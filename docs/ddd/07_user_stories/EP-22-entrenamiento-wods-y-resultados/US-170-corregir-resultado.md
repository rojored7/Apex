# US-170 · Como coach quiero corregir un resultado mal registrado sin borrarlo para que la marca correcta quede vigente y el error quede en el historial

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (esquema `results`, módulo `results`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Resultados_Registro` (`/clases/:id/resultados`)

## Historia

Como coach
quiero corregir un resultado registrando uno nuevo que reemplaza al anterior
para que el leaderboard y el historial muestren la marca correcta sin perder la traza del error

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` con `supersedes_id` e `is_current`.
- **Reglas que aplica:** RN-11, RN-14 (nunca se borra), Q18 (corregir crea uno nuevo con `supersedes_id` y pone `is_current = false` en el anterior).
- **Eventos que emite:** `WodResultRecorded`, `WodResultValidated` (del nuevo, ver supuesto de US-169)
- **Eventos que consume:** ninguno
- **Funciones puras:** `results.validate_score`

## Alcance

- **Backend:** `results.service.correct(supersedes_id, data, by)` vía `PUT /results` con `supersedes_id`; en una transacción: `is_current = false` en el anterior e inserción del nuevo.
- **Front:** en `Resultados_Registro`, acción "Corregir" sobre una fila con resultado, que precarga los valores y exige confirmación.

## Criterios de aceptación

1. `PUT /api/v1/results` con `supersedes_id` de un resultado vigente del mismo socio y WOD crea el nuevo resultado (`is_current = true`) y deja el anterior con `is_current = false`, en la misma transacción; responde 201.
2. Ninguna fila se borra; el anterior conserva todos sus valores (prueba de que el trigger solo permitió cambiar `is_current`).
3. `supersedes_id` que no es vigente, que es de otro socio o de otro WOD devuelve 409 con `code = "invalid_supersedes"`.
4. El nuevo resultado pasa `validate_score` igual que un registro nuevo (422 si falla) y, si falla, el anterior sigue vigente.
5. El leaderboard (US-171) y la ficha (US-173) solo muestran resultados `is_current`.
6. Solo admin y coach; `member` recibe 403.
7. La corrección deja dos entradas de auditoría: el `update` de `is_current` y el `insert` del nuevo.

## Escenarios BDD

```gherkin
# language: es
Característica: Corregir resultado

  Escenario: Corregir un tiempo mal digitado
    Dado que Ana Pérez tiene en "Fran" un resultado vigente de 425 segundos registrado por error
    Cuando lo corrijo a 245 segundos
    Entonces el resultado vigente de Ana Pérez en "Fran" es de 245 segundos
    Y el resultado de 425 segundos sigue existiendo como reemplazado

  Escenario: Reemplazar un resultado que ya no es vigente
    Dado que el resultado de 425 segundos de Ana Pérez ya fue reemplazado
    Cuando intento corregir de nuevo ese resultado de 425 segundos
    Entonces el sistema rechaza la corrección indicando que el resultado no es el vigente
```

## Endpoints

- `PUT /api/v1/results` — rol(es): admin, coach — entrada: igual que US-169 más `supersedes_id` — salida: resultado nuevo — códigos: 201, 401, 403, 404, 409, 422

## Pantalla

- `Resultados_Registro`: botón "Corregir" por fila y modal de confirmación (`ConfirmModal`).

## Notas técnicas

- **Migración:** no (columnas creadas en US-169).
- **Trigger / restricciones:** el índice único parcial obliga a apagar `is_current` del anterior antes de insertar el nuevo dentro de la transacción.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** service con base real (orden de operaciones, rollback si falla la validación, concurrencia de dos correcciones simultáneas: una gana y la otra recibe 409), router.
- **Archivos principales:** `api/src/app/modules/results/service.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-169 · Registrar resultados en tablet

## INVEST

- **Independiente:** extiende el registro sin cambiar su contrato.
- **Negociable:** UI de la corrección ajustable.
- **Valiosa:** permite arreglar errores sin romper la inmutabilidad.
- **Estimable:** una operación transaccional.
- **Pequeña:** un caso de uso.
- **Testeable:** estados de `is_current` verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `results.wod_results`
- [ ] Revisión de PR aprobada
