# US-176 · Como dispositivo TV quiero leer el WOD del día y su leaderboard con mi token para mostrarlos en la pared del box sin datos personales

- **Épica:** EP-23 · Pantalla de TV del box
- **Bounded context:** TV (módulo `tv`, sin esquema), Conformist de Training y Settings
- **Versión:** v0.5
- **Actor:** dispositivo TV
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; la consume US-177)

## Historia

Como dispositivo TV
quiero pedir con mi token el WOD de hoy y su leaderboard
para mostrarlos en la pared del box sin sesión de usuario y sin exponer datos personales

## Contexto de dominio

- **Aggregate / entidades:** ninguno propio; lee `Wod` y `WodResult` por `wods.service` y `results.service`, valida el token por `settings.service.verify_tv_token`.
- **Reglas que aplica:** RN-15 (ruta en la lista blanca sin rol, protegida por token de dispositivo de solo lectura); seguridad de la arquitectura: la TV no ve datos personales salvo nombre y marca; Q22 (sexo nulo solo en "Todos"); Q28 (`today_bogota()`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `tv.to_public_board(wod, leaderboard) -> TvBoard` (proyección que solo deja campos permitidos)

## Alcance

- **Backend:** `tv.service.today(token)` compone WOD de hoy y leaderboard con `results.service.leaderboard`; `tv.router` con `GET /tv/today`; ruta incluida en la lista blanca de `test_every_route_has_role.py`.
- **Front:** No aplica (US-177).

## Criterios de aceptación

1. `GET /api/v1/tv/today` con token válido (cabecera `X-Device-Token` o parámetro `token`) responde 200 con `{ date, wod: { title, score_type, time_cap_s, movements: [{ name, reps, load_rx_m_kg, load_rx_f_kg }] } | null, leaderboard: [{ position, display_name, level, score }] }`.
2. Sin token, con token rotado o con token inventado responde 401 con el envelope de error; no revela si existió.
3. `display_name` es nombre y la inicial del apellido; la respuesta no contiene `member_id`, documento, teléfono, correo, fecha de nacimiento, sexo, notas ni ningún campo cifrado (prueba de contrato que falla si aparece un campo fuera de la lista permitida).
4. El leaderboard incluye solo resultados `is_current` y `validated`, en el orden de `leaderboard_order`, con todos los niveles y sexos (filtro "Todos") y como máximo 50 filas.
5. Sin WOD publicado hoy responde 200 con `wod: null` y `leaderboard: []`.
6. La ruta está en la lista blanca de la prueba de arquitectura de roles y es la única de esa lista que exige token de dispositivo.
7. El endpoint aplica rate limit de 12 peticiones por minuto por IP para evitar sondeos del token.
8. La comparación del token es en tiempo constante (contra el hash, US-175).

## Escenarios BDD

```gherkin
# language: es
Característica: Endpoint público de la TV

  Escenario: La TV lee el WOD y el leaderboard
    Dado que el WOD de hoy es "Fran" con 3 resultados validados
    Cuando la TV pide el tablero del día con su token vigente
    Entonces recibe "Fran" con sus movimientos
    Y recibe 3 filas de leaderboard con nombre, nivel y marca
    Y ninguna fila trae documento, teléfono ni correo

  Escenario: Token rotado
    Dado que el administrador regeneró el token de la TV
    Cuando la TV pide el tablero del día con el token anterior
    Entonces la petición es rechazada como no autorizada
```

## Endpoints

- `GET /api/v1/tv/today` — rol(es): ninguno (lista blanca), token de dispositivo obligatorio — entrada: `X-Device-Token` o `?token=` — salida: ver criterio 1 — códigos: 200, 401, 429

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `to_public_board` descarta campos no permitidos; formato de `display_name` ("Ana P.").
- **Pruebas:** router (401 sin token, con token rotado; 200 con token), contrato de campos permitidos, prueba de arquitectura de rutas (lista blanca), rate limit.
- **Archivos principales:** `api/src/app/modules/tv/{router,schemas,service}.py`, `api/tests/architecture/test_every_route_has_role.py`.

## Supuestos

- Supuesto: `display_name` es nombre más inicial del apellido; la épica dice "nombre", y la inicial reduce la exposición si el token se filtra.
- Supuesto: rate limit de 12 por minuto (refresco cada 30 s más margen); no está fijado en los documentos.
- Supuesto: se acepta el token por parámetro de URL porque `ROUTES.md` abre la TV con `/tv?token=…`; Nginx no debe registrar la query string en el log de acceso para esta ruta.

## Dependencias

- US-175 · Token de dispositivo de TV
- US-171 · Leaderboard del día
- US-035 · Prueba de rutas con rol (lista blanca)

## INVEST

- **Independiente:** compone services ya existentes.
- **Negociable:** forma de pasar el token y número de filas.
- **Valiosa:** habilita la TV del box.
- **Estimable:** un endpoint de lectura.
- **Pequeña:** 3 puntos.
- **Testeable:** 401 y contrato de campos verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Prueba de contrato sin datos personales en verde
- [ ] Prueba de arquitectura de rutas actualizada
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
