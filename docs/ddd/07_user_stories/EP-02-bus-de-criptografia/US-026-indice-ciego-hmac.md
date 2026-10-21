# US-026 · Como equipo quiero un índice ciego HMAC-SHA-256 sobre el valor normalizado para buscar socios por documento, teléfono o correo sin descifrar la tabla

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/bus.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `blind_index(data_class, value)` con una llave HMAC propia por clase de dato y `normalize_for_index` como función pura
para que recepción encuentre a un socio por "1.020.304" o "1020304" en un segundo sin que la base conozca el valor

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (`purpose = index`, `algorithm = HMAC-SHA256`).
- **Reglas que aplica:** RN-13 (búsqueda por índice ciego); `CLAUDE.md` bus punto 5 (minúsculas, sin espacios ni puntos; columna `<campo>_idx`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.normalize_for_index(value) -> str`

## Alcance

- **Backend:** `normalize_for_index`: minúsculas, elimina todo espacio en blanco (incluye tabuladores y espacios no separables) y todos los puntos. `blind_index` usa la llave `index` activa de la clase y devuelve HMAC-SHA-256 en hexadecimal. Al arrancar se crea una llave `index` por cada clase con índice (`member.document`, `member.phone`, `member.email`) si no existe.
- **Front:** No aplica

## Criterios de aceptación

1. `normalize_for_index(" 1.020.304 ") == "1020304"`, `normalize_for_index("Ana.Perez@Mail.com") == "anaperez@mailcom"` y `normalize_for_index("300 123 4567") == "3001234567"`.
2. `"1.020.304"`, `"1020304"` y `" 1020304 "` producen el mismo índice para `member.document`.
3. El mismo valor en dos clases distintas (`member.document` y `member.phone`) produce índices distintos (llaves propias).
4. El índice es determinista: dos llamadas con el mismo valor devuelven el mismo resultado.
5. `blind_index` sobre una clase sin índice (`member.birth_date`) falla con `CryptoError`.
6. Un valor que queda vacío tras normalizar falla con `CryptoError("valor vacío")`.
7. La llave HMAC está envuelta en `crypto_keys` y nunca se persiste en claro.
8. Cada cálculo de índice cuenta en `crypto_ops` con verbo `index` (registro agregado por lote en búsquedas, US-029).

## Escenarios BDD

```gherkin
# language: es
Característica: Índice ciego para búsqueda

  Escenario: Documento con puntos y espacios
    Dado un socio guardado con documento "1020304"
    Cuando recepción busca "1.020.304"
    Entonces el índice calculado coincide con el guardado en document_idx

  Escenario: Clases de dato separadas
    Cuando se calcula el índice de "3001234567" como documento y como teléfono
    Entonces los dos índices son distintos

  Escenario: Clase sin índice
    Cuando se pide el índice de "1990-05-01" para "member.birth_date"
    Entonces el bus lanza CryptoError

  Escenario: Valor vacío tras normalizar
    Cuando se pide el índice de " . . " para "member.document"
    Entonces el bus lanza CryptoError "valor vacío"
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `normalize_for_index` con casos de puntos, espacios, tabulador, mayúsculas, tildes (se conservan) y cadena vacía.
- **Pruebas:** unitarias puras parametrizadas; integración con base para la creación de llaves `index`.
- **Archivos principales:** `api/src/app/core/crypto/bus.py`, `api/src/app/core/crypto/normalize.py`, `api/tests/crypto/test_blind_index.py`.
- **Riesgo irreversible:** la normalización es irreversible una vez haya índices guardados: cambiarla exige recalcular todos los `_idx` y puede ocultar duplicados. `CLAUDE.md` exige detenerse y preguntar antes de cambiarla; se fija en ADR-002.

## Supuestos

- Supuesto: la normalización no quita tildes ni guiones (el documento solo nombra minúsculas, espacios y puntos); "1020-304" y "1020304" producen índices distintos.

## Dependencias

- US-023 · KeyProvider y proveedor local
- US-024 · Tablas crypto_keys, crypto_ops, crypto_jobs

## INVEST

- **Independiente:** no requiere los tipos de columna.
- **Negociable:** caracteres adicionales a eliminar (con la advertencia de irreversibilidad).
- **Valiosa:** búsqueda rápida sin descifrar.
- **Estimable:** una función pura y una primitiva.
- **Pequeña:** menos de un día de trabajo más pruebas.
- **Testeable:** casos de normalización exactos.

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
