# US-027 · Como equipo quiero firmar y verificar datos por clase de dato a través del bus para que auditoría y backups usen firmas sin conocer la llave ni el algoritmo

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/bus.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `sign(data_class, data)` y `verify(data_class, data, signature)` en el bus, delegando en `KeyProvider.sign`/`verify`
para que la firma de auditoría (v0.3) y de backups (v1.0) cambien de algoritmo sin tocar a quien firma

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (`purpose = sign`).
- **Reglas que aplica:** `CLAUDE.md` bus punto 1 (única puerta); Q27 (el algoritmo lo decide la llave registrada; firmas viejas verifican con su llave).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `sign` devuelve una firma textual `apx1.<key_id>.<alg>.<sig_b64url>`; `verify` toma `key_id` de la firma y verifica con esa llave aunque esté `decrypt_only`. En v0.1 el algoritmo es `Ed25519` con el `LocalFileProvider`. Clases de firma registradas en v0.1: ninguna de negocio; se registra una clase de prueba solo en tests. `audit.signature` y `backup.signature` se registran en sus versiones.
- **Front:** No aplica

## Criterios de aceptación

1. `verify(dc, data, sign(dc, data))` es `True`.
2. `verify` con los datos alterados en un byte es `False` (no lanza excepción).
3. `verify` con una firma de formato inválido lanza `CryptoError`.
4. Una firma hecha con una llave que luego pasa a `decrypt_only` sigue verificando.
5. `sign` con una clase sin llave de propósito `sign` falla con `CryptoError`.
6. Cada `sign` y `verify` deja fila en `crypto_ops` con el verbo correspondiente (US-029).
7. La llave privada de firma nunca sale del proveedor (el bus no tiene método que la exponga).

## Escenarios BDD

```gherkin
# language: es
Característica: Firma por el bus

  Antecedentes:
    Dado una clase de firma de prueba registrada con algoritmo Ed25519

  Escenario: Firmar y verificar
    Cuando se firma "hash-de-la-cadena"
    Entonces la verificación de esos mismos datos es verdadera

  Escenario: Datos alterados
    Dado una firma de "hash-de-la-cadena"
    Cuando se verifica contra "hash-de-la-cadenA"
    Entonces la verificación es falsa

  Escenario: Firma con formato inválido
    Cuando se verifica una firma "abc"
    Entonces el bus lanza CryptoError
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** formato de la firma (parseo).
- **Pruebas:** unitarias con proveedor local en directorio temporal.
- **Archivos principales:** `api/src/app/core/crypto/bus.py`, `api/tests/crypto/test_sign.py`.

## Supuestos

- Supuesto: la firma devuelta por el bus usa el mismo prefijo `apx1` y estructura de partes que el blob de cifrado, para que el algoritmo vaya en el dato (no está fijado en los documentos).

## Dependencias

- US-023 · KeyProvider y proveedor local

## INVEST

- **Independiente:** solo el proveedor.
- **Negociable:** formato textual de la firma.
- **Valiosa:** base de la auditoría firmada y de backups firmados.
- **Estimable:** dos métodos delegados.
- **Pequeña:** un día.
- **Testeable:** verdadero/falso exactos.

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
