# US-140 · Como administrador quiero un registro inmutable de firmas de la cadena de auditoría con su propia llave para poder probar que la historia no fue reescrita

- **Épica:** EP-17 · Auditoría firmada post-cuántica
- **Bounded context:** Audit (esquema `audit`) con Crypto (`audit.signature`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que exista la tabla de firmas de auditoría y una llave de firma registrada para la clase de dato `audit.signature`
para que la firma nocturna tenga dónde guardarse y con qué firmar sin que la llave privada pase por el servidor de aplicación

## Contexto de dominio

- **Aggregate / entidades:** `AuditSignature` (`through_seq`, `hash`, `signature`, `key_id`, `signed_at`); `CryptoKey` con `purpose = sign`, `data_class = audit.signature`.
- **Reglas que aplica:** RN-14 (la auditoría y las llaves nunca se borran); RN-16; Q27 (si OpenBao no ofrece ML-DSA, la llave se crea con Ed25519 y se rota a `ML-DSA-65` después; las firmas viejas se verifican con su llave).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `audit.signature_payload(through_seq, hash) -> bytes` (serialización canónica de lo que se firma)

## Alcance

- **Backend:** migración `audit.signatures` con trigger append-only; registro de la llave `audit.signature` en `crypto_keys` vía `cli init-keys --data-class audit.signature`, con algoritmo decidido por disponibilidad en OpenBao.
- **Front:** No aplica.

## Criterios de aceptación

1. Existe `audit.signatures` con `id` (UUID), `through_seq` (bigint, único), `hash`, `signature`, `key_id` (FK lógica a `crypto_keys`), `algorithm`, `signed_at` (TIMESTAMPTZ) y columnas comunes.
2. Un `UPDATE` o `DELETE` sobre `audit.signatures` es rechazado por un trigger de PostgreSQL.
3. `cli init-keys --data-class audit.signature` crea en OpenBao Transit una llave de firma `ML-DSA-65` si la versión la soporta; si no, `Ed25519`, y deja la fila en `crypto_keys` con `purpose = sign`, `provider = openbao`, `algorithm` real y `state = active`. Correrlo dos veces no crea otra llave.
4. Ninguna fila de `crypto_keys` ni de `audit.signatures` contiene material privado.
5. `signature_payload` produce los mismos bytes para el mismo `through_seq` y `hash` y está documentada en el ADR de auditoría (cambiarla rompe la verificación).
6. El comando registra la operación en `crypto_ops` y deja auditoría.

## Escenarios BDD

```gherkin
# language: es
Característica: Llave y registro de firmas de auditoría

  Escenario: Crear la llave de firma con ML-DSA disponible
    Dado que OpenBao Transit soporta ML-DSA-65
    Cuando ejecuto "cli init-keys --data-class audit.signature"
    Entonces existe una llave activa de firma para "audit.signature" con algoritmo "ML-DSA-65"
    Y el material privado solo está en OpenBao

  Escenario: Respaldo con Ed25519
    Dado que OpenBao Transit no soporta ML-DSA
    Cuando ejecuto "cli init-keys --data-class audit.signature"
    Entonces la llave queda con algoritmo "Ed25519"
    Y el comando avisa que debe rotarse a ML-DSA-65 cuando esté disponible

  Escenario: La tabla de firmas no se puede alterar
    Dado que existe una firma registrada
    Cuando intento actualizar su columna "signature" directamente en la base
    Entonces la base rechaza el cambio
```

## Endpoints

- Ninguno. Comando `cli init-keys --data-class audit.signature`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí, `audit.signatures` y trigger `forbid_update_delete`.
- **Trigger / restricciones:** append-only; único en `through_seq`.
- **Funciones puras a probar:** `signature_payload` determinista.
- **Pruebas:** service con base real (trigger); integración contra OpenBao de `compose.dev.yml` en los dos modos (con y sin ML-DSA, este último simulando la respuesta de capacidades).
- **Archivos principales:** `api/src/app/core/audit.py`, `api/src/app/core/crypto/service.py`, `api/src/app/cli.py`, migración.

## Supuestos

- Supuesto: la disponibilidad de ML-DSA se detecta consultando las capacidades de Transit al crear la llave; la detección exacta depende de la versión de OpenBao.

## Dependencias

- US-015 · Tabla de auditoría y cadena de hashes
- US-134 · Proveedor OpenBao
- US-027 · Firma y verificación en el bus
- US-023 debe aceptar `cli init-keys --data-class` (agregado en consolidación)

## INVEST

- **Independiente:** solo prepara tabla y llave.
- **Negociable:** algoritmo según disponibilidad.
- **Valiosa:** base de la evidencia firmada.
- **Estimable:** migración y comando.
- **Pequeña:** 3.
- **Testeable:** trigger y fila de llave verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y OpenBao de prueba en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] ADR de auditoría actualizado con `signature_payload`
- [ ] Revisión de PR aprobada
