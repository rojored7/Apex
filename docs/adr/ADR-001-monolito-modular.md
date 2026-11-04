# ADR-001 · Monolito modular

## Estado

Aceptado. Vigente desde el Sprint 0 (v0.1). Cambiarlo exige detenerse y preguntar: es una decisión estructural que toca cada módulo.

## Contexto

APEX administra un solo gimnasio de CrossFit en Colombia: unas decenas o pocos cientos de socios, un equipo de una a tres personas con acceso de administración y un servidor. El sistema guarda datos personales y pagos (Ley 1581), así que la trazabilidad y la auditoría pesan más que la escala. No hay equipo de plataforma que opere varios servicios, ni tráfico que lo justifique.

## Decisión

Un solo proceso del api (FastAPI) más un worker (APScheduler) sobre un único servidor PostgreSQL 16 con un esquema por módulo. Cada módulo de `api/src/app/modules/` tiene `router.py`, `schemas.py`, `service.py` y, si tiene tablas, `models.py`.

- Un módulo solo llama a otro por su `service.py`; puede importar `schemas.py` y `exceptions.py`, nunca `models.py` ni `router.py`. Sin joins entre esquemas.
- Cuando una acción interesa a varios módulos, el origen emite un evento por el bus en memoria de `core/events.py`; los demás se suscriben. No se encadenan services de tres módulos en un endpoint.
- Las dependencias mutuas entre dos services se resuelven con un puerto que registra el módulo dueño o, solo en lecturas de presentación y para los pares de una lista blanca, con un import perezoso.
- `core/` es compartido y ningún módulo lo modifica desde su dominio. La criptografía vive en `core/crypto/` y es la única puerta (ver ADR-002).
- Interfaces solo donde hay algo que intercambiar (`KeyProvider`, canales de notificación, almacenamiento): sin repositorios abstractos por tabla ni entidades de dominio aparte de los modelos.

## Alternativas descartadas

- **Microservicios por contexto:** costo operativo (despliegue, red, observabilidad, transacciones distribuidas) sin escala que lo pague; la auditoría encadenada y los pagos necesitan una sola transacción.
- **Monolito sin fronteras (todo importa todo):** más rápido el primer mes, pero deja a v0.2 a v1.0 (clases, WODs, portal) sin forma de crecer sin enredarse; por eso las fronteras se vigilan con pruebas.
- **Una base por módulo:** impide la integridad referencial y la verificación de la cadena de auditoría; el esquema por módulo da el aislamiento sin esos costos.

## Consecuencias

- Un solo despliegue y una sola base que respaldar y restaurar; el rollback de código es simple, el de datos no (ver `docs/operacion/actualizar.md`).
- Los módulos pueden extraerse luego a servicios porque ya hablan por `service.py`, eventos y puertos, pero ese paso sería otra decisión.
- Las fronteras cuestan disciplina: se rompen con un import, y por eso las vigilan pruebas de arquitectura que corren en cada gate.
- Un fallo en el proceso del api afecta a todos los módulos; se mitiga con `/health`, reinicio automático y el worker aparte.

## Cómo se verifica

- `api/tests/architecture/test_service_import_graph.py` fija los pares permitidos entre services y `api/tests/architecture/test_no_cross_models.py` prohíbe importar `models.py` ajenos.
- `api/tests/architecture/test_no_cross_schema_sql.py` impide SQL entre esquemas de otros módulos.
- `api/tests/architecture/test_core_import_direction.py` impide que `core/` importe módulos de negocio.
- Cambiar esta decisión (partir un módulo en servicio, abrir una segunda base) exige detenerse y preguntar antes de tocar código.
