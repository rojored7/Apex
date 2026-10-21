# US-145 · Como administrador quiero rotar una llave desde la pantalla con confirmación y motivo para reaccionar a una sospecha de filtración sin abrir una terminal

- **Épica:** EP-18 · Administración de llaves de cifrado
- **Bounded context:** Crypto (`core/crypto/service.py`, esquema `crypto`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Llaves` (`/sistema/llaves`, modal Rotar)

## Historia

Como administrador
quiero rotar una llave desde la pantalla escribiendo "ROTAR" y un motivo
para cambiar la llave de una clase de dato cuando sospecho de una filtración o lo pide la política, sin dejar de leer los datos durante el proceso

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey`, `CryptoJob(kind = rotate)`, `CryptoOp(verb = rotate)`.
- **Reglas que aplica:** una sola llave `active` por (`purpose`, `data_class`); la anterior queda `decrypt_only` hasta que el job termine y luego `retired`; una sola rotación en curso por `data_class`; cada rotación se audita con motivo; RN-13; RN-14 (las llaves nunca se borran).
- **Eventos que emite:** ninguno de dominio (la rotación queda en `crypto_ops` y en auditoría).
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva (reutiliza el flujo de US-030).

## Alcance

- **Backend:** `POST /api/v1/crypto/keys/{id}/rotate` que valida, crea la DEK nueva, deja la anterior en `decrypt_only`, crea un `CryptoJob` y lanza en segundo plano el mismo recifrado por lotes de 500 de `cli rotate-key` (US-030).
- **Front:** botón "Rotar" por llave `active` con `ConfirmModal` que muestra la clase de dato, el número de registros afectados, un campo de motivo y un campo donde se escribe "ROTAR".

## Criterios de aceptación

1. El endpoint exige rol `admin`; coach y socio reciben 403.
2. Sin `reason` (vacío o solo espacios) o con `confirm` distinto de la cadena exacta `"ROTAR"` devuelve 422 con `field`.
3. Solo se puede rotar una llave en estado `active`; rotar una `decrypt_only` o `retired` devuelve 409.
4. Si ya existe un `CryptoJob` `running` para la misma `data_class`, devuelve 409 y no crea otra llave.
5. Una rotación aceptada responde 202 con el `job_id`; en la misma transacción queda la llave nueva `active` (versión + 1), la anterior `decrypt_only`, el `CryptoJob` creado y una fila de auditoría con el usuario y el motivo.
6. Durante el recifrado los datos de la clase siguen legibles: una lectura de un registro aún no recifrado descifra con la llave `decrypt_only` y uno ya recifrado con la nueva.
7. Al terminar el job, la llave anterior pasa a `retired` y `CryptoJob.status = done`; si el job falla, queda `failed` con `error` y la llave anterior sigue `decrypt_only` (ningún dato queda ilegible).
8. Cada lote registra sus operaciones en `crypto_ops` con un mismo `batch_id`.
9. Ninguna respuesta incluye material de llave.

## Escenarios BDD

```gherkin
# language: es
Característica: Rotar una llave desde la pantalla

  Escenario: Rotación confirmada de la llave de teléfonos
    Dado que inicié sesión como administrador
    Y la llave "member.phone" versión 1 está activa y protege 1200 registros
    Cuando abro "Rotar", escribo el motivo "posible filtración del portátil de recepción" y escribo "ROTAR"
    Entonces recibo la confirmación de que la rotación empezó
    Y la llave versión 2 queda activa y la versión 1 queda "decrypt_only"
    Y en la pestaña Trabajos veo el avance por lotes de 500
    Y al terminar la versión 1 queda "retired" y todos los teléfonos se siguen leyendo

  Escenario: Segunda rotación mientras hay una en curso
    Dado que hay una rotación en curso de "member.phone"
    Cuando el administrador pide rotar de nuevo "member.phone"
    Entonces recibe 409 y no se crea ninguna llave nueva

  Escenario: Confirmación mal escrita
    Dado que inicié sesión como administrador
    Cuando envío la rotación con confirm "rotar"
    Entonces recibo 422 con field "confirm"
```

## Endpoints

- `POST /api/v1/crypto/keys/{id}/rotate` — rol(es): admin — entrada: `{ reason: string, confirm: "ROTAR" }` — salida: `{ job_id, new_key_id, previous_key_id }` — códigos: 202, 401, 403, 404, 409, 422

## Pantalla

- `Llaves`, modal Rotar (`ConfirmModal` con motivo y texto de confirmación). Tras confirmar, la vista salta a la pestaña Trabajos. Estado de error con el mensaje del envelope.

## Notas técnicas

- **Migración:** no; si no existe, índice único parcial `crypto_jobs(data_class) WHERE status = 'running'` para garantizar una sola rotación en curso (una migración).
- **Trigger / restricciones:** índice único parcial `crypto_keys(purpose, data_class) WHERE state = 'active'` (de US-024).
- **Funciones puras a probar:** validación del cuerpo (`confirm` exacto, `reason` no vacío).
- **Pruebas:** service con base real (transición de estados, concurrencia 409, lectura durante el recifrado, fallo a mitad), router (rol, 422), front (modal deshabilita confirmar hasta escribir "ROTAR").
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `api/src/app/core/crypto/router.py`, `web/src/features/system/components/RotateKeyModal.tsx`.

## Supuestos

- Supuesto: el job corre en segundo plano dentro del proceso del API (tarea asíncrona), no en el worker; si el API se reinicia, el job queda `running` sin avance y se reanuda con `cli rotate-key --resume <job_id>` (no está definido quién reanuda).
- Supuesto: la rotación aplica a llaves de `purpose = encrypt`; rotar llaves de índice ciego (`index`) exige recalcular todos los `_idx` y no está cubierto aquí.

## Dependencias

- US-144 · Bitácora y trabajos (seguimiento del job)
- US-030 · Rotación de llave por CLI (flujo de recifrado reutilizado)

## INVEST

- **Independiente:** reusa el flujo ya probado por CLI.
- **Negociable:** forma de confirmación y advertencias.
- **Valiosa:** permite responder a un incidente en minutos.
- **Estimable:** endpoint + modal + manejo de concurrencia.
- **Pequeña:** cabe en un sprint.
- **Testeable:** estados de llave y 409/422 verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para la rotación
- [ ] Revisión de PR aprobada
