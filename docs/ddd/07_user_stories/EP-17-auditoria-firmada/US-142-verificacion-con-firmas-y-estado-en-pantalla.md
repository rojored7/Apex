# US-142 · Como administrador quiero que la verificación de auditoría compruebe también las firmas y me muestre la última firma válida para demostrar que nadie reescribió la historia

- **Épica:** EP-17 · Auditoría firmada post-cuántica
- **Bounded context:** Audit (esquema `audit`) con Crypto
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Auditoria` (`/sistema/auditoria`, estado de firma)

## Historia

Como administrador
quiero que "Verificar cadena" compruebe cada firma contra su `through_seq` y que la pantalla muestre la fecha y el `seq` de la última firma válida
para detectar incluso una reescritura completa de la cadena desde una fila

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`, `AuditSignature`.
- **Reglas que aplica:** RN-16; Q27 (cada firma se verifica con la llave y el algoritmo con que se hizo, aunque la llave esté en `decrypt_only` o rotada).
- **Eventos que emite:** ninguno (la verificación se registra como acción `verify`)
- **Eventos que consume:** ninguno
- **Funciones puras:** `audit.verify_result(chain_ok, broken_at_seq, signatures_checked, first_bad_signature_seq) -> VerifyResult`

## Alcance

- **Backend:** ampliar `audit.service.verify()` y `cli verify-audit`; `GET /audit/signatures/latest`.
- **Front:** bloque de estado de firma en `Auditoria` y resultado ampliado de "Verificar cadena".

## Criterios de aceptación

1. `POST /api/v1/audit/verify` recorre la cadena (US-104) y además, por cada fila de `audit.signatures`, recalcula `signature_payload(through_seq, hash_en_la_cadena)` y llama `bus.verify("audit.signature", ...)` con la llave de su `key_id`.
2. El resultado incluye `chain_ok`, `broken_at_seq` (o `null`), `signatures_checked`, `signatures_valid`, `first_invalid_signature_seq` (o `null`) y `last_valid_signature` (`through_seq`, `signed_at` en UTC, `algorithm`).
3. Si alguien recalcula todos los hashes desde una fila alterada, `chain_ok` puede salir verdadero pero la firma que cubre ese tramo no coincide y `first_invalid_signature_seq` lo señala; el resultado global es "no íntegra".
4. Una firma hecha con una llave Ed25519 previa a la rotación a ML-DSA-65 se sigue verificando con su llave (Q27).
5. `GET /api/v1/audit/signatures/latest` devuelve la última firma válida conocida (de la última verificación) y la última firma registrada; solo `admin` (coach recibe 403).
6. La pantalla `Auditoria` muestra "Última firma válida: seq N, fecha (hora de Bogotá), algoritmo" y, si no hay firma en las últimas 48 horas, la advertencia "Firma atrasada".
7. La verificación queda registrada como acción `verify` con el resultado resumido.
8. `cli verify-audit` imprime el mismo resultado y sale con código distinto de 0 si la cadena o alguna firma no es válida.

## Escenarios BDD

```gherkin
# language: es
Característica: Verificación con firmas

  Escenario: Cadena y firmas íntegras
    Dado que inicié sesión como administrador
    Y hay 3 firmas válidas, la última con through_seq 1350
    Cuando pulso "Verificar cadena"
    Entonces el resultado es íntegro
    Y la pantalla muestra "Última firma válida: seq 1350"

  Escenario: Detectar una cadena reescrita
    Dado que alguien alteró la fila 1300 y recalculó todos los hashes siguientes
    Cuando verifico la cadena
    Entonces el resultado no es íntegro
    Y la primera firma inválida señalada es la que cubre el seq 1350
```

## Endpoints

- `POST /api/v1/audit/verify` — rol(es): admin — salida ampliada — códigos: 200, 202 (si corre en segundo plano), 401, 403
- `GET /api/v1/audit/signatures/latest` — rol(es): admin — códigos: 200, 401, 403

## Pantalla

- `Auditoria`: bloque de estado de firma junto al botón Verificar, `StatusTag` con texto (Íntegra, Alterada, Firma atrasada).

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `verify_result` en las combinaciones cadena ok/rota y firma ok/inválida.
- **Pruebas:** service con base real y OpenBao de prueba (reescritura completa detectada, llave rotada verificable); router; Vitest del bloque.
- **Archivos principales:** `api/src/app/modules/audit/service.py`, `api/src/app/modules/audit/router.py`, `web/src/features/system/pages/AuditPage.tsx`.

## Supuestos

- Supuesto: umbral de 48 horas para "Firma atrasada"; no está definido.
- Supuesto: el endpoint `GET /audit/signatures/latest` no está en el contrato; se nombra aquí.

## Dependencias

- US-141 · Firma nocturna de la cadena
- US-104 · Verificar cadena desde pantalla

## INVEST

- **Independiente:** amplía una verificación existente.
- **Negociable:** umbral de atraso y textos.
- **Valiosa:** convierte la firma en evidencia visible.
- **Estimable:** acotada.
- **Pequeña:** 5.
- **Testeable:** reescritura detectada en prueba.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y OpenBao de prueba en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol y envelope
- [ ] Front: prueba del bloque; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
