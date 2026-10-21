# US-014 · Como equipo quiero un bus de eventos en memoria que ejecute los handlers en la misma transacción del emisor para que vender, cobrar y activar sean atómicos sin acoplar los módulos

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/events.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `core/events.py` con `subscribe(EventType, handler)` y `emit(event)` donde los eventos son dataclasses congeladas y los handlers reciben la misma sesión
para que, por ejemplo, `PaymentRegistered` active la membresía en la misma transacción y un fallo del handler revierta también el pago

## Contexto de dominio

- **Aggregate / entidades:** ninguno propio; transporta eventos de todos.
- **Reglas que aplica:** regla de módulos 3 de `CLAUDE.md` (cuando una acción interesa a varios módulos, el origen emite un evento); `02_domain_model.md` sección 3 (handlers en la misma transacción; si un handler falla, todo se revierte); `04_architecture_decision.md` sección 5 y 8 (el bus no sobrevive a reinicios).
- **Eventos que emite:** ninguno (es el mecanismo)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** clase base `DomainEvent` (`@dataclass(frozen=True, slots=True)` con `occurred_at` UTC del `Clock`); registro `subscribe(event_type, handler)` donde `handler` es `async def (event, session) -> None`; `emit(event, session)` ejecuta los handlers en orden de registro, en la misma sesión, de forma síncrona respecto de la transacción (await secuencial); los handlers se registran al importar el `service.py` de cada módulo; `clear_subscribers()` solo para pruebas; protección contra recursión infinita (profundidad máxima configurable, por defecto 5).
- **Front:** No aplica.

## Criterios de aceptación

1. Un evento emitido con dos suscriptores ejecuta ambos handlers con la misma instancia de sesión que el emisor.
2. Si un handler lanza una excepción, la excepción se propaga al emisor y la transacción completa se revierte: ni el cambio del emisor ni los de handlers anteriores quedan en la base (prueba con PostgreSQL real).
3. Los eventos son inmutables: asignar un atributo después de crearlo lanza `FrozenInstanceError`.
4. Un evento sin suscriptores se emite sin error.
5. Una cadena de eventos que supera la profundidad máxima lanza un error explícito.
6. El bus no persiste nada; está documentado en el docstring que todo efecto obligatorio debe guardarse en tabla.

## Escenarios BDD

```gherkin
# language: es
Característica: Eventos dentro de la transacción

  Escenario: Handler activa en la misma transacción
    Dado un handler suscrito a "PaymentRegistered" que actualiza una fila
    Cuando el emisor inserta un pago y emite "PaymentRegistered"
    Y la transacción se confirma
    Entonces el pago y la actualización del handler existen en la base

  Escenario: Fallo del handler revierte todo
    Dado un handler suscrito que lanza una excepción
    Cuando el emisor inserta una fila y emite el evento
    Entonces la petición termina en error
    Y la fila del emisor no existe en la base

  Escenario: Evento inmutable
    Dado un evento "MembershipSold" creado
    Cuando intento cambiar su "membership_id"
    Entonces se lanza un error de instancia congelada
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna (la lógica es de orquestación).
- **Pruebas:** `tests/core/test_events.py` con base real (rollback por fallo de handler) y prueba de inmutabilidad.
- **Archivos principales:** `api/src/app/core/events.py`.

## Supuestos

- Supuesto: `emit` recibe la sesión de forma explícita (no por variable de contexto) para que mypy verifique la firma de los handlers; si se prefiere `contextvars`, se negocia sin cambiar el comportamiento.

## Dependencias

- US-012 · Base de datos y Alembic multiesquema (sesión y transacción).

## INVEST

- **Independiente:** no depende de módulos de negocio.
- **Negociable:** firma exacta de los handlers.
- **Valiosa:** habilita S5 (vender con primer pago) y RN-03 sin sagas.
- **Estimable:** acotada.
- **Pequeña:** dos días.
- **Testeable:** rollback verificable en base real.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas con PostgreSQL real en verde
- [ ] Revisión de PR aprobada
