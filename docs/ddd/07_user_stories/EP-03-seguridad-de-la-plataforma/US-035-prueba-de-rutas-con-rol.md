# US-035 · Como equipo quiero una prueba de arquitectura que falle si una ruta no declara rol para que ningún endpoint nuevo quede público por descuido

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core/security` (`api/tests/architecture/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `test_every_route_has_role.py` que recorra las rutas registradas en `create_app()`
para que CI rechace cualquier endpoint sin `require_role` que no esté en la lista blanca

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** RN-15 (nada sin rol salvo login, recuperación y health); `04_architecture_decision.md` sección 6 (lista blanca).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `route_has_role_dependency(route) -> bool`

## Alcance

- **Backend:** la prueba instancia la app, recorre `app.routes` (incluidas las de `include_router`) y para cada `APIRoute` busca en su árbol de dependencias la marca de `require_role`. Lista blanca exacta: `GET /health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/forgot`, `POST /api/v1/auth/reset`, `GET /api/v1/tv/today` (esta última protegida por token de dispositivo desde v0.5). Rutas de documentación OpenAPI deshabilitadas en producción o en la lista blanca solo si `ENV=dev`.
- **Front:** No aplica

## Criterios de aceptación

1. La prueba pasa con la app actual.
2. Agregar una ruta `GET /api/v1/prueba` sin `require_role` hace fallar la prueba con método y ruta en el mensaje.
3. Una ruta de la lista blanca sin rol no hace fallar la prueba.
4. Una ruta de la lista blanca que cambie de método (por ejemplo `GET /api/v1/auth/login`) sí falla: la lista blanca compara método y ruta.
5. La lista blanca vive en un solo lugar (`core/security.PUBLIC_ROUTES`) y la usan la prueba y la documentación.
6. `/docs` y `/openapi.json` no se sirven cuando `ENV=prod`.

## Escenarios BDD

```gherkin
# language: es
Característica: Toda ruta declara rol

  Escenario: Todas las rutas protegidas o públicas por lista blanca
    Dado la aplicación con sus routers registrados
    Cuando corre test_every_route_has_role
    Entonces la prueba pasa

  Escenario: Ruta nueva sin rol
    Dado un router que agrega GET /api/v1/prueba sin require_role
    Cuando corre la prueba
    Entonces falla indicando "GET /api/v1/prueba"

  Escenario: Método distinto en ruta pública
    Dado una ruta GET /api/v1/auth/login sin rol
    Cuando corre la prueba
    Entonces falla porque solo POST está en la lista blanca
```

## Endpoints

- Ninguno propio.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `route_has_role_dependency` con rutas sintéticas.
- **Pruebas:** arquitectura.
- **Archivos principales:** `api/tests/architecture/test_every_route_has_role.py`, `api/src/app/core/security.py`.

## Supuestos

- Supuesto: `/docs` y `/openapi.json` en vivo se deshabilitan en producción; el contrato se publica como archivo `docs/openapi.json` (US-021).

## Dependencias

- US-034 · Dependencias current_user y require_role

## INVEST

- **Independiente:** solo la dependencia de rol.
- **Negociable:** tratamiento de las rutas de documentación.
- **Valiosa:** cierra la puerta al olvido.
- **Estimable:** una prueba.
- **Pequeña:** un día.
- **Testeable:** un PR de control debe fallar.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
