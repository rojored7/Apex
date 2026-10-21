# US-105 · Como administrador quiero verificar la cadena de auditoría desde la línea de comandos para comprobar la integridad sin entrar al sistema web

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`), comando en `cli.py`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero correr `cli verify-audit` en el servidor
para comprobar la integridad de la auditoría aunque el front no esté disponible, o desde un script de mantenimiento

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`.
- **Reglas que aplica:** RN-16, regla de datos 8 (comandos de mantenimiento en `cli.py`, auditados).
- **Eventos que emite:** ninguno (escribe una entrada `verify`).
- **Eventos que consume:** ninguno.
- **Funciones puras:** `core.audit.verify_chain(rows_iter)` (compartida con US-104).

## Alcance

- **Backend:** comando `uv run python -m app.cli verify-audit` (typer) que recorre la cadena completa con `verify_chain`, imprime el resultado y registra la entrada `verify` con `user_id` = `SYSTEM_USER_ID` (o el de `--as <email>`, N-15) y origen `cli`.
- **Front:** No aplica.

## Criterios de aceptación

1. `verify-audit` con la cadena íntegra imprime "Cadena íntegra: N filas verificadas" y sale con código 0.
2. Con una fila alterada imprime "Cadena rota en el registro seq X" y sale con código 1.
3. Si la base no está disponible imprime el error y sale con código 2.
4. Cada ejecución deja una entrada de auditoría `action = "verify"` con `user_id` = `SYSTEM_USER_ID` (o el de `--as`) y `after.source = "cli"`.
5. El comando siempre recorre la cadena completa (no tiene modo en segundo plano) y la recorre por lotes sin cargar toda la tabla en memoria.
6. El comando no imprime ningún valor de `before` ni `after`.

## Escenarios BDD

```gherkin
# language: es
Característica: Verificar la cadena desde la línea de comandos

  Escenario: Cadena íntegra
    Dado una cadena de auditoría sin alterar
    Cuando ejecuto "cli verify-audit"
    Entonces la salida dice "Cadena íntegra"
    Y el código de salida es 0
    Y se registra una entrada "verify" con origen "cli"

  Escenario: Cadena rota
    Dado una cadena donde la fila con "seq" 42 fue alterada a mano
    Cuando ejecuto "cli verify-audit"
    Entonces la salida dice "Cadena rota en el registro seq 42"
    Y el código de salida es 1

  Escenario: Base no disponible
    Dado que la base de datos no responde
    Cuando ejecuto "cli verify-audit"
    Entonces el código de salida es 2
```

## Endpoints

- Ninguno. Comando: `cli verify-audit [--as <email>]`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** reutiliza las pruebas de `verify_chain`.
- **Pruebas:** prueba del comando con `typer.testing.CliRunner` contra PostgreSQL de prueba (códigos 0, 1, 2).
- **Archivos principales:** `api/src/app/cli.py`, `api/src/app/core/audit.py`.

## Supuestos

- Supuesto: la función `core.audit.verify_chain` vive en `core/audit.py`; la crea la primera de US-104 o US-105 que se implemente y la otra la reutiliza.
- Supuesto: la entrada `verify` del CLI lleva `user_id` = `SYSTEM_USER_ID`, o el usuario de `--as <email>` si se pasa (N-15).

## Dependencias

- US-015 · Tabla de auditoría y cadena de hashes.

## INVEST

- **Independiente:** solo necesita la cadena y `chain_hash`.
- **Negociable:** formato de la salida.
- **Valiosa:** verificación sin depender del front.
- **Estimable:** un comando.
- **Pequeña:** un día.
- **Testeable:** códigos de salida probados.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz y error (rol no aplica: comando en el servidor)
- [x] Endpoints y roles definidos (no hay)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas del comando con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Auditoría verificada (entrada `verify`)
- [ ] Revisión de PR aprobada
