# EP-02 · Bus de criptografía y cifrado de datos personales

- **Versión del plan:** v0.1 (Tarea 2).
- **Bounded context:** Crypto (soporte, transversal, `core/crypto/`, esquema `crypto`). Shared Kernel restringido con Members, Athletes, Attachments y Audit.
- **Estimación relativa:** L.

## Objetivo de negocio

Que la cédula, el teléfono, el correo, la fecha de nacimiento y el contacto de emergencia de los socios nunca estén en claro en la base ni en los backups, y que aun así recepción pueda buscar a un socio por documento o teléfono en un segundo. Es la respuesta directa al riesgo legal de la Ley 1581 de 2012 descrito en el problema del producto (RN-13).

## Actores

- Módulos con datos sensibles (Members en v0.1; Athletes, Attachments y Audit después), que llaman al bus.
- Administrador, que inicializa la KEK local y ejecuta la rotación por CLI.
- Worker y CLI, que hacen operaciones masivas por lote.

## Capacidades incluidas

- Única puerta del bus (`bus.py`): `encrypt(data_class, plaintext, aad)`, `decrypt(blob, aad)`, `blind_index(data_class, value)`, `sign(data_class, data)`, `verify(data_class, data, signature)`. El que llama nunca elige llave ni algoritmo.
- Puerto `KeyProvider` (`wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info`) con la implementación `LocalFileProvider`: KEK de 32 bytes en un archivo con permisos 600 fuera del repo, creada por `cli init-keys`; firma Ed25519 con llave aparte.
- Envelope: DEK por `data_class`, envuelta en `crypto.crypto_keys`, abierta en memoria al arrancar. Campos en AES-256-GCM con `aad = id del registro`.
- Formato del blob `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`, con `alg = A256GCM` en v0.1. El algoritmo va en el dato, no en el código.
- Índice ciego HMAC-SHA-256 sobre el valor normalizado (`crypto.normalize_for_index`: minúsculas, sin espacios ni puntos), con llave propia por `data_class`, en la columna `<campo>_idx`.
- Tipos de columna `Encrypted(data_class)` y `BlindIndexed(data_class)` en `core/crypto/types.py`.
- Aggregates `CryptoKey` (una sola `active` por `purpose` y `data_class`; estados `active`, `decrypt_only`, `retired`), `CryptoOp` (bitácora inmutable: quién, verbo, data_class, key_id, versión, record_id, resultado, `batch_id`) y `CryptoJob` (progreso de rotaciones y recifrados).
- Clases de dato de v0.1: `member.document`, `member.phone`, `member.email` (las tres con índice ciego), `member.birth_date` y `member.emergency_contact`.
- `cli rotate-key <data_class>`: DEK nueva, la anterior pasa a `decrypt_only`, recifrado por lotes de 500 con progreso en `crypto_jobs` (para que la pantalla de EP-18 tenga qué mostrar, `BRECHAS.md` sección 2) y retiro de la anterior al terminar.
- Prueba de arquitectura `test_banned_imports.py`, que complementa la regla `banned-api` de ruff (EP-00).

## Fuera de alcance

- Proveedor OpenBao y migración de proveedor (EP-15).
- Router `/crypto/*`, pantalla de llaves e informe CBOM (EP-18 y EP-26).
- Firma de la auditoría con ML-DSA (EP-17) y envoltura con ML-KEM (EP-26).
- Cifrado de medidas corporales (EP-24) y de adjuntos sensibles (EP-19).

## Criterios de éxito medibles

- Prueba de ida y vuelta de cifrado para las cinco clases de dato de v0.1.
- Prueba de AAD: un blob copiado a otro registro no descifra.
- Prueba de índice ciego: `"1.020.304"`, `"1020304"` y `" 1020304 "` producen el mismo índice.
- Prueba de rotación: después de rotar, los datos viejos se leen y los nuevos usan la llave nueva; al terminar el job la llave anterior queda `retired`.
- `SELECT document FROM members.members` no contiene ningún valor en claro (prueba de arquitectura de `05_service_design.md` sección 6).
- Cada operación del bus deja una fila en `crypto_ops`; ninguna fila de `crypto_keys` contiene material en claro.
- Una prueba falla si un módulo importa `cryptography` directamente (criterio de salida de la Tarea 2).

## Dependencias

- EP-01 Núcleo compartido (base, mixin, eventos, auditoría).
- EP-00 Cimientos (volumen de la KEK y regla `banned-api`).

## Riesgos

- Perder la KEK local equivale a perder todos los datos cifrados: se necesita un procedimiento de respaldo de la KEK fuera del servidor (lo cubre EP-13).
- Cambiar el formato del blob después de tener datos es irreversible; `CLAUDE.md` exige detenerse y preguntar.
- Las DEK viven en memoria del proceso; quien entre al contenedor en ejecución puede leerlas. Riesgo aceptado para v0.1 (`04_architecture_decision.md` sección 8) y mitigado en EP-15.
- Costo de `crypto_ops` por operación en listas grandes: hay que registrar por lote para no multiplicar escrituras.

## Pantallas del diseño que habilita

- Ninguna propia en v0.1. Es requisito del valor enmascarado (`MaskedValue`) de `Socio_Ficha` y de la búsqueda de `Socios_Lista` (EP-07), y de `Llaves` (EP-18).
