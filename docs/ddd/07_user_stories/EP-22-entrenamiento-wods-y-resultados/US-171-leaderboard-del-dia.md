# US-171 · Como coach quiero un leaderboard del WOD por nivel y sexo para que los atletas comparen sus marcas

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (módulo `results`), Conformist de Members (nombre y sexo)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `WOD_Detalle` (`/wods/:id`, sección leaderboard)

## Historia

Como coach
quiero ver el leaderboard de un WOD ordenado según su tipo de marca y filtrable por nivel y sexo
para mostrarle al box quién hizo qué y motivar a los atletas

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` (lectura de los `is_current` y `validated`), `Member` (solo `first_name`, `last_name`, `sex` vía `members.service`).
- **Reglas que aplica:** orden del `Score`: `time` ascendente, los demás descendente; `scaled` siempre después de `rx` y `rx_plus`; Q22: socios con `sex` nulo solo aparecen en el filtro "Todos"; Training nunca lee campos cifrados.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `results.leaderboard_order(score_type) -> key function`

## Alcance

- **Backend:** `results.service.leaderboard(wod_id, level?, sex?)` compone resultados con `members.service.public_names(ids)` (nombre, apellido, sexo); `GET /wods/{id}/leaderboard`.
- **Front:** sección de leaderboard en `WOD_Detalle` con `Chips` de nivel (Todos, RX+, RX, Escalado) y de sexo (Todos, F, M).

## Criterios de aceptación

1. `GET /api/v1/wods/{id}/leaderboard` devuelve posición, `member_id`, nombre, apellido abreviado, `level` y la marca formateable, solo de resultados `is_current = true` y `status = validated`.
2. Orden: primero `rx_plus` y `rx` mezclados según la marca, después `scaled`; dentro de cada grupo, `time` ascendente; `rounds_reps` por rondas y luego reps descendente; `reps` y `load` descendente.
3. Empates en la marca comparten posición y se desempatan para mostrar por apellido (orden estable); un resultado `time` que no terminó dentro del time cap se trata según el supuesto declarado.
4. `level` filtra por nivel; `sex=f` y `sex=m` excluyen a socios con `sex` nulo o `x`; sin `sex` (Todos) los incluye a todos (Q22).
5. Parámetros fuera del enum devuelven 422 con `field`.
6. La respuesta no contiene documento, teléfono, correo, fecha de nacimiento ni ningún campo cifrado (prueba de contrato y prueba de arquitectura de que `results` no llama a `reveal` ni a `decrypt`).
7. Solo admin y coach en esta ruta; `member` recibe 403 (la TV usa `/tv/today`, US-176).
8. Con 60 resultados el endpoint responde en menos de 300 ms.

## Escenarios BDD

```gherkin
# language: es
Característica: Leaderboard del WOD

  Escenario: Orden por tiempo con escalados al final
    Dado que el WOD "Fran" es de tipo de marca "time"
    Y Ana hizo 245 segundos en "rx", Juan 230 segundos en "scaled" y Laura 260 segundos en "rx_plus"
    Cuando consulto el leaderboard de "Fran" con todos los niveles
    Entonces el orden es Ana, Laura y Juan

  Escenario: Socio sin sexo registrado
    Dado que Pedro tiene resultado en "Fran" y su sexo no está registrado
    Cuando filtro el leaderboard por sexo "M"
    Entonces Pedro no aparece
    Y cuando quito el filtro de sexo Pedro aparece
```

## Endpoints

- `GET /api/v1/wods/{id}/leaderboard` — rol(es): admin, coach — entrada: `level?` (`rx` | `rx_plus` | `scaled`), `sex?` (`f` | `m`), `limit`, `offset` — salida: `{ items, total, limit, offset }` — códigos: 200, 401, 403, 404, 422

## Pantalla

- `WOD_Detalle` en `/wods/:id`: tabla del leaderboard con chips de filtro, estado vacío "Aún no hay resultados".

## Notas técnicas

- **Migración:** no; índice en `results.wod_results (wod_id) WHERE is_current` si el plan de consulta lo pide.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `leaderboard_order` con casos de empate, mezcla de niveles, `rounds_reps` con mismas rondas y distintas reps, `load` descendente.
- **Pruebas:** puras, service con base real, contrato sin campos cifrados, front.
- **Archivos principales:** `api/src/app/modules/results/service.py`, `api/src/app/modules/members/service.py` (`public_names`), `web/src/features/wods/components/Leaderboard.tsx`.

## Supuestos

- Supuesto: `members.service.public_names(ids)` es una consulta nueva del service de Members que devuelve solo `first_name`, `last_name` y `sex`.
- Supuesto: en un WOD `time`, un resultado sin terminar dentro del time cap se registra con `seconds = time_cap_s` y reps logradas, y ordena después de todos los que terminaron; el dominio no lo define (pregunta abierta).
- Supuesto: `rx_plus` y `rx` comparten grupo y se ordenan solo por marca; el dominio solo dice que `scaled` va después.

## Dependencias

- US-169 · Registrar resultados en tablet

## INVEST

- **Independiente:** lectura pura sobre resultados existentes.
- **Negociable:** formato de la marca y abreviatura de apellido ajustables.
- **Valiosa:** es lo que el atleta mira al terminar la clase.
- **Estimable:** una consulta y una función de orden.
- **Pequeña:** sin escrituras.
- **Testeable:** el orden es una función pura con casos concretos.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
