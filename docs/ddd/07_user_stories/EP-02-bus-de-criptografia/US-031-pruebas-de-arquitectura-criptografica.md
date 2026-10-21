# US-031 · Como equipo quiero pruebas de arquitectura que fallen si un módulo usa primitivas criptográficas fuera del bus o si un dato sensible queda en claro en la base

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`api/tests/architecture/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `test_banned_imports.py` y una prueba de "sin claro en base" que corran en CI
para que nadie se salte el bus por descuido y que la promesa de RN-13 sea verificable en cada PR

## Contexto de dominio

- **Aggregate / entidades:** ninguno propio; protege los value objects cifrados de `Member`.
- **Reglas que aplica:** RN-13; `CLAUDE.md` bus punto 8 (fuera de `core/crypto` y `core/security` prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`); `05_service_design.md` sección 6 (blob nunca en claro).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `test_banned_imports.py` recorre el AST de todos los `.py` de `src/app` y falla si un archivo fuera de `core/crypto/` o `core/security/` importa (directo o `from`) uno de los seis módulos, incluido `importlib.import_module("hashlib")` literal. Complementa la regla `banned-api` de ruff (US-002). Prueba "sin claro": crea registros con valores conocidos en todas las columnas `Encrypted` registradas y verifica con SQL crudo que ninguna columna de la fila contiene el valor en claro ni su forma normalizada.
- **Front:** No aplica

## Criterios de aceptación

1. Agregar `import hashlib` en `api/src/app/modules/members/service.py` hace fallar `test_banned_imports.py` con el nombre del archivo y la línea.
2. `from cryptography.hazmat... import ...` en un módulo fuera del bus falla la prueba.
3. Los mismos imports dentro de `core/crypto/` o `core/security/` no hacen fallar la prueba.
4. La prueba "sin claro" recorre automáticamente todas las columnas declaradas con `Encrypted` (no una lista escrita a mano) y falla si alguna fila contiene el valor en claro o normalizado.
5. Ambas pruebas corren en el job de pytest de CI (US-003) y bloquean el merge.

## Escenarios BDD

```gherkin
# language: es
Característica: Pruebas de arquitectura criptográfica

  Escenario: Código limpio
    Dado que solo core/crypto y core/security importan primitivas
    Cuando corre la suite de arquitectura
    Entonces las pruebas pasan

  Escenario: Import prohibido en un módulo
    Dado que modules/members/service.py importa hashlib
    Cuando corre la suite de arquitectura
    Entonces test_banned_imports falla indicando el archivo y la línea

  Escenario: Dato en claro en la base
    Dado una columna sensible declarada como texto normal por error
    Cuando corre la prueba "sin claro en base"
    Entonces la prueba falla indicando la tabla y la columna
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** el analizador de imports con fixtures de código.
- **Pruebas:** arquitectura (AST) y de integración con base.
- **Archivos principales:** `api/tests/architecture/test_banned_imports.py`, `api/tests/architecture/test_no_plaintext_at_rest.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-028 · Tipos de columna Encrypted y BlindIndexed

## INVEST

- **Independiente:** solo necesita los tipos.
- **Negociable:** alcance del análisis (dinámico o solo estático).
- **Valiosa:** convierte una regla escrita en una regla dura.
- **Estimable:** dos pruebas.
- **Pequeña:** un día.
- **Testeable:** un PR de control debe fallar.

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
