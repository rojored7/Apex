# EP-17 · Auditoría firmada post-cuántica

- **Versión del plan:** v0.3 (punto 1 de la versión 0.3).
- **Bounded context:** Audit (soporte), con el bus de Crypto para firmar (`audit.signature`).
- **Estimación relativa:** M.

## Objetivo de negocio

Que la cadena de auditoría no solo detecte una fila alterada, sino que también pruebe que nadie, ni siquiera quien tenga acceso a la base, reescribió la cadena entera desde un punto. Una firma nocturna fuera del alcance del servidor de aplicación sella cada día lo ocurrido, y se hace con un algoritmo resistente a computación cuántica (ML-DSA) para que la evidencia dure.

## Actores

- Worker: firma cada noche.
- Administrador: consulta y verifica firmas.
- OpenBao Transit: custodio de la llave de firma.

## Capacidades incluidas

- Entidad `AuditSignature`: `through_seq`, `hash`, `signature` (ML-DSA), `key_id`, `signed_at`, en la tabla `audit.signatures`, append-only.
- Job `worker/jobs/sign_audit.py`: firma el último hash de la cadena con ML-DSA desde OpenBao Transit (OpenBao 2.7 o superior), vía `bus.sign("audit.signature", ...)`.
- `cli sign-audit` para firmar a demanda.
- La verificación de EP-11 se amplía: además de recorrer la cadena, comprueba cada firma contra su `through_seq` y reporta la última firma válida.
- Clase de dato `audit.signature` en `crypto_keys` con algoritmo `ML-DSA-65`.

## Fuera de alcance

- Firma de backups (EP-26).
- Publicación de los hashes firmados en un tercero (sello de tiempo externo).

## Criterios de éxito medibles

- Cada noche queda una firma nueva si hubo filas nuevas; si no las hubo, no se firma dos veces el mismo `through_seq`.
- Reescribir la cadena completa desde una fila (recalculando todos los hashes) es detectado por la verificación porque la firma ya no coincide.
- La llave privada de firma nunca aparece en el servidor de aplicación (solo en OpenBao).
- La pantalla de auditoría muestra la fecha y el `seq` de la última firma válida.

## Dependencias

- EP-11 Auditoría y trazabilidad (cadena y verificación).
- EP-15 Custodia de llaves con OpenBao (Transit con ML-DSA).
- EP-13 Puesta en marcha y continuidad (worker).

## Riesgos

- Soporte de ML-DSA en OpenBao Transit depende de la versión 2.7 o superior; si no está disponible, la épica se bloquea o se cae a Ed25519 temporalmente (decisión a tomar, no a asumir).
- Si OpenBao está sellado a la hora de firmar, la firma de esa noche se pierde; el job debe reintentar y avisar.

## Pantallas del diseño que habilita

- Estado de firma en `Auditoria`.
