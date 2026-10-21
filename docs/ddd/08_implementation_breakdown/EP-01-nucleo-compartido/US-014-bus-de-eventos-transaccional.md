# US-014 · Bus de eventos en memoria dentro de la transacción — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-014-bus-de-eventos-transaccional.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/events.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El mecanismo está completamente especificado: dataclasses congeladas, handlers con la misma sesión, propagación del error y profundidad máxima. El supuesto de pasar la sesión de forma explícita se acepta, porque mypy verifica así la firma de los handlers. DECISIONES N-37 confirma que nada se ejecuta "después del commit".

## Resumen

Se crea `core/events.py` con lo siguiente:
- `DomainEvent`: base congelada, con `occurred_at` tomado de `current_clock()`;
- `subscribe(event_type, handler)`, idempotente;
- `emit(event, session)`, que ejecuta los handlers en orden de registro y en la misma sesión, propaga cualquier excepción y corta las cadenas que superan cinco niveles;
- `clear_subscribers()`, solo para pruebas.

Hay pruebas puras y pruebas con PostgreSQL que demuestran que un handler que falla revierte también el cambio del emisor.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. N-37 refuerza el diseño: ningún efecto se crea después del commit, y lo que deba ocurrir sí o sí se persiste en tabla dentro de la misma transacción.

## Validación contra el dominio

- Transporta los eventos del catálogo de `02_domain_model.md` sección 3 (`PaymentRegistered`, `PaymentVoided`, `MembershipSold`, etc.). No define ninguno.
- Invariante transversal: los handlers corren en la misma transacción. Si un handler falla, se revierte todo (sección 3), y así S5 y RN-03 quedan atómicos.
- Sin funciones puras de negocio.

## Validación contra la arquitectura

- Regla de módulos 3 de `CLAUDE.md`: cuando una acción interesa a varios módulos, el origen emite un evento.
- `core/events.py` solo importa `core/clock.py` y el tipo `AsyncSession`. No importa ningún módulo, y la prueba de dirección de imports de US-015 lo vigila.
- Ubicación de los eventos: cada evento se declara como dataclass en el `service.py` del módulo emisor, que es su contrato público. El suscriptor lo importa desde ese `service.py`, lo cual está permitido, y se suscribe al importarse su propio `service.py`.
- Cuando dos services se usan mutuamente (memberships ↔ payments), se importan como módulo (`from app.modules.payments import service as payments_service`) y se accede a sus atributos en tiempo de llamada. Nunca `from ... import Nombre` en el nivel superior. Así se evitan los ciclos de import.
- Carga de suscriptores: `main.load_module_services()` importa el `service.py` de cada módulo registrado. Lo llaman `create_app()`, el worker y el CLI, para que los handlers estén suscritos en los tres procesos.
- Bus de criptografía, rol, paginación y auditoría: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `@dataclass(frozen=True, slots=True, kw_only=True) class DomainEvent` con `occurred_at: datetime = field(default_factory=lambda: current_clock().now_utc())`. Las subclases usan `@dataclass(frozen=True, slots=True)`. Con `kw_only` en la base, las subclases pueden declarar campos sin valor por defecto — 1 h
- [ ] T2 · Registro:
  - `E = TypeVar("E", bound=DomainEvent)` y `Handler = Callable[[E, AsyncSession], Awaitable[None]]`;
  - `subscribe(event_type: type[E], handler: Handler[E]) -> None`, idempotente: el mismo handler no se registra dos veces si el módulo se reimporta;
  - despacho por tipo exacto, sin herencia, para que el orden sea predecible.
  
  — 1,5 h
- [ ] T3 · `async def emit(event: DomainEvent, session: AsyncSession) -> None`:
  - ejecuta `await handler(event, session)` en orden de registro;
  - no atrapa excepciones (se propagan al emisor);
  - controla la profundidad con un `ContextVar[int]` y la constante `MAX_EVENT_DEPTH = 5`; al superarla lanza `EventDepthExceeded(RuntimeError)`, que el handler genérico de US-017 traduce a 500 `internal_error`;
  - sin suscriptores, no hace nada (criterio 4).
  
  — 1,5 h
- [ ] T4 · `clear_subscribers() -> None` y `subscribers_for(event_type) -> tuple[Handler, ...]`, solo para pruebas y diagnóstico — 0,5 h
- [ ] T5 · Docstrings del módulo:
  - el bus no persiste nada; todo efecto obligatorio va a una tabla en la misma transacción (criterio 6, N-37);
  - convención de dónde se declaran los eventos y cómo importar entre services;
  - `load_module_services()` en `main.py`, que US-020 cablea.
  
  — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T6 · `tests/core/test_events.py` (sin base, con una sesión simulada):
  - dos suscriptores reciben la misma instancia de sesión, en orden (criterio 1);
  - asignar un atributo lanza `FrozenInstanceError` (criterio 3);
  - emitir sin suscriptores no falla (criterio 4);
  - un handler que reemite el mismo evento corta en profundidad 5 con `EventDepthExceeded` (criterio 5);
  - `subscribe` es idempotente;
  - `occurred_at` sale de un `FrozenClock` fijado con `set_clock`.
  
  — 2 h

### Tests de service con PostgreSQL
- [ ] T7 · `tests/core/test_events_db.py`, con una tabla de prueba:
  - el emisor inserta, un handler actualiza otra fila y, tras el commit, ambas existen (BDD 1);
  - un primer handler actualiza, el segundo lanza una excepción, y ni la fila del emisor ni el cambio del primer handler quedan en la base (criterio 2, BDD 2).
  
  — 2,5 h

### Tests de router
- [ ] T8 · `tests/core/test_events_router.py`: en una app mínima con `get_session` (US-012), un endpoint que emite un evento cuyo handler falla responde con error y la fila no existe (BDD 2, petición completa) — 1 h

### Tests de arquitectura
- No aplica en esta historia. Debe seguir verde `api/tests/architecture/test_core_import_direction.py` (US-015): `core/events.py` no importa `app.modules`.

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión:
  - ningún `except` que se trague errores de un handler;
  - si se loguea un evento, se loguea solo el nombre del tipo, nunca su contenido (puede llevar datos del socio);
  - la profundidad máxima evita un bucle de eventos que deje la petición colgada.
  
  — 0,5 h

## Orden de ejecución
1. T6 (en rojo)
2. T1
3. T2
4. T3
5. T4
6. T7
7. T8
8. T5
9. T9

## Dependencias técnicas
- US-012 · Base de datos y Alembic multiesquema: sesión, transacción por petición y fixture con rollback.
- US-013 · Reloj de Bogotá: `current_clock()` para `occurred_at`.
- US-017 · Envelope de errores: la excepción que se propaga llega al cliente como envelope.
- US-020 · create_app: llama a `load_module_services()` para registrar los handlers.

## Endpoints
- Ninguno.

## Riesgos
- Ciclos de import entre services que se usan mutuamente (memberships ↔ payments, por `sell` y la validación del pago) — mitigación: importar el módulo y no el nombre; accederlo en tiempo de llamada. Queda documentado en T5 y lo deben seguir EP-09 y EP-10.
- Handlers no registrados en el worker o el CLI porque nadie importó su `service.py`: los eventos se emitirían sin efecto — mitigación: `load_module_services()` es obligatorio en los tres arranques, con una prueba en US-020.
- Un bus en memoria que no sobrevive a un reinicio — mitigación: es una restricción aceptada (`04_architecture_decision.md` sección 8). Los efectos obligatorios van a una tabla (N-37).
- Handlers lentos alargan la transacción y el lock de auditoría (US-015) — mitigación: los handlers solo escriben en la base; nada de HTTP externo dentro de un handler. Se revisa en el code review de cada épica.

## Estimación
- Backend: 5 h
- Front: 0 h
- Pruebas: 5,5 h
- DevOps / seguridad: 0,5 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_events.py tests/core/test_events_db.py tests/core/test_events_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Con el handler que falla de T7, `SELECT count(*) FROM <tabla de prueba>` devuelve 0 tras la petición
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.events --cov-fail-under=80`
