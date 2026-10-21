# EP-01 · Núcleo compartido de la plataforma

- **Versión del plan:** v0.1 (Tarea 1, salvo `security.py`, que va en EP-03; Tarea 12 punto 2, exportación de OpenAPI).
- **Bounded context:** `core/` (transversal). Incluye el hook de escritura del contexto Audit.
- **Estimación relativa:** M.

## Objetivo de negocio

Dar a todos los módulos las mismas reglas de juego: una base de datos con columnas comunes, un bus de eventos que mantiene la consistencia entre contextos dentro de una sola transacción, un registro de auditoría que nadie puede saltarse y errores que el front entiende siempre igual. Esto es lo que permite que "vender y cobrar" sea atómico (S5) y que cada cambio quede rastreable (RN-16).

## Actores

- Todos los módulos de negocio, como consumidores del núcleo.
- Worker, que usa `Clock` y el bus de eventos en sus jobs.

## Capacidades incluidas

- `config.py`: `Settings` con pydantic-settings, todo desde `.env`; el arranque falla si falta una variable obligatoria.
- `db.py`: engine async, `async_session`, `Base` y `CommonColumnsMixin` (`id` UUID, `created_at`, `updated_at`, `created_by`, `deleted_at` opcional), según la regla de datos 3 y RN-14.
- Un esquema de PostgreSQL por contexto; Alembic con un `env.py` que incluye todos los esquemas; `create_all` prohibido fuera de pruebas.
- `clock.py`: puerto `Clock` con `SystemClock` y `FrozenClock` para pruebas.
- `events.py`: bus en memoria (`subscribe`, `emit`), eventos como dataclasses congeladas; los handlers corren en la misma sesión y transacción, y un fallo revierte todo (`02_domain_model.md` sección 3).
- `audit.py`: `record(...)`, `chain_hash(prev_hash, row)` como función pura y hook `after_flush` para tablas con `__audited__ = True`. Aggregate `AuditEntry` append-only, con trigger que rechaza `UPDATE` y `DELETE` (RN-16). La consulta y la verificación las expone EP-11.
- `errors.py`: envelope `{ "error": { "code", "message", "field"?, "existing_id"? } }` y handlers de excepciones.
- `logging.py`: logs JSON a stdout con un filtro que nunca imprime campos cifrados ni tokens.
- Contrato de listas: `limit` de 1 a 200 (25 por defecto) y `offset`; respuesta `{ items, total, limit, offset }` (regla de datos 6, supuesto S2).
- `main.py` con `create_app()`, registro de routers, `alembic upgrade head` al arrancar y `/health`.
- Exportación de `docs/openapi.json` en CI para que el front genere sus tipos (Tarea 12).
- Prueba de arquitectura `test_no_cross_models.py`: ningún módulo importa `models` de otro (regla de módulos 2).

## Fuera de alcance

- Hash de contraseñas, JWT y roles (EP-03).
- Bus de criptografía y tipos `Encrypted` y `BlindIndexed` (EP-02).
- Router de auditoría, verificación desde la pantalla y filtros (EP-11).
- Firma nocturna de la cadena (EP-17).

## Criterios de éxito medibles

- Prueba de encadenamiento: tres filas auditadas producen tres hashes, cada uno dependiente del anterior; alterar una fila a mano rompe la verificación (criterio de salida de la Tarea 1).
- Prueba de que un handler de evento que lanza una excepción revierte también el cambio del emisor.
- Prueba de que un `UPDATE` o `DELETE` sobre `audit.audit_log` es rechazado por la base.
- La prueba de arquitectura falla si se agrega un `from app.modules.<otro>.models`.
- `/health` responde 200 con la base arriba y un código distinto de 200 con la base abajo.
- `docs/openapi.json` se regenera en CI y el job falla si el archivo versionado está desactualizado.

## Dependencias

- EP-00 Cimientos del repositorio.

## Riesgos

- El bus en memoria no sobrevive a un reinicio; todo efecto obligatorio (por ejemplo, avisos) debe persistirse en tabla (`04_architecture_decision.md` sección 8).
- El hook `after_flush` puede volverse lento con lotes grandes (importación de socios, recifrado); se mide en EP-13 y EP-02.
- La serialización canónica de filas para el hash es una decisión irreversible: cambiarla con datos existentes rompe la cadena. Se fija y se documenta en el ADR.

## Pantallas del diseño que habilita

- Ninguna directamente. Es requisito de todas.
