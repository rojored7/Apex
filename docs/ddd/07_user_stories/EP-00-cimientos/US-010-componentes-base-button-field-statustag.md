# US-010 · Como equipo quiero los componentes base `Button`, `Field` y `StatusTag` accesibles y probados para que los primeros formularios y listas se construyan sobre piezas comunes y no con HTML suelto

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (base de `P_Formulario` y `P_Lista`)

## Historia

Como equipo
quiero `Button`, `Field` y `StatusTag` en `web/src/shared/ui/` con estados de foco, hover, activo y deshabilitado, controles de 44 px y pruebas de componente
para que cada pantalla use las mismas piezas accesibles y el estado de una membresía nunca se comunique solo con color

## Contexto de dominio

- **Aggregate / entidades:** ninguno (`StatusTag` muestra estados de membresía: al día, por vencer, vencido, congelado, cancelado, pendiente de pago, sin plan).
- **Reglas que aplica:** `01_product_discovery.md` sección 6 (controles de 44 px, foco visible, contraste 4,5:1, el color nunca es el único portador de significado); Q3 de `DECISIONES.md` (estado "Pendiente de pago" con `--warning`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:**
  - `Button`: variantes `primary`, `secondary`, `danger`, `ghost`; tamaños `md` (44 px) y `lg` (56 px, tablet); `loading` (deshabilita y anuncia con `aria-busy`); `type="button"` por defecto.
  - `Field`: etiqueta asociada (`htmlFor`), texto de ayuda, mensaje de error con `aria-describedby` y `aria-invalid`, marca de obligatorio, compatible con React Hook Form (`forwardRef`); soporta enlace en el error (para el `existing_id` de socio duplicado de US-069).
  - `StatusTag`: recibe `status` (`active`, `expiring`, `expired`, `frozen`, `cancelled`, `pending_payment`, `none`) y siempre muestra texto en español ("Al día", "Por vencer", "Vencido", "Congelado", "Cancelado", "Pendiente de pago", "Sin plan") más color de token; `pending_payment` usa borde y texto `--warning`.
  - Todos usan solo variables de `tokens.css`.

## Criterios de aceptación

1. Los tres componentes existen en `web/src/shared/ui/` con prueba de componente (Vitest + Testing Library) y cobertura de 80 % o más.
2. `Button` y los controles de `Field` miden al menos 44 px de alto en tamaño `md` y 56 px en `lg`.
3. El foco por teclado es visible en los tres (prueba con `userEvent.tab()` y estilo `:focus-visible` con token).
4. `Field` con error expone `aria-invalid="true"` y el mensaje está enlazado por `aria-describedby`.
5. `StatusTag` muestra siempre una etiqueta de texto; una prueba renderiza cada uno de los siete estados y verifica su texto.
6. `Button` con `loading` no dispara `onClick` y tiene `aria-busy="true"`.
7. Ningún componente contiene colores ni fuentes literales (el lint de US-009 pasa).
8. Un chequeo automático de accesibilidad (`axe` vía `vitest-axe` o `jest-axe`) no reporta violaciones en los tres componentes.

## Escenarios BDD

```gherkin
# language: es
Característica: Componentes base accesibles

  Escenario: Estado de membresía con texto
    Dado un StatusTag con estado "pending_payment"
    Cuando se renderiza
    Entonces muestra el texto "Pendiente de pago"
    Y usa el color de token "--warning"

  Escenario: Campo con error de validación
    Dado un Field "Documento" con el error "Ya existe un socio con este documento"
    Cuando se renderiza
    Entonces el input tiene "aria-invalid" igual a "true"
    Y el lector de pantalla anuncia el mensaje de error

  Escenario: Botón cargando no se puede pulsar dos veces
    Dado un Button primario con loading activo
    Cuando el usuario hace clic
    Entonces no se ejecuta la acción
    Y el botón indica "aria-busy"
```

## Endpoints

- Ninguno.

## Pantalla

- Base de los patrones `P_Formulario` y `P_Lista` de `docs/design/screens/`; las variantes visuales se toman de `DESIGN.md`. `// DESIGN-GAP:` para el estado "Pendiente de pago" si el diseño no lo tiene aún (Q3).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** mapeo `status → etiqueta` como función exportada (`statusLabel`).
- **Pruebas:** Vitest + Testing Library + axe por componente.
- **Archivos principales:** `web/src/shared/ui/Button.tsx`, `Field.tsx`, `StatusTag.tsx` y sus `*.test.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-009 · Esqueleto del front (tokens, lint, Vitest).

## INVEST

- **Independiente:** solo necesita el esqueleto del front.
- **Negociable:** variantes adicionales.
- **Valiosa:** lo usan todos los formularios y listas de v0.1.
- **Estimable:** tres componentes acotados.
- **Pequeña:** dos o tres días.
- **Testeable:** pruebas de componente y axe.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] Pruebas de componente y axe en verde, cobertura de 80 % o más
- [ ] Sin colores literales
- [ ] Revisión de PR aprobada
