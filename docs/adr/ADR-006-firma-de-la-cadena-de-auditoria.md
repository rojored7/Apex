# ADR-006 · Firma de la cadena de auditoría

## Estado

Aceptado el 2026-11-11 (Sprint 6, v0.3; S6-D4, S6-D34, S6-D49, S6-D51, S6-D62, S6-D69 y S6-D81). Precisado el 2026-11-14 con autorización del usuario (S6-D142): `--provider local` solo con `CRYPTO_PROVIDER=local` y el residual del volumen `keys` en el api; ninguna regla de firma ni de verificación cambia. El formato del payload firmado es irreversible con datos reales: cambiar un solo byte invalida todas las firmas ya guardadas en `audit.signatures`. Cambiarlo, o cambiar el algoritmo, la clave que firma o la forma de verificar, exige detenerse y preguntar.

## Contexto

La cadena de hashes de `audit.audit_log` (ADR-004) detecta que una fila cambió, pero no quién la reescribió: quien controla la base y conoce el algoritmo puede recalcular la cadena entera desde la fila alterada y dejarla consistente. Una firma digital sobre el hash de una fila, hecha con una llave que la base no contiene, convierte esa reescritura en detectable: el atacante tendría que además falsificar la firma.

Fuerzas en juego:

- El api no debe poder firmar: un compromiso del api no puede fabricar firmas de una cadena reescrita. Firma el worker, de noche, y el api solo verifica.
- Verificar no puede depender del custodio: con OpenBao sellado o inalcanzable la verificación debe seguir funcionando y las firmas de llaves retiradas deben seguir verificando.
- No hay sello de tiempo externo en v0.3.
- OpenBao 2.7.2 (Transit) no ofrece ML-DSA ni SLH-DSA (sondeo del Sprint 6) y `liboqs` no está en las dependencias.

## Decisión

**Payload.** `signature_payload(through_seq, chain_hash, version=1)` es, todo en ASCII:

`b"apex-audit-sig-v1" + b"\n" + <through_seq en decimal> + b"\n" + <chain_hash>`

- `through_seq` es un entero mayor o igual que 1, en decimal sin signo ni ceros a la izquierda.
- `chain_hash` es el `hash` de la fila `through_seq` de `audit.audit_log` (no su `prev_hash`): 64 caracteres hexadecimales en minúscula. Ese hash ya encadena todo lo anterior.
- Cualquier otra entrada lanza `CanonicalError`. El prefijo separa dominios: la misma llave no firma otra cosa con el mismo formato.
- La versión viaja en `audit.signatures.payload_version`; el verificador elige el constructor por esa columna, de modo que un `v2` futuro no invalida las firmas viejas.

Vector de referencia (la fila es la de ADR-004; la prueba reconstruye el payload con `through_seq = 1` y el `hash` de esa fila, y compara byte a byte):

```signature-payload-vector
{
  "version": 1,
  "through_seq": 1,
  "hash": "097f1f232644029a217ea42c6e1e9c4871e508c30340a9369ce2a796a032f441",
  "payload": "apex-audit-sig-v1\n1\n097f1f232644029a217ea42c6e1e9c4871e508c30340a9369ce2a796a032f441",
  "payload_hex": "617065782d61756469742d7369672d76310a310a30393766316632333236343430323961323137656134326336653165396334383731653530386333303334306139333639636532613739366130333266343431"
}
```

**Algoritmo y llave.** Ed25519 es el único algoritmo de firma en v0.3. La clase `audit.signature` tiene llave propia (propósito `sign`, nunca compartida con una clase `encrypt`). Con el proveedor `openbao` la firma la hace Transit (`apex-sign-audit`, no exportable); con `local` la hace el archivo `custody/sign-ed25519.key`. `audit.signatures` guarda `algorithm` por fila, de modo que `SIGNATURE_ALGS` conserva `ML-DSA-65` para EP-26 sin migración.

**Quién firma y cuándo.** Solo el worker (política de Transit `sign`), en el job nocturno `sign_audit`. El api solo tiene `verify` en la política de Transit. Residual con `CRYPTO_PROVIDER=local`: el api monta el volumen `keys` entero en solo lectura, incluida `custody/sign-ed25519.key`, y la barrera real es el grant (ningún llamador de `sign_latest` fuera del worker y el CLI, `tests/architecture/test_audit_sign_callers.py`); montar en el api solo `custody/kek.bin` y `jwt/` queda para el Sprint 7 (S6-D133).

**Verificación incremental antes de firmar (H-1).** Firmar el hash de la última fila a ciegas daría fe de una cadena que quizá ya fue reescrita. Antes de firmar, `sign_audit` toma como ancla la última fila firmada (`last_signed_seq`) y recorre el tramo sin firmar recalculando `prev_hash` y `hash` con el serializador canónico (solo lectura; `core/audit.py` no cambia). Si el tramo no cuadra no firma: termina con `JobResult(ok=False)` y la alerta `audit_chain_broken` con `through_seq`.

**Verificación sin custodio (S6-D62, S6-D81).** Cada firma se verifica en el api con la clave pública Ed25519 guardada en `crypto_keys.public_key` de su `key_id` (base64 de los 32 bytes crudos), en cualquier estado de la llave (`active`, `decrypt_only`, `retired`). Nunca se llama al proveedor: funciona con OpenBao sellado. Además, la regla anti-retroceso compara el mayor `through_seq` firmado y persistido con el `last_valid_signature_seq` de la verificación anterior, de modo que borrar firmas recientes se detecta.

**Qué prueba una firma válida.** Que, al momento de firmar, la cadena de hashes hasta `through_seq` coincidía con la firmada por la llave de firma, y que desde entonces ninguna fila hasta `through_seq` cambió. **Qué no prueba:** (1) `signed_at` es informativa; no hay sello de tiempo externo, así que no demuestra cuándo se hizo una acción, solo que existía antes de la firma; (2) no protege filas posteriores a la última firma (el tramo entre firmas queda cubierto solo por la cadena); (3) no resiste a quien obtenga la llave de firma, ni al operador que controle el worker y la custodia a la vez; (4) no prueba que el contenido de cada acción fuera legítimo, solo que no se alteró.

**Rotación de la llave de firma.** En v0.3 la llave no se rota «en sitio» ni se recifra: una firma es inmutable. Cambiar de proveedor es una llave nueva: `rotate-key audit.signature --provider <local|openbao>` (`local` solo con `CRYPTO_PROVIDER=local`: con `compose.openbao.yml` el worker no monta `keys`, S5-D50, y el comando sale 2 antes de abrir la base, S6-D136) inserta la fila `version + 1` `active` con la referencia y la clave pública del proveedor destino y deja la anterior en `decrypt_only`. `migrate-provider` excluye las filas `sign` (sale 2 `signatures_reference_key`) porque la llave no viaja entre proveedores. `retire-key` rechaza una llave `sign` mientras existan firmas que la referencien. Pasar a ML-DSA-65 u otro algoritmo, y la rotación dentro del mismo proveedor (otra llave Transit con otro nombre), llegan con EP-26 con el mismo mecanismo (fila nueva, `payload_version` y `alg` por firma) y no tienen fecha en v0.3.

## Alternativas descartadas

- **ML-DSA-65 desde v0.3:** Transit de OpenBao 2.7.2 lo rechaza y `liboqs` no está en las dependencias; queda en EP-26.
- **Firmar dentro del api:** un compromiso del api podría fabricar firmas de una cadena reescrita; la política de Transit del api solo concede `verify`.
- **Verificar llamando a Transit por cada firma:** ata la verificación al custodio (sellado = sin verificación) y deja sin verificar las firmas de llaves retiradas. Con la clave pública guardada no hace falta.
- **Firmar `prev_hash` o la fila serializada completa:** el `hash` de la fila ya encadena todo lo anterior y no depende de reserializar.
- **Sello de tiempo externo (RFC 3161):** depende de un tercero y de red; fuera de v0.3.
- **Modificar `core/audit.py` o ADR-004:** la serialización de la cadena es irreversible; la firma vive en `core/audit_sign.py` como archivo hermano.

## Consecuencias

- Un atacante con acceso de escritura a la base ya no puede reescribir la historia hasta la última firma sin que la verificación lo detecte; sí puede alterar el tramo posterior a la última firma hasta la próxima corrida nocturna.
- Si el worker no firma (OpenBao sellado, cadena rota), la firma se atrasa: tras 48 h con filas sin firmar se emite la alerta `audit_sign_late`.
- Cambiar el prefijo, el orden de los campos o la codificación de enteros exige un `payload_version` nuevo; las firmas anteriores siguen verificando con su constructor.
- La clave pública se guarda en `crypto_keys.public_key` y es inmutable; se conserva mientras existan firmas que la referencien.
- Quien implemente un verificador externo puede hacerlo con el vector de arriba y las claves públicas del inventario.

- **La llave de firma solo se rota con `rotate-key audit.signature --provider` (A2).** Antes de entregar una firma, el bus la verifica con la clave pública de la fila `sign`; si no verifica (una versión nueva de `apex-sign-audit` en Transit o otra semilla en `custody/sign-ed25519.key`) no se guarda nada, `crypto_ops(sign)` queda con `result = error` y el job termina con `signature_unverifiable` hasta crear la fila nueva con su clave pública. Las políticas de OpenBao niegan `rotate` a api, worker y tools: rotar a mano exige la raíz y es un incidente.

- **Algoritmo distinto de `Ed25519` = firma inválida (cierre seguro).** La verificación solo acepta `Ed25519` con la clave pública guardada; cualquier otro `algorithm` cuenta como inválida. Hoy es inalcanzable, porque `bus.sign` rechaza `unsupported`; cambia con EP-26 (`ML-DSA-65`).
- **Frontera de confianza de `public_key`.** La clave pública es inmutable para `apex_api` y `apex_worker` por grants. Un propietario o superusuario de la base que apague los triggers, cambie `public_key` y vuelva a firmar el tramo pasaría la verificación, igual que podría reescribir `audit.verifications`. La defensa frente a ese actor es la copia externa firmada (manifiestos de respaldo con minisign, Sprint 5); como mejora futura, candidato a EP-26: guardar la huella de la clave pública en cada verificación.

## Cómo se verifica

- `api/tests/core/test_chain_hash_vector.py` fija el hash de la fila de ejemplo que este ADR reutiliza (la serialización es la de ADR-004).
- `api/tests/core/test_signature_payload_vector.py` reconstruye el payload del bloque `signature-payload-vector` y lo compara byte a byte con `signature_payload`; `api/tests/core/test_audit_sign_pure.py` fija la construcción del payload, `needs_signature` e `is_signature_late`; `api/tests/audit/test_sign_latest.py` prueba `sign_latest` y la verificación incremental del tramo sin firmar (H-1) con la base real.
- `api/tests/audit/test_verify_signatures.py` prueba la verificación de TODAS las firmas con la clave pública guardada: cadena sana, firma alterada o ilegible, cadena reescrita con los hashes recalculados, firma borrada (anti-retroceso) sin llamadas al proveedor, llaves `decrypt_only` y `retired`, custodio sellado, 365 firmas mixtas `local` y `openbao`, `public_key` alterada y `payload_version`; `api/tests/audit/test_router_signatures.py` fija `GET /audit/signatures/latest` y los campos de firmas de la verificación.
- `api/tests/architecture/test_adr_docs.py` comprueba el formato de este documento. Las pruebas de la verificación de firmas y del job llegan con los slices S6-A2 y S6-A3 y se citan aquí cuando existan.
- Cambiar cualquier decisión de este documento exige detenerse y preguntar.
