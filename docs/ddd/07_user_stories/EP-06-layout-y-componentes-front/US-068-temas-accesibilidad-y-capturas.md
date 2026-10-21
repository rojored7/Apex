# US-068 · Como equipo quiero temas claro y oscuro, chequeo automático de accesibilidad y capturas por ancho para que ningún componente salga con contraste pobre, desbordes o colores literales

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Todas (kit y layouts)

## Historia

Como equipo
quiero los temas claro y oscuro definidos con tokens, un chequeo de accesibilidad en CI y capturas en 320, 768, 1024 y 1440 px
para que recepción, la tablet y el celular vean un sistema legible y consistente, y que una regresión visual se detecte antes de mezclar

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** restricciones no funcionales de accesibilidad (44 px, 56 px en tablet, foco visible, contraste 4,5:1, color nunca único portador de significado); criterios de EP-06 (cero colores literales, 16 componentes con 80 % de cobertura).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:** tema por atributo `data-theme` con preferencia del sistema y conmutador persistido en `localStorage` (con `try/catch`); chequeo `stylelint` o regla propia que rechaza hex, `rgb()`, `hsl()` y familias de fuente fuera de `tokens.css`; página de catálogo de componentes no enrutada en producción; Playwright con `@axe-core/playwright` sobre el catálogo y capturas en los cuatro anchos y dos temas; job de CI.

## Criterios de aceptación

1. Todos los colores, tipografías, espacios y radios de `shared/ui/` y `layouts/` vienen de variables de `tokens.css`; el chequeo de CI falla con un literal.
2. El tema oscuro redefine solo variables, sin estilos duplicados por componente.
3. El conmutador de tema funciona aunque `localStorage` no esté disponible (cae a la preferencia del sistema sin error).
4. `axe` no reporta violaciones de contraste, nombre accesible, rol ni foco en el catálogo de componentes y en los cuatro layouts, en ambos temas.
5. Las capturas en 320, 768, 1024 y 1440 px, en claro y oscuro, se guardan como artefacto de CI y ninguna muestra desplazamiento horizontal (prueba que compara `scrollWidth` con `clientWidth`).
6. Los 16 componentes del kit tienen prueba y la cobertura de `shared/ui/` es de 80 % o más.
7. Todo `StatusTag` del catálogo lleva texto además de color.

## Escenarios BDD

```gherkin
# language: es
Característica: Temas y accesibilidad del kit

  Escenario: Tema oscuro por preferencia del sistema
    Dado un navegador que prefiere tema oscuro
    Cuando se abre el catálogo de componentes
    Entonces los componentes usan las variables del tema oscuro

  Escenario: Color literal en un componente
    Dado un cambio que escribe "#ff0000" en un componente compartido
    Cuando corre el chequeo de estilos en CI
    Entonces el job falla señalando el archivo y la línea

  Escenario: Desborde horizontal
    Dado un componente que mide 400 px fijos
    Cuando se captura el catálogo a 320 px
    Entonces la prueba de desborde falla

  Escenario: Sin almacenamiento local
    Dado un navegador en modo privado sin acceso a localStorage
    Cuando el usuario cambia el tema
    Entonces el tema cambia en la sesión actual sin errores en pantalla
```

## Endpoints

- Ninguno.

## Pantalla

- Catálogo de componentes interno (no enrutado en producción) y los cuatro layouts.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Playwright con axe; capturas; Vitest con cobertura sobre `shared/ui/`.
- **Archivos principales:** `web/src/core/styles/tokens.css`, `web/src/core/theme/`, `web/tests/e2e/kit.spec.ts`, `web/.stylelintrc`, `.github/workflows/ci.yml`.

## Supuestos

- Ninguno.

## Dependencias

- US-061 · Panel layout, TopBar y SideNav.
- US-062 · Layouts portal, gym y TV.
- US-063 · Tabla, paginación, filtros y chips.
- US-064 · Encabezado, pestañas y KPI.
- US-065 · Panel lateral y modal de confirmación.
- US-066 · Valor enmascarado e historial.

## INVEST

- **Independiente:** cierra el kit sin depender de pantallas de negocio.
- **Negociable:** herramienta de chequeo de literales y comparación de capturas.
- **Valiosa:** previene regresiones visuales y de accesibilidad en todo el producto.
- **Estimable:** configuración de CI y catálogo.
- **Pequeña:** 4 a 5 días.
- **Testeable:** cada criterio es un job automático.

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
