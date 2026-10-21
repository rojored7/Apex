# US-062 · Como equipo quiero los layouts de portal, tablet del box y TV para que cada dispositivo tenga su marco listo antes de que lleguen sus pantallas

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/layouts/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Referencia `Portal_Inicio` (`/mi`), `CheckIn` (`/clases/:id/checkin`), `TV` (`/tv`)

## Historia

Como equipo
quiero `PortalLayout`, `GymLayout` y `TvLayout`
para que el portal del socio, la tablet del piso y la TV de la pared se construyan sobre marcos probados y accesibles

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** restricciones no funcionales de `01_product_discovery.md` sección 6 (44 px, 56 px en tablet, foco visible, contraste 4,5:1, el color nunca es el único portador de significado); TV sin interacción y solo tema oscuro (EP-23).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:** `PortalLayout` (una columna, ancho máximo para 390 px, menú inferior fijo con seis destinos: Inicio, Pagos, WODs, Progreso, Datos, Avisos); `GymLayout` (tema oscuro forzado, controles de 56 px, tipografía ampliada, sin SideNav, barra superior mínima con nombre de la sesión y salida); `TvLayout` (1920 × 1080 fijo, tema oscuro, sin foco ni cursor, sin elementos interactivos).

## Criterios de aceptación

1. `PortalLayout` muestra el menú inferior con seis destinos; cada destino tiene icono y texto, mide al menos 44 px de alto y marca el activo con `aria-current="page"`.
2. `PortalLayout` no tiene desbordes horizontales en 320 y 390 px; el contenido no queda tapado por el menú inferior (relleno inferior igual a su alto).
3. `GymLayout` fuerza el tema oscuro sin depender de la preferencia del sistema y todos sus controles miden al menos 56 px.
4. `TvLayout` renderiza a 1920 × 1080 sin barras de desplazamiento, oculta el cursor y no contiene ningún elemento enfocable.
5. Los tres layouts usan solo tokens de `tokens.css`.
6. Los tres pasan el chequeo automático de accesibilidad (`axe`) sin violaciones de contraste ni de foco.
7. Ningún layout hace peticiones al API; reciben su contenido como hijos.

## Escenarios BDD

```gherkin
# language: es
Característica: Layouts por dispositivo

  Escenario: Portal en celular
    Dado una pantalla de 390 por 844
    Cuando se monta una página dentro de PortalLayout
    Entonces se ve el menú inferior con Inicio, Pagos, WODs, Progreso, Datos y Avisos
    Y el último elemento del contenido queda visible por encima del menú

  Escenario: Tablet del box en tema oscuro
    Dado que el sistema operativo prefiere tema claro
    Cuando se monta una página dentro de GymLayout
    Entonces la página se ve en tema oscuro
    Y cada botón mide al menos 56 px de alto

  Escenario: TV sin interacción
    Dado una página montada en TvLayout
    Cuando se recorre la página con la tecla Tab
    Entonces ningún elemento recibe foco

  Escenario: Contraste insuficiente
    Dado un cambio que usa un token de texto con contraste menor a 4,5:1 sobre el fondo de GymLayout
    Cuando corre el chequeo de accesibilidad
    Entonces el chequeo falla
```

## Endpoints

- Ninguno.

## Pantalla

- Marcos de `Portal_*` (EP-25), `CheckIn` y `Resultados_Registro` (EP-21, EP-22) y `TV` (EP-23). En v0.1 se prueban con contenido de ejemplo en Vitest y en una página de muestra no enrutada.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Testing Library (menú inferior, `aria-current`, ausencia de foco en TV), `axe`, capturas de Playwright a 390 × 844, 1024 × 768 y 1920 × 1080.
- **Archivos principales:** `web/src/layouts/PortalLayout.tsx`, `web/src/layouts/GymLayout.tsx`, `web/src/layouts/TvLayout.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-061 · Panel layout, TopBar y SideNav (patrón y tokens de layout).

## INVEST

- **Independiente:** no necesita API ni pantallas de negocio.
- **Negociable:** los iconos y textos del menú inferior.
- **Valiosa:** adelanta el marco de tres dispositivos y su accesibilidad.
- **Estimable:** tres componentes de layout.
- **Pequeña:** 4 a 5 días.
- **Testeable:** medidas, foco y capturas verificables.

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
