# US-022 · Prueba de arquitectura sin `models` cruzados — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-022-prueba-arquitectura-sin-models-cruzados.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core, pruebas de arquitectura (`api/tests/architecture/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**NEEDS_REFINEMENT**

Las tres reglas que la prueba prohíbe son claras:
- `models` de otro módulo;
- `models` desde un `router.py`;
- el `router` de otro módulo.

Queda abierto el supuesto de la historia: si un módulo puede importar el `schemas.py` de otro. DECISIONES.md no lo resuelve, y la restricción dura dice "solo service a service o eventos". La respuesta cambia qué código acepta la prueba y, por lo tanto, cómo tipan las épicas de negocio lo que devuelven los services ajenos. La implementación puede avanzar con la alternativa por defecto, porque es una regla configurable de la prueba.

## Resumen

Esta historia entrega:
- un analizador `find_forbidden_imports` basado en `ast`, que resuelve también los imports relativos y los que están dentro de funciones;
- `test_no_cross_models.py`, que lo aplica a cada carpeta de `src/app/modules/*` y lista todas las violaciones con archivo y línea;
- fixtures de código de ejemplo para cada caso permitido y prohibido.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- No toca aggregates. Protege las fronteras de los bounded contexts de `03_context_map.md` sección 5: nada de `models` ajenos, y los cruces entre esquemas pasan por el `service.py` dueño.
- Función pura (en código de pruebas): `find_forbidden_imports(file: Path, *, module: str, source: str | None = None) -> list[Violation]`.

## Validación contra la arquitectura

- Reglas de módulos 1 y 2 de `CLAUDE.md`, y la regla de dependencias de `05_service_design.md` sección 1 (`router` → `service` → `models`).
- Los módulos de lectura sin `models` (`dashboard`, `portal`, `tv`) quedan cubiertos por la misma regla.
- El helper vive en `api/tests/architecture/_imports.py`, no en `src/`: es una herramienta de prueba.
- Es complementaria de otras pruebas:
  - `test_core_import_direction.py` (US-015): `core` no importa módulos;
  - `test_banned_imports.py` (US-002): primitivas criptográficas;
  - `test_every_route_has_role.py` (US-035): rol por ruta.
- Rol, paginación, bus de criptografía y auditoría: no aplican.

## Preguntas abiertas

- **Pregunta:** ¿puede un módulo importar `app.modules.<otro>.schemas` (y `exceptions`) para tipar lo que devuelve y capturar lo que lanza el `service.py` de ese otro módulo? ¿O todo tipo que cruza la frontera debe venir del propio `service.py` (reexportado ahí)?
- **Alternativa propuesta por defecto:** sí. `schemas.py` y `exceptions.py` son contrato público del service y se permiten. La prueba prohíbe solo `models` ajenos, `models` desde cualquier `router.py` y el `router` de otro módulo.
- Si el gate elige la opción estricta, se agrega la regla (d), "solo `service` de otro módulo", sin cambiar el resto (T2 la deja como una bandera `ALLOW_FOREIGN_SCHEMAS`).

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `api/tests/architecture/_imports.py`, con `find_forbidden_imports`, que:
  - recorre con `ast.walk` todo el árbol, de modo que detecta imports dentro de funciones y de bloques `if TYPE_CHECKING` (criterio 5);
  - resuelve `from ..memberships.models import X`, `from app.modules.memberships import models`, `import app.modules.memberships.models as m` y `from app.modules.memberships.models import X` a su nombre absoluto;
  - aplica tres reglas: (a) `app.modules.<y>.models` con `y` distinto del módulo propio; (b) cualquier `app.modules.<*>.models` importado desde un `router.py`; (c) `app.modules.<y>.router` con `y` distinto del módulo propio;
  - trata igual una llamada `importlib.import_module("...")` con una cadena literal.
  
  — 2,5 h
- [ ] T2 · `@dataclass(frozen=True) class Violation(file: str, line: int, imported: str, rule: Literal["foreign_models", "router_models", "foreign_router", "foreign_non_service"])`, con `__str__` legible (`members/service.py:12 importa app.modules.memberships.models (foreign_models)`), y la bandera `ALLOW_FOREIGN_SCHEMAS: Final = True` para la regla (d) de la pregunta abierta — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/architecture/test_find_forbidden_imports.py`, con fuentes de ejemplo pasadas como `source` y estos casos:
  - `members/service.py` con `from app.modules.memberships.models import Membership` da una violación `foreign_models` con su línea (criterio 2);
  - `plans/router.py` con `from app.modules.plans.models import Plan` da `router_models` (criterio 3);
  - `from app.modules.memberships import service as memberships_service` en `members/service.py` está permitido (criterio 4);
  - un import dentro de una función se detecta (criterio 5);
  - un import relativo `from ..memberships.models import X` se detecta;
  - `import app.modules.memberships.models as m` se detecta;
  - `from app.modules.memberships import models` se detecta;
  - un import de `app.modules.billing.router` desde otro módulo da `foreign_router`;
  - un import de `schemas` ajenos depende de la bandera.
  
  — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T4 · `api/tests/architecture/test_no_cross_models.py`: recorre cada `src/app/modules/<x>/**/*.py`, junta todas las violaciones y falla con la lista completa, una por línea. Con el código limpio pasa (criterio 1) — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T5 · Confirmar que el job `api` de CI (US-003) ejecuta `uv run pytest tests/architecture -q` como paso propio con nombre visible ("Fronteras entre módulos"), para que una violación se vea sin abrir el log (criterio 6) — 0,5 h

### Seguridad
- No aplica (no maneja datos ni entradas externas).

## Orden de ejecución
1. T3 (en rojo)
2. T2
3. T1
4. T4
5. T5

## Dependencias técnicas
- US-020 · create_app: estructura de módulos registrada (`MODULES`).
- US-003 · Pipeline CI: job `api`, donde corre la suite de arquitectura.
- US-015 · `test_core_import_direction.py`: complementa la regla para `core/`.

## Endpoints
- Ninguno.

## Riesgos
- Imports dinámicos (`importlib.import_module("app.modules.x.models")`) escapan al análisis estático — mitigación: T1 analiza también `importlib.import_module` con una cadena literal; los nombres armados en tiempo de ejecución quedan para la revisión de PR.
- Si el gate prohíbe `schemas` ajenos después de que EP-07 a EP-10 los usen, habría que mover tipos a los `service.py` — mitigación: decidirlo antes de US-069 y US-084; la bandera (T2) permite activar la regla sin reescribir la prueba.
- Los paquetes internos de un módulo (`notifications/channels/`, `attachments/storage/`) importados desde otro módulo no están cubiertos — mitigación: se anota como regla futura en EP-14 y EP-19, que son las que crean esos paquetes.

## Estimación
- Backend: 3 h
- Front: 0 h
- Pruebas: 2,5 h
- DevOps / seguridad: 0,5 h
- **Total: 6 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/architecture/test_find_forbidden_imports.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Agregar a mano `from app.modules.memberships.models import Membership` en `members/service.py` hace fallar `test_no_cross_models.py` con el archivo y la línea; quitarlo lo deja en verde
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest tests/architecture --cov=tests.architecture --cov-fail-under=80`
