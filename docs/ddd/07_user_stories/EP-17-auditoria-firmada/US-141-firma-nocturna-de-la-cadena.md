# US-141 · Como administrador quiero que cada noche se firme el último eslabón de la cadena de auditoría para sellar lo ocurrido en el día

- **Épica:** EP-17 · Auditoría firmada post-cuántica
- **Bounded context:** Audit (esquema `audit`) con Crypto
- **Versión:** v0.3
- **Actor:** administrador (ejecuta el worker)
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (el resultado se ve en US-142)

## Historia

Como administrador
quiero que el worker firme el hash de la última fila de auditoría con la llave `audit.signature` y que pueda firmar a demanda por CLI
para que nadie pueda reescribir la cadena desde un punto sin que la firma lo delate

## Contexto de dominio

- **Aggregate / entidades:** `AuditSignature`, `AuditEntry`.
- **Reglas que aplica:** RN-16; Q27 (el algoritmo lo decide la llave registrada); "no se firma dos veces el mismo `through_seq`" (EP-17).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `audit.needs_signature(last_seq, last_signed_seq) -> bool`

## Alcance

- **Backend:** job `worker/jobs/sign_audit.py` en el horario del worker; `cli sign-audit`; llamada `bus.sign("audit.signature", signature_payload(seq, hash))`.
- **Front:** No aplica.

## Criterios de aceptación

1. El job lee la última fila de `audit.audit_log` (`seq`, `hash`); si `seq` es mayor que el mayor `through_seq` firmado, firma `signature_payload(seq, hash)` con `bus.sign("audit.signature", ...)` y guarda una fila en `audit.signatures` con `key_id`, `algorithm` y `signed_at` en UTC.
2. Si no hubo filas nuevas desde la última firma, no crea fila (no firma dos veces el mismo `through_seq`).
3. Si OpenBao está sellado o no responde, el job reintenta 3 veces con espera creciente; si sigue fallando, termina con error registrado en logs sin datos sensibles y en `crypto_ops` con `result = error`; la noche siguiente firma hasta el último `seq` (no se pierde cobertura).
4. `cli sign-audit` hace lo mismo a demanda y devuelve código de salida 0 al firmar o al no haber nada nuevo, y distinto de 0 si falla.
5. Cada firma deja una fila en `crypto_ops` con verbo `sign`, `data_class = audit.signature` y `key_id`.
6. La llave privada nunca se lee en el proceso de la aplicación: la firma la hace OpenBao Transit.
7. Dos ejecuciones simultáneas (job y CLI) no crean dos firmas del mismo `through_seq` (restricción única y bloqueo de aviso).

## Escenarios BDD

```gherkin
# language: es
Característica: Firma nocturna de la auditoría

  Escenario: Firmar las filas del día
    Dado que la última firma cubre hasta el seq 1200
    Y la cadena de auditoría llega hasta el seq 1350
    Cuando el worker corre el job de firma
    Entonces existe una firma nueva con through_seq 1350
    Y queda registrada la operación "sign" en la bitácora criptográfica

  Escenario: No repetir firma sin cambios
    Dado que la última firma cubre hasta el seq 1350
    Y no hubo filas nuevas
    Cuando el worker corre el job de firma
    Entonces no se crea ninguna firma

  Escenario: OpenBao sellado
    Dado que OpenBao está sellado
    Cuando el worker corre el job de firma
    Entonces el job termina con error después de 3 intentos
    Y la bitácora criptográfica registra el error
```

## Endpoints

- Ninguno. Job `worker/jobs/sign_audit.py`; comando `cli sign-audit`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** único en `through_seq` (US-140); `pg_advisory_xact_lock` para evitar carreras.
- **Funciones puras a probar:** `needs_signature` en los bordes.
- **Pruebas:** job con `FrozenClock`, base real y OpenBao de prueba; caso sellado con proveedor que falla; prueba de concurrencia.
- **Archivos principales:** `api/src/app/worker/jobs/sign_audit.py`, `api/src/app/core/audit.py`, `api/src/app/cli.py`.

## Supuestos

- Supuesto: 3 reintentos con espera creciente; EP-17 dice "reintentar y avisar" sin cifra.
- Supuesto: "avisar" se cumple en v0.3 con el log de error, la bitácora y el estado en la pantalla de Auditoría (US-142); no hay canal de alerta al administrador definido.
- Supuesto: el job corre en el horario único del worker (07:00 Bogotá), aunque la épica dice "cada noche"; si se quiere de madrugada hace falta una segunda hora de disparo.

## Dependencias

- US-140 · Registro de firmas de auditoría
- US-113 · Proceso worker programado

## INVEST

- **Independiente:** un job y un comando.
- **Negociable:** hora y reintentos.
- **Valiosa:** sella la evidencia diaria.
- **Estimable:** flujo acotado.
- **Pequeña:** 5.
- **Testeable:** filas de firma verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas del job con PostgreSQL real y OpenBao de prueba en verde; cobertura de 80 % o más en lo tocado
- [ ] Revisión de PR aprobada
