# US-061 · Como equipo quiero el layout del panel con barra superior y menú lateral filtrado por rol para que admin y coach naveguen igual en todas las pantallas

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/layouts/`, `web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Base del panel; referencia `P_Lista`, `P_Ficha` e `Inicio` (`/`)

## Historia

Como equipo
quiero `PanelLayout` con `TopBar` y `SideNav`, donde el menú solo muestra lo que el rol puede ver
para que cada pantalla del panel se monte dentro del mismo marco y el coach no vea Planes ni Sistema

## Contexto de dominio

- **Aggregate / entidades:** ninguno; usa el rol del usuario de la sesión (`User.role`).
- **Reglas que aplica:** RN-15 (rol por endpoint; el front oculta, el API verifica); matriz de permisos de `ROUTES.md`; Q25 (el grupo "Hoy" son tres enlaces a pantallas existentes, no una ruta nueva).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `buildNavItems(role, enabledFeatures) -> NavItem[]`

## Alcance

- **Backend:** No aplica.
- **Front:** `PanelLayout` (grid TopBar + SideNav + contenido con `<main>`), `TopBar` (logo, nombre del gimnasio, menú de usuario con espacio para "Mi cuenta" y "Cerrar sesión", conmutador de tema), `SideNav` (grupos Inicio, Hoy, Socios, Planes, Membresías, Pagos, Clases, Movimientos, WODs, Avisos, Sistema), colapsable en tablet y como cajón en celular; usa `useCan` de US-040.

## Criterios de aceptación

1. `SideNav` se construye con `buildNavItems(role, enabledFeatures)`; para `coach` no incluye Planes ni ninguna entrada de Sistema; para `admin` incluye todas las entradas habilitadas.
2. Solo aparecen las entradas cuya épica ya existe (`enabledFeatures`); en v0.1 aparecen Inicio, Socios, Planes (admin), Membresías, Pagos y Sistema (Usuarios, Auditoría, Configuración) para admin.
3. El grupo "Hoy" (cuando existan sus pantallas) enlaza a `Sesiones` filtrada a hoy, `WOD_Detalle` del día y `PorAvisarHoy`, sin ruta propia (Q25); en v0.1 no se muestra.
4. La entrada activa se marca con `aria-current="page"` y con un indicador que no depende solo del color.
5. Todos los controles miden al menos 44 px y tienen foco visible; el orden de tabulación es TopBar, SideNav, contenido; existe enlace "Saltar al contenido".
6. En anchos menores a 768 px el menú lateral se oculta y se abre como cajón con botón de 44 px; el cajón se cierra con Escape y devuelve el foco al botón.
7. El layout usa solo tokens de `tokens.css`; cero colores, tamaños de fuente o familias literales.
8. Sin desbordes horizontales en 320, 768, 1024 y 1440 px, en claro y en oscuro.

## Escenarios BDD

```gherkin
# language: es
Característica: Layout del panel

  Escenario: Administrador ve todo el menú habilitado
    Dado un usuario con rol "admin"
    Cuando abre cualquier pantalla del panel
    Entonces el menú lateral muestra Inicio, Socios, Planes, Membresías, Pagos y Sistema

  Escenario: Coach no ve Planes ni Sistema
    Dado un usuario con rol "coach"
    Cuando abre cualquier pantalla del panel
    Entonces el menú lateral no muestra Planes
    Y no muestra Usuarios, Auditoría, Llaves ni Configuración

  Escenario: Menú en celular
    Dado una pantalla de 390 px de ancho
    Cuando el usuario pulsa el botón de menú
    Entonces se abre el cajón con las entradas de su rol
    Y al pulsar Escape el cajón se cierra y el foco vuelve al botón

  Escenario: Entrada de una épica no habilitada
    Dado que la épica de Clases no está habilitada
    Cuando se construye el menú para un administrador
    Entonces la entrada Clases no aparece
```

## Endpoints

- Ninguno.

## Pantalla

- Marco común de las pantallas del panel (`Inicio`, `Socios_Lista`, `Socio_Ficha`, `Planes`, `Membresias`, `Pagos`, `Usuarios`, `Auditoria`, `Config` y siguientes). `// DESIGN-GAP:` si el diseño no define el cajón en celular.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `buildNavItems` con `admin`, `coach`, `member` (devuelve lista vacía: el socio usa `PortalLayout`) y distintas combinaciones de `enabledFeatures`.
- **Pruebas:** Vitest y Testing Library (render por rol, `aria-current`, teclado), prueba de accesibilidad con `axe`, capturas en los cuatro anchos.
- **Archivos principales:** `web/src/layouts/PanelLayout.tsx`, `web/src/shared/ui/TopBar.tsx`, `web/src/shared/ui/SideNav.tsx`, `web/src/layouts/nav.ts`.

## Supuestos

- Ninguno.

## Dependencias

- US-010 · Componentes base Button, Field, StatusTag.
- US-040 · Matriz de permisos del front (`useCan`).

## INVEST

- **Independiente:** no necesita API; el rol llega por contexto simulado en pruebas.
- **Negociable:** comportamiento en tablet (colapsado o cajón) se puede ajustar.
- **Valiosa:** marco de todas las pantallas del panel.
- **Estimable:** tres componentes y una función pura.
- **Pequeña:** 4 a 5 días.
- **Testeable:** render por rol, teclado y capturas.

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
