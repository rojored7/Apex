# US-025 · Como equipo quiero cifrar y descifrar campos con AES-256-GCM en un blob autodescriptivo para que ningún dato personal quede en claro en la base

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/bus.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `encrypt(data_class, plaintext, aad)` y `decrypt(blob, aad)` en el bus, con DEK por clase de dato abierta en memoria al arrancar
para que los módulos cifren sin elegir llave ni algoritmo y el algoritmo viaje en el dato

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (DEK `purpose = encrypt` por `data_class`).
- **Reglas que aplica:** RN-13; `CLAUDE.md` bus puntos 1 a 4 (única puerta, el que llama no elige llave, envelope, formato `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`, `alg = A256GCM`, `aad = id del registro`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.format_blob(key_id, alg, nonce, ct) -> str` y `crypto.parse_blob(blob) -> BlobParts` (formato, sin primitivas)

## Alcance

- **Backend:** `CryptoBus` con `encrypt` y `decrypt`. Al arrancar, por cada `data_class` registrada sin llave `active` crea una DEK de 32 bytes, la envuelve con `KeyProvider.wrap` y la guarda en `crypto_keys`; luego desenvuelve todas las llaves `active` y `decrypt_only` y las mantiene en memoria. `encrypt` usa la llave `active` de la clase y nonce aleatorio de 12 bytes. `decrypt` toma `key_id` del blob, así descifra con llaves `decrypt_only` también. Registro de clases de dato de v0.1: `member.document`, `member.phone`, `member.email`, `member.birth_date`, `member.emergency_contact`.
- **Front:** No aplica

## Criterios de aceptación

1. `decrypt(encrypt(dc, p, aad), aad) == p` para las cinco clases de dato de v0.1.
2. El blob tiene exactamente cinco partes separadas por punto: `apx1`, `key_id` (UUID de `crypto_keys`), `A256GCM`, nonce y ciphertext en base64url sin relleno.
3. Dos cifrados del mismo texto producen blobs distintos (nonce aleatorio).
4. Un blob descifrado con un `aad` distinto (otro id de registro) falla con `CryptoError`.
5. Un blob con prefijo distinto de `apx1`, con un `alg` desconocido o con el ciphertext alterado falla con `CryptoError`, nunca devuelve datos.
6. Llamar `encrypt` con una `data_class` no registrada falla con `CryptoError("data_class desconocida")`.
7. Al arrancar con una base sin llaves, se crea una DEK `active` por clase de dato; al arrancar de nuevo no se crea ninguna adicional.
8. El valor de `crypto_keys.wrapped_material` nunca es igual a la DEK en claro.
9. El bus no expone ningún método que devuelva una DEK, ni la imprime en logs.
10. Cada `encrypt` y `decrypt` deja registro en `crypto_ops` (implementación del registro en US-029).

## Escenarios BDD

```gherkin
# language: es
Característica: Cifrado de campos por clase de dato

  Antecedentes:
    Dado un bus inicializado con el proveedor local
    Y la clase de dato "member.document" registrada

  Escenario: Ida y vuelta
    Cuando el módulo de socios cifra "1020304" con aad igual al id del socio
    Entonces el resultado empieza con "apx1." y contiene "A256GCM"
    Y al descifrarlo con el mismo aad obtiene "1020304"

  Escenario: Blob copiado a otro registro
    Dado un documento cifrado para el socio A
    Cuando se intenta descifrar con el id del socio B como aad
    Entonces el bus lanza CryptoError

  Escenario: Clase de dato desconocida
    Cuando un módulo pide cifrar con la clase "member.foo"
    Entonces el bus lanza CryptoError "data_class desconocida"

  Escenario: Llaves creadas una sola vez
    Dado una base sin llaves
    Cuando el API arranca dos veces
    Entonces existe exactamente una llave active de purpose "encrypt" por cada clase de dato de v0.1
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (usa las tablas de US-024).
- **Trigger / restricciones:** las de US-024.
- **Funciones puras a probar:** `format_blob`/`parse_blob` con blob válido, con 4 y 6 partes, con base64url inválido.
- **Pruebas:** ida y vuelta por clase, AAD, alteración, arranque idempotente con base real, prueba de que `wrapped_material != dek`.
- **Archivos principales:** `api/src/app/core/crypto/bus.py`, `api/src/app/core/crypto/registry.py`, `api/tests/crypto/test_bus_encrypt.py`.
- **Riesgo irreversible:** el formato del blob es un contrato con los datos. Cambiarlo cuando ya hay datos cifrados es irreversible; `CLAUDE.md` exige detenerse y preguntar antes. Se fija en ADR-002 (US-119).

## Supuestos

- Supuesto: el registro de clases de dato es una constante en `core/crypto/registry.py` (no tabla); agregar una clase nueva es un cambio de código revisado.

## Dependencias

- US-023 · KeyProvider y proveedor local
- US-024 · Tablas crypto_keys, crypto_ops, crypto_jobs

## INVEST

- **Independiente:** solo proveedor y tablas.
- **Negociable:** dónde vive el registro de clases.
- **Valiosa:** es el cifrado en reposo de RN-13.
- **Estimable:** dos operaciones con primitivas conocidas.
- **Pequeña:** un servicio y su arranque.
- **Testeable:** ida y vuelta, AAD y alteración binarios.

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
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
