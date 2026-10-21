# US-022 · Como equipo quiero una prueba de arquitectura que falle si un módulo importa los `models` de otro para que las fronteras entre bounded contexts no se rompan con el tiempo

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (pruebas de arquitectura)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `tests/architecture/test_no_cross_models.py` que recorra `app/modules/*` y falle ante un `from app.modules.<otro>.models` o un router que importe `models`
para que un módulo solo hable con otro a través de su `service.py`, como exige el monolito modular

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** reglas de módulos 1 y 2 de `CLAUDE.md` (lógica solo en `service.py`; prohibido importar `models` de otro módulo); `03_context_map.md` sección 5; `05_service_design.md` sección 1 (`router` → `service` → `models`, nunca `router` → `models`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `find_forbidden_imports(module_path) -> list[Violation]`

## Alcance

- **Backend:** prueba que analiza con `ast` cada archivo `.py` de `src/app/modules/<x>/` y reporta: (a) imports de `app.modules.<y>.models` con `y != x`; (b) imports de `models` (propio o ajeno) desde un `router.py`; (c) imports de `app.modules.<y>.router` desde otro módulo. Los módulos de lectura sin models (`dashboard`, `portal`, `tv`) quedan cubiertos por la misma regla. La prueba lista todas las violaciones con archivo y línea.
- **Front:** No aplica.

## Criterios de aceptación

1. Con el código limpio, la prueba pasa.
2. Un archivo `modules/members/service.py` con `from app.modules.memberships.models import Membership` hace fallar la prueba y el mensaje nombra archivo y línea.
3. Un `modules/plans/router.py` que importa `app.modules.plans.models` hace fallar la prueba.
4. `from app.modules.memberships import service as memberships_service` dentro de `members/service.py` está permitido.
5. La prueba detecta imports dentro de funciones (no solo al inicio del archivo).
6. La prueba corre en el job `api` de CI.

## Escenarios BDD

```gherkin
# language: es
Característica: Fronteras entre módulos

  Escenario: Código respetando las fronteras
    Dado módulos que solo se llaman por "service.py"
    Cuando corre la prueba de arquitectura
    Entonces la prueba pasa

  Escenario: Import de models ajeno
    Dado "members/service.py" importa "memberships.models"
    Cuando corre la prueba de arquitectura
    Entonces la prueba falla
    Y el mensaje indica el archivo y la línea

  Escenario: Router que salta el service
    Dado "plans/router.py" importa "plans.models"
    Cuando corre la prueba de arquitectura
    Entonces la prueba falla
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `find_forbidden_imports` con fixtures de código de ejemplo (import absoluto, relativo `from ..memberships.models`, import dentro de función).
- **Pruebas:** arquitectura.
- **Archivos principales:** `api/tests/architecture/test_no_cross_models.py`.

## Supuestos

- Supuesto: los `schemas.py` de otro módulo sí se pueden importar para tipar respuestas de su service (son contrato público); si el gate lo prohíbe, se agrega a la regla.

## Dependencias

- US-020 · create_app, migraciones y health (estructura de módulos registrada).

## INVEST

- **Independiente:** no requiere módulos de negocio para escribirse (usa fixtures).
- **Negociable:** si `schemas` ajenos se permiten.
- **Valiosa:** protege el diseño modular a largo plazo.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** fixtures con violaciones.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Prueba en CI en verde
- [ ] Revisión de PR aprobada
