# US-073 · Ver ficha del socio — desglose técnico

> **Corregido en S3-W0-1** (`docs/ddd/blueprints/sprint-03-plan.md`, sección 1; registro en `docs/ddd/DECISIONES.md`, "Sprint 3"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - `bus.op_context(...)` no existe: la puerta es `core.crypto.types.reveal(obj, field, purpose)`; la ficha descifra con propósito `mask` sin `bus.batch` (una fila `decrypt` por campo no vacío con el `record_id` del socio; D20, S3-C3).
> - "Notas" no existe desde M-5 del Sprint 2 (S3-C18).
> - `test_service_import_cycles.py` → `test_service_import_graph.py` (S3-C9).
> - Firma real: `get(session, member_id)`; el actor sale de `get_actor()` y la sesión es `SessionDep` (S3-C5).

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-073-ver-ficha-del-socio.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

N-01 decide que la ficha descifra en memoria para enmascarar y que esa lectura queda en `crypto_ops` con verbo `decrypt` y propósito `mask`. La brecha que este desglose detectó al principio (no había dónde guardar el propósito) quedó cerrada en la consolidación: `0003_crypto` (US-024) ya trae `crypto_ops.purpose` y el bus de US-029 recibe `purpose` como argumento con nombre (`decrypt(blob, aad, *, purpose=None)`). El resto de la historia está resuelto por N-01 y N-20. (Ajuste del orquestador en la consolidación.)

## Resumen

- `GET /api/v1/members/{id}` para admin y coach devuelve `MemberDetail` con nombres, sexo, estado, notas, `data_consent_at`, `deleted_at`, `membership_status` y los cinco campos sensibles enmascarados.
- El servidor descifra los cinco campos dentro de un contexto de operación con propósito `mask`, calcula el enmascarado con la función pura `mask` (US-069) y nunca devuelve el valor completo. No escribe auditoría `reveal`.
- Un socio dado de baja se devuelve igual (no 404) para admin y coach y la ficha se pinta en solo lectura.
- Front: `MemberDetailPage` con encabezado, acciones por rol, `MaskedValue` por campo, aviso de autorización faltante (Q16) y pestañas.

## Correcciones aplicadas por DECISIONES.md

- La historia calcula el enmascarado "sin descifrar", con columnas `<campo>_hint` en claro, y el criterio 3 exige que abrir la ficha no genere ningún `decrypt` en `crypto_ops` → no hay `*_hint`; la ficha descifra en memoria, enmascara y deja en `crypto_ops` una operación `decrypt` con propósito `mask` por campo; sigue sin escribir auditoría `reveal`: corregido por DECISIONES N-01.
- La firma pura `members.mask(field, blob_meta)` → pasa a `mask(field, value)` sobre el valor descifrado en memoria (definida en US-069): corregido por DECISIONES N-01.
- El criterio 4 y el supuesto dicen que el coach recibe 404 al abrir un socio dado de baja → admin y coach lo ven en solo lectura, con la etiqueta "Dado de baja" y sin acciones de edición ni venta; el admin ve además "Reactivar" (US-076): corregido por DECISIONES N-20.
- Q16 ya está en la historia (aviso "Sin autorización de datos registrada" sin bloquear nada); se mantiene.

## Validación contra el dominio

- Lectura del aggregate `Member`; `membership_status` es consulta derivada que calcula `memberships` (`02_domain_model.md` 2.1).
- RN-13: los datos sensibles nunca salen completos; RN-14: el dado de baja sigue existiendo y se ve marcado.
- Sin eventos. Función pura `mask` reutilizada. Sin discrepancias de dominio.

## Validación contra la arquitectura

- Módulo dueño: `members`. Llama a `memberships.service.status_for([id])` con el import perezoso del par permitido `("members", "memberships")` de US-071.
- Bus: el descifrado ocurre por el tipo `Encrypted` (US-028), es decir, por `core.crypto.bus.decrypt`; ninguna primitiva fuera de `core/crypto`.
- Propósito del descifrado: resuelto por US-024 (columna `crypto_ops.purpose` en `0003_crypto`) y US-029 (`decrypt(..., purpose="mask")`); antes era una brecha, cerrada en la consolidación.
- Rol: `require_role("admin", "coach")`. Sin auditoría de lectura (solo `crypto_ops`), coherente con N-01.

## Preguntas abiertas

- Ninguna. La brecha original (propósito en `crypto_ops`) quedó cerrada en la consolidación: `0003_crypto` incluye `purpose` (validado en código con `OpPurpose`) y el bus lo recibe por argumento con nombre. No hace falta `0014_crypto_ops_purpose`.

## Tareas

### Migración Alembic
- No aplica (la columna `purpose` la crea `0003_crypto` en US-024).

### Models
- No aplica.

### Service
- [ ] T1 · Caso de uso `async def get(session, member_id: UUID, by: Actor) -> MemberDetailOut`: carga el socio aunque tenga `deleted_at`; abre `bus.op_context(user_id=by.id, record_id=member_id, purpose="mask")` y descifra en un solo `bus.batch("decrypt")` los cinco campos; aplica `mask` a cada uno; pide `status_for([member_id])` con import perezoso; lanza `MemberNotFound` si no existe; nunca escribe auditoría — 3 h

### Schemas
- [ ] T2 · Reutilizar `MemberDetailOut` de US-069 (sin `warnings` en lectura: lista vacía); asegurar que ningún campo sensible tenga tipo distinto de `str | None` enmascarado — 0.5 h

### Router
- [ ] T3 · `GET /api/v1/members/{id}` con `id: UUID` (422 si no es UUID), `Depends(require_role("admin", "coach"))`, 404 con el envelope si no existe; cabecera `Cache-Control: no-store` — 1 h

### Tests unitarios puros
- [ ] T4 · Ampliar `api/tests/members/test_member_rules.py` con los casos de `mask` que pinta la ficha (documento corto de 4 dígitos o menos, correo sin dominio reconocible, contacto de emergencia sin teléfono) — 0.5 h

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/members/test_service_get.py`: los cinco campos vuelven enmascarados (`•••• 0304`, `••• ••• 4567`, `l•••@•••.com`, `••/••/1990`, `Registrado`); `crypto_ops` recibe cinco filas `decrypt` con el mismo `batch_id` y `purpose = 'mask'`; `audit.audit_log` no recibe ninguna fila `reveal`; un socio con `deleted_at` se devuelve con `deleted_at` lleno; `membership_status` viene de `status_for` (doble hasta US-092) — 2.5 h

### Tests de router
- [ ] T6 · `api/tests/members/test_router_get.py`: 200 admin y coach, 200 de coach sobre un dado de baja (N-20), 403 `member`, 401 sin token, 404 inexistente, 422 id no UUID, cabecera `no-store`, la respuesta no contiene el documento en claro — 1.5 h

### Tests de arquitectura
- [ ] T7 · `api/tests/architecture/test_service_import_graph.py` (de US-071) cubre el nuevo import perezoso en `get` dentro del par permitido; sin cambios en la lista blanca — 0.5 h

### Front
- [ ] T8 · `web/src/features/members/api.ts`: `useMember(id)` — 0.5 h
- [ ] T9 · `web/src/features/members/pages/MemberDetailPage.tsx`: `PageHeader` con nombre, `StatusTag` de membresía y acciones por rol con `useCan` (Editar y Vender membresía para admin y coach; Dar de baja solo admin); si `deleted_at` no es nulo, etiqueta "Dado de baja", sin acciones de edición ni venta y "Reactivar" solo para admin; bloque de datos con `MaskedValue` por campo sensible (el botón "Mostrar" lo conecta US-074); aviso "Sin autorización de datos registrada" si `data_consent_at` es nulo (`// DESIGN-GAP:`); `Tabs` Membresías, Pagos e Historial (contenido en US-093, US-101, US-106) con la pestaña activa en la URL y Asistencia, Resultados, Atleta, Avisos y Adjuntos deshabilitadas con su versión; estados de carga, 404 ("Socio no encontrado") y error con reintento — 3.5 h
- [ ] T10 · Vitest `web/src/features/members/pages/MemberDetailPage.test.tsx`: acciones por rol, modo solo lectura del dado de baja, aviso de autorización, pestañas y 404 — 1.5 h

### DevOps
- [ ] T11 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T12 · Revisar que el valor descifrado no sobreviva fuera de la función (no se guarda en la sesión ni en caché), que el log de la petición no contenga valores enmascarados ni claros y que el 404 no distinga entre "no existe" y "id de otro esquema" — 0.5 h

## Orden de ejecución

1. Confirmar que US-024 y US-029 están hechas (columna `purpose` y argumento `purpose` del bus).
2. T4 y T5 (en rojo), luego T1 y T2.
3. T3, T6 y T7.
4. T11 y T12.
5. T8, T9 y T10.

## Dependencias técnicas

- US-069 · Registrar socio: tabla, `MemberDetailOut` y `mask`.
- US-024 · Tablas crypto_keys, crypto_ops y crypto_jobs: columna `purpose`.
- US-029 · Bitácora crypto_ops por lote: argumento `purpose` en `decrypt`.
- US-071 · Filtrar socios: prueba de ciclos y par perezoso permitido.
- US-092 · Resumen y consultas de estado: `status_for` (doble hasta entonces).
- US-040 · Matriz de permisos del front; US-064 · Encabezado, pestañas y KPI; US-066 · Valor enmascarado e historial.

## Endpoints

- `GET /api/v1/members/{id}` — roles: admin, coach

## Riesgos

- Cada apertura de ficha hace cinco descifrados: costo bajo, pero multiplica las filas de `crypto_ops` — mitigación: un solo `bus.batch` por ficha (cinco filas con el mismo `batch_id`, una por `data_class`).
- Sin la columna `purpose`, la bitácora no separa enmascarados de `reveal`: se pierde la evidencia que N-01 pide — mitigación: no cerrar la historia hasta que EP-02 integre la propuesta.
- El valor completo pasa por memoria del proceso para enmascararlo — mitigación: aceptado por N-01 y por `04_architecture_decision.md` sección 8; la variable vive solo dentro de `get`.
- Front condicionado a D1.

## Estimación

- Backend: 4.5 h
- Front: 5.5 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 16 h**

Supera en 1 h la referencia de 3 puntos por el modo de solo lectura de N-20 en la ficha.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_member_rules.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_get.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_get.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/pages/MemberDetailPage.test.tsx`
- [ ] Después de abrir una ficha: `psql -c "SELECT verb, purpose, count(*) FROM crypto.crypto_ops WHERE record_id = '<id>' GROUP BY 1,2"` muestra `decrypt | mask | 5` y `psql -c "SELECT count(*) FROM audit.audit_log WHERE action='reveal' AND record_id='<id>'"` devuelve 0.
- [ ] `curl /api/v1/members/<id_dado_de_baja>` con token de coach responde 200 con `deleted_at` lleno.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
