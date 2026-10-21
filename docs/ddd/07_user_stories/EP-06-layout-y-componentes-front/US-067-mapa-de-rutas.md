# US-067 · Como equipo quiero el mapa de rutas del front con habilitación por épica para que cada pantalla aparezca solo cuando su API existe

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/routes.tsx`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Mapa` (solo referencia, no se implementa)

## Historia

Como equipo
quiero `routes.tsx` con todas las rutas de `ROUTES.md` declaradas y una bandera por épica
para que la navegación siga el diseño y una ruta cuya épica no existe responda "no encontrada" en lugar de una pantalla rota

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** S4 (cada pantalla entra en el sprint en que existe su API); Q25 (no hay ruta "Hoy"); permisos por rol de `ROUTES.md` (la guarda la conecta US-053).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `isRouteEnabled(route, enabledFeatures) -> boolean`

## Alcance

- **Backend:** No aplica.
- **Front:** `web/src/routes.tsx` con React Router 7: grupos Acceso (`/login`, `/recuperar`, `/restablecer/:token`, `/tv`), Panel (`PanelLayout`), Portal (`/mi/*`, `PortalLayout`), tablet (`/clases/:id/checkin`, `/clases/:id/resultados`, `GymLayout`); cada ruta declara `feature` (épica), `roles` permitidos y carga diferida (`lazy`); `enabledFeatures` desde un archivo de configuración versionado; página 404 propia.

## Criterios de aceptación

1. Están declaradas todas las rutas de `ROUTES.md` con su `feature` y sus `roles`; una prueba compara la lista contra un archivo de referencia derivado de `ROUTES.md`.
2. Una ruta cuya `feature` no está en `enabledFeatures` muestra la página 404 y no carga su código.
3. Cada página se carga de forma diferida; el bundle inicial no incluye páginas de negocio.
4. No existe ninguna ruta `/hoy` (Q25).
5. Las rutas de tablet usan `GymLayout`, las del portal `PortalLayout`, la de TV `TvLayout` y el resto `PanelLayout`.
6. Los parámetros de ruta usan los nombres de `ROUTES.md` (`/socios/:id`, `/membresias/vender?socio=:id&renovar=1`).

## Escenarios BDD

```gherkin
# language: es
Característica: Mapa de rutas

  Escenario: Ruta habilitada
    Dado que la épica de socios está habilitada
    Cuando el usuario navega a "/socios"
    Entonces se carga la página de lista de socios dentro del layout del panel

  Escenario: Ruta de una épica no habilitada
    Dado que la épica de clases no está habilitada
    Cuando el usuario navega a "/clases"
    Entonces se ve la página "No encontrada"
    Y no se descarga el código de la página de sesiones

  Escenario: Ruta inexistente
    Dado cualquier usuario
    Cuando navega a "/hoy"
    Entonces se ve la página "No encontrada"
```

## Endpoints

- Ninguno.

## Pantalla

- `Mapa` como referencia del árbol de navegación; no se implementa como pantalla.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `isRouteEnabled` con rutas habilitadas, deshabilitadas y sin `feature`.
- **Pruebas:** Testing Library con `MemoryRouter`; prueba de inventario de rutas; revisión del tamaño del bundle inicial en el build.
- **Archivos principales:** `web/src/routes.tsx`, `web/src/config/features.ts`, `web/src/pages/NotFound.tsx`.

## Supuestos

- Supuesto: `enabledFeatures` es una lista en código versionada (no viene del API); se actualiza en cada épica.

## Dependencias

- US-061 · Panel layout, TopBar y SideNav.

## INVEST

- **Independiente:** solo depende del layout del panel.
- **Negociable:** origen de las banderas.
- **Valiosa:** permite entregar pantallas por versión sin romper navegación.
- **Estimable:** un archivo de rutas y una prueba de inventario.
- **Pequeña:** 1 a 2 días.
- **Testeable:** navegación y 404 verificables.

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
