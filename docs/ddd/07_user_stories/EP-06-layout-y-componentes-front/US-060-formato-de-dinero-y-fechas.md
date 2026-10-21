# US-060 · Como equipo quiero funciones únicas de formato de dinero y fechas para que todo monto y toda hora se vean igual y en hora de Bogotá

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/core/i18n/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (la usan todas)

## Historia

Como equipo
quiero un módulo `format.ts` con funciones puras para dinero en COP, fechas y horas en zona `America/Bogota`
para que recepción vea `$ 120.000` y `20 oct 2026` en todas las pantallas mientras el dato sigue siendo entero y UTC

## Contexto de dominio

- **Aggregate / entidades:** value object `Money` (entero COP) y fechas de todos los aggregates.
- **Reglas que aplica:** RN-01 (dinero entero sin decimales); regla de datos 2 (UTC en API y base, conversión a Bogotá en el front); Q28 (las fechas civiles de membresía son fechas, no horas).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `formatCop(amount: number) -> string`, `parseCop(input: string) -> number | null`, `formatDate(isoDate: string) -> string`, `formatDateTime(isoUtc: string) -> string`, `formatTime(isoUtc: string) -> string`, `todayBogota() -> string (AAAA-MM-DD)`

## Alcance

- **Backend:** No aplica.
- **Front:** `web/src/core/i18n/format.ts` con `Intl.NumberFormat("es-CO")` e `Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota" })`; constante `TZ_DISPLAY` desde configuración de build.

## Criterios de aceptación

1. `formatCop(120000)` devuelve `$ 120.000`; `formatCop(0)` devuelve `$ 0`; nunca se muestran decimales.
2. `formatCop` lanza error de desarrollo (y devuelve `—` en producción) si recibe un número no entero, para detectar violaciones de RN-01.
3. `parseCop("$ 120.000")`, `parseCop("120000")` y `parseCop("120.000")` devuelven `120000`; `parseCop("120.000,50")` y `parseCop("-5")` devuelven `null` (el formulario muestra error).
4. `formatDate("2026-10-20")` devuelve `20 oct 2026` sin conversión de zona (fecha civil).
5. `formatDateTime("2026-10-21T02:30:00Z")` devuelve `20 oct 2026, 9:30 p. m.` (hora de Bogotá, UTC-5).
6. `todayBogota()` devuelve la fecha civil de Bogotá aunque el navegador esté en otra zona: a las 03:00 UTC del 21 de octubre devuelve `2026-10-20`.
7. Ningún componente formatea dinero o fechas por fuera de `format.ts` (regla de ESLint que prohíbe `toLocaleString` y `Intl.*` fuera de `core/i18n`).

## Escenarios BDD

```gherkin
# language: es
Característica: Formato de dinero y fechas

  Escenario: Monto entero en pesos
    Dado un monto de 120000
    Cuando se formatea para pantalla
    Entonces se muestra "$ 120.000"

  Escenario: Entrada de monto con decimales
    Dado que recepción escribe "120.000,50" en un campo de dinero
    Cuando el formulario interpreta el valor
    Entonces el valor es inválido
    Y el campo muestra "El monto debe ser un número entero en pesos"

  Escenario: Hora UTC mostrada en Bogotá
    Dado un instante "2026-10-21T02:30:00Z"
    Cuando se formatea con fecha y hora
    Entonces se muestra "20 oct 2026, 9:30 p. m."

  Escenario: Hoy en Bogotá con navegador en otra zona
    Dado un navegador configurado en UTC a las 03:00 del 21 de octubre de 2026
    Cuando se pide la fecha de hoy
    Entonces la respuesta es "2026-10-20"

  Escenario: Formato por fuera del módulo
    Dado un componente que usa toLocaleString para un monto
    Cuando corre el lint
    Entonces el lint falla
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** las seis listadas, con casos de borde: 1.000.000, 999, montos grandes (50.000.000), medianoche Bogotá, fin de mes, cambio de año.
- **Pruebas:** Vitest con `TZ=UTC` y `TZ=Asia/Tokyo` para garantizar independencia de la zona del equipo.
- **Archivos principales:** `web/src/core/i18n/format.ts`, `web/src/core/i18n/format.test.ts`, `.eslintrc`.

## Supuestos

- Supuesto: los separadores de hora "a. m." y "p. m." son los que produce `Intl` para `es-CO`; si el diseño pide formato de 24 horas se cambia solo en `format.ts`.

## Dependencias

- US-009 · Esqueleto del front.

## INVEST

- **Independiente:** solo necesita el proyecto del front.
- **Negociable:** el formato de hora (12 o 24 horas) es ajustable.
- **Valiosa:** consistencia y cumplimiento de RN-01 en pantalla.
- **Estimable:** un archivo de funciones puras.
- **Pequeña:** 1 a 2 días.
- **Testeable:** todo son funciones puras con casos concretos.

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
