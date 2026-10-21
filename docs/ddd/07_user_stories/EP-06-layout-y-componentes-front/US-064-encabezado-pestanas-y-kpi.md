# US-064 · Como equipo quiero el encabezado de página, las pestañas y la tarjeta KPI compartidos para que fichas y tablero se armen con piezas iguales

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Patrón `P_Ficha` (referencia; lo usan `Socio_Ficha`, `Config`, `Inicio`)

## Historia

Como equipo
quiero `PageHeader`, `Tabs` y `KpiCard`
para que la ficha del socio, la configuración y el tablero compartan jerarquía visual y estados, incluido el KPI que aún no existe en la versión

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** contrato estable del tablero con campos futuros en `null` (EP-12); pestañas en la URL (reglas web).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:** `PageHeader` (título, subtítulo, migas, zona de acciones con hasta tres botones y menú de más acciones); `Tabs` (patrón WAI-ARIA tabs, pestaña activa en la URL como segmento o `?tab=`, pestañas deshabilitadas con texto "Disponible en v0.x"); `KpiCard` (etiqueta, valor, variación opcional, enlace; estados carga, valor, `null` y error).

## Criterios de aceptación

1. `Tabs` implementa `role="tablist"`, `role="tab"` y `role="tabpanel"` con flechas izquierda y derecha para moverse; la pestaña activa se refleja en la URL y sobrevive a recargar.
2. Una pestaña marcada como no disponible se ve deshabilitada, no es seleccionable y anuncia su versión con texto.
3. `KpiCard` con valor `null` muestra un estado vacío con el texto "Disponible en v0.x" (versión por prop), sin cero engañoso.
4. `KpiCard` con valor numérico de dinero usa `formatCop` (US-060); con conteo usa separador de miles.
5. `KpiCard` con enlace es un único destino enfocable con texto accesible que incluye etiqueta y valor.
6. `PageHeader` usa un único `h1` por página y coloca las acciones en orden de tabulación después del título.
7. Los tres componentes usan solo tokens y tienen prueba de componente.

## Escenarios BDD

```gherkin
# language: es
Característica: Encabezado, pestañas y KPI

  Escenario: Cambiar de pestaña con teclado
    Dado una ficha con pestañas Membresías, Pagos e Historial
    Cuando el usuario enfoca Membresías y pulsa flecha derecha
    Entonces se activa la pestaña Pagos
    Y la URL refleja la pestaña Pagos

  Escenario: KPI de una versión futura
    Dado un KpiCard "Por avisar" con valor null y versión "v0.2"
    Cuando se renderiza
    Entonces muestra "Disponible en v0.2"
    Y no muestra el número 0

  Escenario: Pestaña no disponible
    Dado una pestaña Asistencia marcada como no disponible
    Cuando el usuario intenta seleccionarla
    Entonces la pestaña activa no cambia
```

## Endpoints

- Ninguno.

## Pantalla

- `P_Ficha` como referencia; consumidores en `Socio_Ficha` (US-073), `Config` (US-055) e `Inicio` (US-109).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Testing Library (roles ARIA, teclado, URL), `axe`, capturas en claro y oscuro.
- **Archivos principales:** `web/src/shared/ui/PageHeader.tsx`, `Tabs.tsx`, `KpiCard.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-010 · Componentes base Button, Field, StatusTag.

## INVEST

- **Independiente:** sin API ni pantallas de negocio.
- **Negociable:** forma de reflejar la pestaña en la URL (segmento o parámetro).
- **Valiosa:** base de ficha, configuración y tablero.
- **Estimable:** tres componentes conocidos.
- **Pequeña:** 2 a 3 días.
- **Testeable:** comportamiento ARIA y estados verificables.

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
