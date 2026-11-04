# ADR-004 · Serialización canónica de la auditoría

## Estado

Aceptado. Vigente desde el Sprint 1 (cadena de hashes de `audit.audit_log`). Es irreversible con datos reales: cambiar un solo byte de la serialización invalida toda la cadena ya escrita. Cambiarla exige detenerse y preguntar.

## Contexto

`audit.audit_log` es una cadena: cada fila guarda `prev_hash` y su propio `hash`, y quien verifica (`POST /audit/verify`, `verify-audit`, el job de verificación) recalcula la cadena entera. Para que el recálculo coincida años después, en otra máquina y con otra versión de Python, la fila debe convertirse a bytes siempre igual. Un JSON "normal" no lo garantiza: el orden de las claves, los espacios, la forma de escribir una fecha o un UUID y la normalización Unicode cambian entre implementaciones.

## Decisión

`hash = SHA-256( prev_hash_ascii || canonical(fila) )`, en hexadecimal minúscula de 64 caracteres. La primera fila usa `prev_hash = ZERO_HASH` (64 ceros). `canonical` (`core/audit.py`) escribe la fila así:

- Entran las claves de `HASHED_KEYS`: `id`, `seq`, `at`, `user_id`, `action`, `table_name`, `record_id`, `before`, `after`; y `subject_member_id` solo cuando no es nulo.
- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` codificado en UTF-8.
- `datetime`: exige zona, pasa a UTC y se escribe `YYYY-MM-DDTHH:MM:SS.ffffffZ`, siempre con 6 decimales. Un `datetime` sin zona lanza `CanonicalError`.
- `date`: `YYYY-MM-DD`. `UUID`: texto en minúscula con guiones. `None`: `null`. `bool`, `int` y `str` quedan tal cual, sin normalizar Unicode. `Enum`: su `.value`. `dict` y `list` se recorren de forma recursiva con las claves como `str`.
- `float`, `Decimal`, `bytes` y cualquier otro tipo lanzan `CanonicalError`: la auditoría no guarda valores sin representación única.
- Los campos cifrados entran como el blob `apx1.` ya cifrado, nunca en claro (ADR-002).

Vector de referencia (fila de ejemplo sin datos personales; el `hash` lo calcula `core.audit.chain_hash` y una prueba lo vuelve a calcular en cada corrida):

```chain-hash-vector
{
  "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "row": {
    "id": "00000000-0000-4000-8000-000000000001",
    "seq": 1,
    "at": "2026-01-15T14:30:00.000000Z",
    "user_id": "00000000-0000-0000-0000-000000000001",
    "action": "insert",
    "table_name": "plans.plans",
    "record_id": "00000000-0000-4000-8000-0000000000a1",
    "before": null,
    "after": {
      "name": "Plan de ejemplo",
      "price_cop": 150000
    }
  },
  "hash": "097f1f232644029a217ea42c6e1e9c4871e508c30340a9369ce2a796a032f441"
}
```

## Alternativas descartadas

- **JSON canónico RFC 8785 (JCS):** resuelve números de coma flotante, que la auditoría no admite; añade una dependencia y reglas de escape que no necesitamos.
- **Serialización de la base (`row_to_json`, `jsonb::text`):** depende de la versión de PostgreSQL y de la configuración de zona horaria; imposible de recalcular fuera de la base.
- **Hash por columna (Merkle):** permite verificar campos sueltos, pero complica la cadena sin que exista el caso de uso.
- **`pickle` o `repr`:** dependen de la versión de Python.

## Consecuencias

- Cualquier cambio de `canonical`, de `HASHED_KEYS` o de la forma de los instantes rompe la verificación de todo lo ya escrito. No se corrige con una migración: exigiría una cadena nueva con un corte firmado y documentado.
- Agregar una clave nueva a la cadena no es retrocompatible; `subject_member_id` entró solo cuando no es nulo para no alterar las filas anteriores.
- Los números reales no pueden auditarse; el dinero va en enteros (COP sin decimales) y los demás valores como texto.
- Quien implemente un verificador externo puede hacerlo con el vector de arriba.

## Cómo se verifica

- `api/tests/core/test_chain_hash_vector.py` lee el bloque `chain-hash-vector` de este documento y exige `chain_hash(ZERO_HASH, fila) == hash`.
- `api/tests/core/test_audit_serialize.py` fija cada regla de `canonical`; `api/tests/core/test_audit_chain.py` fija el recorrido y las rupturas de la cadena.
- `api/tests/audit/test_verify.py` prueba la verificación por el service sobre cadenas rotas y sanas.
- Cambiar la serialización exige detenerse y preguntar antes de tocar `core/audit.py`.
