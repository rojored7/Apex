# US-104 · Como administrador quiero verificar la integridad de la cadena de auditoría desde la pantalla para demostrar que el historial no fue alterado

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Auditoria` (`/sistema/auditoria`, botón "Verificar cadena")

## Historia

Como administrador
quiero presionar "Verificar cadena" y saber si la auditoría está íntegra o en qué fila exacta se rompe
para demostrar, incluso ante la Ley 1581, que el historial no fue alterado

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`.
- **Reglas que aplica:** RN-16 (`hash = SHA-256(prev_hash || canonical(row))`; una fila alterada rompe la cadena; la verificación recorre toda la cadena), `05_service_design.md` (con más de 100.000 filas corre aparte y devuelve la última verificación), la verificación queda registrada como acción `verify`.
- **Eventos que emite:** ninguno (escribe una entrada `verify` en auditoría).
- **Eventos que consume:** ninguno.
- **Funciones puras:** `audit.chain_hash(prev_hash, row)` (de US-015) y `core.audit.verify_chain(rows_iter) -> VerifyResult { ok, rows_checked, broken_at_seq? }`.

## Alcance

- **Backend:** `audit.service.verify()` que recorre la cadena por lotes en orden de `seq`, recalcula cada hash y se detiene en la primera fila rota; si la tabla tiene más de 100.000 filas, lanza la verificación en una tarea en segundo plano y responde 202 con la última verificación conocida; el resultado se registra como entrada `verify` con `after = { ok, rows_checked, broken_at_seq, started_at, finished_at }`. `GET /audit/verify/last` devuelve la última.
- **Front:** botón "Verificar cadena" en `Auditoria` con estado "Verificando...", resultado "Cadena íntegra: N filas verificadas" o "Cadena rota en el registro seq X" con enlace al detalle, y fecha de la última verificación.

## Criterios de aceptación

1. `POST /api/v1/audit/verify` con 100.000 filas o menos responde 200 con `{ ok, rows_checked, broken_at_seq, finished_at }` cuando termina.
2. Con una fila alterada a mano (con el trigger deshabilitado en la prueba) la verificación devuelve `ok = false` y `broken_at_seq` igual al `seq` exacto alterado.
3. Con más de 100.000 filas responde 202 con `{ status: "running", last: <última verificación o null> }` y no bloquea otras peticiones; al terminar, `GET /api/v1/audit/verify/last` devuelve el resultado nuevo.
4. Una segunda petición mientras hay una verificación en curso devuelve 409 con `code = "verification_running"`.
5. Cada verificación terminada deja una entrada de auditoría con `action = "verify"`, el usuario que la pidió y el resultado; esa entrada entra a la cadena como cualquier otra.
6. La verificación de 100.000 filas de prueba termina en menos de 60 segundos o queda en segundo plano sin bloquear el API.
7. La verificación nunca escribe ni corrige filas existentes.
8. Rol: `require_role("admin")`; coach recibe 403; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Verificar la cadena de auditoría

  Antecedentes:
    Dado que estoy autenticado como "admin"

  Escenario: La cadena está íntegra
    Dado una cadena de 5000 entradas sin alterar
    Cuando presiono "Verificar cadena"
    Entonces veo "Cadena íntegra: 5000 filas verificadas"
    Y la auditoría tiene una nueva entrada "verify" con mi usuario

  Escenario: Detecto la fila alterada
    Dado una cadena de 5000 entradas donde la fila con "seq" 1234 fue modificada a mano
    Cuando presiono "Verificar cadena"
    Entonces veo "Cadena rota en el registro seq 1234"

  Escenario: Cadena grande se verifica en segundo plano
    Dado una cadena de 150000 entradas
    Cuando pido verificar
    Entonces la respuesta es 202 con estado "running"
    Y al terminar la última verificación muestra el resultado

  Escenario: No se lanzan dos verificaciones a la vez
    Dado que hay una verificación en curso
    Cuando pido verificar otra vez
    Entonces la respuesta es 409 con "code" igual a "verification_running"

  Escenario: El coach no verifica
    Dado que estoy autenticado como "coach"
    Cuando pido verificar la cadena
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/audit/verify` — rol(es): admin — salida: `VerifyResult` (200) o `{ status, last }` (202) — códigos: 200, 202, 401, 403, 409.
- `GET /api/v1/audit/verify/last` — rol(es): admin — salida: `VerifyResult | null` — códigos: 200, 401, 403.

## Pantalla

- `Auditoria` en `/sistema/auditoria`: botón "Verificar cadena", indicador de progreso, resultado y fecha de la última verificación (hora de Bogotá).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** las pruebas de alteración deshabilitan el trigger append-only solo dentro de la transacción de prueba.
- **Funciones puras a probar:** `verify_chain` con cadena íntegra, fila 1 alterada, fila del medio alterada, fila borrada (salto de `seq`).
- **Pruebas:** pura; service con base real (100.000 filas con `FrozenClock`, medición de tiempo); router (200/202/409, rol); front (estados del botón).
- **Archivos principales:** `api/src/app/core/audit.py` (`verify_chain`), `api/src/app/modules/audit/{service,router}.py`, `web/src/features/system/components/VerifyChainButton.tsx`.

## Supuestos

- Supuesto: el resultado de cada verificación se guarda como entrada `verify` de la propia auditoría (no hay tabla nueva) y "la última verificación" se lee de la entrada `verify` más reciente.
- Supuesto: la tarea en segundo plano corre en el proceso del API (tarea asyncio con su propia sesión); si el API se reinicia, la verificación en curso se pierde y se puede volver a pedir.
- Supuesto: se agrega `GET /audit/verify/last`, que no está en el contrato de `05_service_design.md`.
- Supuesto: un salto en `seq` (fila borrada) se reporta como cadena rota en el primer `seq` faltante.

## Dependencias

- US-102 · Consultar auditoría (pantalla donde vive el botón).

## INVEST

- **Independiente:** usa `chain_hash` de US-015; no requiere otras pantallas.
- **Negociable:** umbral de segundo plano y presentación del resultado.
- **Valiosa:** prueba de integridad ante un reclamo.
- **Estimable:** un recorrido por lotes y un endpoint.
- **Pequeña:** cuatro a cinco días.
- **Testeable:** alteración detectada en el `seq` exacto.

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
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada (entrada `verify`)
- [ ] Revisión de PR aprobada
