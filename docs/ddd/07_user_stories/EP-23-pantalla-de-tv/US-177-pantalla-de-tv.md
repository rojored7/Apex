# US-177 · Como dispositivo TV quiero mostrar el WOD del día y el leaderboard actualizados cada 30 segundos para reemplazar la pizarra de la pared

- **Épica:** EP-23 · Pantalla de TV del box
- **Bounded context:** TV (front `web/src/features/tv/`)
- **Versión:** v0.5
- **Actor:** dispositivo TV
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `TV` (`/tv?token=…`)

## Historia

Como dispositivo TV
quiero mostrar a 1920 × 1080 el WOD del día y el leaderboard, refrescados solos cada 30 segundos
para que los atletas vean su marca al lado de la de los demás sin preguntarle al coach

## Contexto de dominio

- **Aggregate / entidades:** ninguno (consume `GET /tv/today`).
- **Reglas que aplica:** sin interacción; solo tema oscuro; sin datos personales salvo nombre, nivel y marca.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `tv.formatScore(score_type, score)` en el front (`4:05`, `5 + 12`, `150 reps`, `100 kg`)

## Alcance

- **Backend:** No aplica (US-176).
- **Front:** página `TV` en `TvLayout`, ruta pública `/tv` fuera de las guardas de sesión; lee `token` de la URL, lo guarda en memoria y lo envía en `X-Device-Token`; refresco con TanStack Query cada `refresh_seconds` (30); estados "Sin WOD publicado", "Token inválido" y "Sin conexión, mostrando la última información".

## Criterios de aceptación

1. `/tv?token=…` muestra el título, tipo de marca, time cap y movimientos del WOD de hoy, y el leaderboard con posición, nombre, nivel y marca, en 1920 × 1080 sin barras de desplazamiento.
2. La pantalla pide `GET /api/v1/tv/today` cada 30 segundos; un resultado nuevo aparece en menos de 30 segundos después de registrarse en la tablet.
3. Con 401 la pantalla muestra "Token inválido. Pide un enlace nuevo en Configuración" y deja de reintentar cada 30 s (reintenta cada 5 minutos).
4. Sin red o con error 5xx mantiene la última información visible con un indicador discreto de "Sin conexión" y sigue reintentando.
5. Sin WOD (`wod: null`) muestra el logo y "Sin WOD publicado".
6. No hay botones, enlaces ni elementos que respondan a clic o teclado; el cursor se oculta.
7. Usa solo tokens de `tokens.css` en tema oscuro; cero colores literales; contraste de 4,5:1 o más visto a distancia (tamaño de texto mínimo 28 px en el leaderboard).
8. Con más filas de las que caben, muestra las 15 primeras y rota las siguientes cada refresco.
9. Prueba de resistencia: 12 horas de refresco simulado sin crecimiento sostenido de memoria (prueba de Playwright con reloj acelerado y medición de heap).
10. La ruta no usa la sesión del panel; abrirla con sesión de admin no expone nada adicional.

## Escenarios BDD

```gherkin
# language: es
Característica: Pantalla de TV

  Escenario: La TV muestra el tablero y se actualiza sola
    Dado que la TV está abierta con un token vigente
    Y el WOD de hoy es "Fran" con 2 resultados
    Cuando el coach registra un tercer resultado en la tablet
    Entonces en menos de 30 segundos la TV muestra 3 filas en el leaderboard

  Escenario: Token inválido
    Dado que el administrador regeneró el token
    Cuando la TV refresca con el token anterior
    Entonces la TV muestra "Token inválido. Pide un enlace nuevo en Configuración"
```

## Endpoints

- `GET /api/v1/tv/today` — consumido, ver US-176.

## Pantalla

- `TV` de `docs/design/screens/` en `/tv?token=…`, `TvLayout` 1920 × 1080, tema oscuro; estados sin WOD, token inválido y sin conexión. `// DESIGN-GAP:` para el estado "sin conexión" y la rotación de filas si el diseño no los trae.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `formatScore` para los cuatro `score_type`.
- **Pruebas:** Vitest de la página con respuestas simuladas (200, 401, red caída, `wod: null`), Playwright con captura a 1920 × 1080, prueba de memoria de 12 h con reloj acelerado.
- **Archivos principales:** `web/src/features/tv/pages/TvPage.tsx`, `web/src/layouts/TvLayout.tsx`, `web/src/routes.tsx`.

## Supuestos

- Supuesto: con más filas de las que caben se rota por páginas de 15; el diseño y la épica no lo definen.
- Supuesto: tras un 401 se reintenta cada 5 minutos para que la TV se recupere sola si se le cambia la URL.

## Dependencias

- US-176 · Endpoint público de TV
- US-062 · Layouts portal, gym y TV

## INVEST

- **Independiente:** solo consume un endpoint.
- **Negociable:** diseño de filas y rotación.
- **Valiosa:** reemplaza la pizarra.
- **Estimable:** una página sin interacción.
- **Pequeña:** 3 puntos.
- **Testeable:** estados y tiempo de refresco verificables.

## Definición de terminado

- [ ] Front: pruebas de componente y página en verde; sin colores literales
- [ ] Captura de Playwright a 1920 × 1080 aprobada
- [ ] Prueba de 12 horas sin fuga de memoria en verde
- [ ] Chequeo automático de accesibilidad sin violaciones de contraste
- [ ] Revisión de PR aprobada
