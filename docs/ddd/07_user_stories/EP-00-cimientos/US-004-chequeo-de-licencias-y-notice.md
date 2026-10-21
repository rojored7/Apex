# US-004 · Como equipo quiero que CI rechace cualquier dependencia con licencia prohibida y mantenga un `NOTICE` para que el gimnasio nunca quede atado a obligaciones GPL, LGPL, AGPL, BSL o SSPL

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (CI, `api/`, `web/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero un chequeo de licencias del backend (`pip-licenses`) y del front (`license-checker` o equivalente) en CI, con la lista permitida y un archivo `NOTICE`
para que una dependencia con licencia prohibida no entre nunca, ni siquiera de forma transitiva

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** sección "Licencias" de `CLAUDE.md` (permitidas MIT, BSD, Apache 2.0, PostgreSQL; MPL-2.0 solo sin modificar; prohibidas GPL, LGPL, AGPL, BSL, SSPL); `01_product_discovery.md` sección 6 (se agregan ISC y OFL 1.1 por Lucide y fuentes); `BRECHAS.md` sección 7.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** paso en el job `api` con `uv run pip-licenses --from=mixed --fail-on="GPL;LGPL;AGPL;BSL;SSPL"` (con variantes de nombre: "GNU General Public License", "GNU Lesser...", "Business Source License", "Server Side Public License") y `--allow-only` con la lista permitida; lista de excepciones explícitas y comentadas para MPL-2.0 sin modificar (OpenBao, pywebpush cuando lleguen).
- **Front:** paso en el job `web` con `license-checker --onlyAllow "MIT;BSD-2-Clause;BSD-3-Clause;Apache-2.0;ISC;OFL-1.1;0BSD"` sobre dependencias de producción.
- **Documentación:** `NOTICE` en la raíz con las dependencias directas y su licencia, y la regla en `CONTRIBUTING.md` de actualizarlo al agregar una dependencia.

## Criterios de aceptación

1. El job `api` falla si cualquier paquete instalado (directo o transitivo) tiene una licencia de la lista prohibida.
2. El job `web` falla si cualquier dependencia de producción tiene una licencia fuera de la lista permitida.
3. ISC y OFL 1.1 son aceptadas en el front; MPL-2.0 solo se acepta para paquetes listados como excepción.
4. Un PR de control que agrega `python-telegram-bot` (LGPL) o `fpdf2` (LGPL) al backend queda en rojo.
5. Existe `NOTICE` en la raíz con nombre, versión y licencia de cada dependencia directa de `api` y `web`.
6. Un paquete sin licencia declarada hace fallar el chequeo (no se asume permitida).

## Escenarios BDD

```gherkin
# language: es
Característica: Solo licencias permisivas

  Escenario: Dependencias permitidas en verde
    Dado que todas las dependencias tienen licencias MIT, BSD, Apache 2.0, ISC u OFL 1.1
    Cuando corre CI
    Entonces los pasos de licencias de "api" y "web" terminan en verde

  Escenario: Dependencia LGPL rechazada
    Dado un PR que agrega "fpdf2" a las dependencias del api
    Cuando corre el paso "pip-licenses"
    Entonces el paso falla
    Y el mensaje nombra el paquete y su licencia LGPL

  Escenario: Paquete sin licencia declarada
    Dado un paquete del front sin campo de licencia
    Cuando corre "license-checker"
    Entonces el paso falla por licencia desconocida
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** PR de control con `fpdf2` en rojo.
- **Archivos principales:** `.github/workflows/ci.yml`, `NOTICE`, `CONTRIBUTING.md`, `api/pyproject.toml` (`pip-licenses` en dev).

## Supuestos

- Supuesto: se acepta `0BSD` en el front como variante BSD (aparece en dependencias transitivas comunes de Vite); si el gate lo rechaza se quita de la lista.

## Dependencias

- US-003 · Pipeline CI (donde vive el paso).
- US-009 · Esqueleto del front (necesario para el paso del front; el del backend no lo espera).

## INVEST

- **Independiente:** el paso del backend se entrega sin el front.
- **Negociable:** herramienta exacta del front.
- **Valiosa:** evita un riesgo legal permanente.
- **Estimable:** herramientas conocidas.
- **Pequeña:** dos días.
- **Testeable:** PR de control en rojo.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] Pasos de licencias en CI en verde
- [ ] PR de control rechazado verificado
- [ ] `NOTICE` versionado
- [ ] Revisión de PR aprobada
