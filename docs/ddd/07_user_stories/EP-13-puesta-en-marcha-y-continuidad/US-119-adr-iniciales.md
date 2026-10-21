# US-119 · Como equipo quiero los ADR iniciales de monolito modular, bus de criptografía y pagos inmutables para que las decisiones irreversibles queden escritas y nadie las cambie sin saberlo

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno; `docs/adr/`
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `ADR-001-monolito-modular.md`, `ADR-002-bus-de-criptografia.md` y `ADR-003-pagos-inmutables.md` en `docs/adr/`
para que el contexto, la decisión y las consecuencias de lo que no se negocia queden registrados y verificables

## Contexto de dominio

- **Aggregate / entidades:** Payment (ADR-003), CryptoKey y formato del blob (ADR-002).
- **Reglas que aplica:** RN-02, RN-13, RN-16; `04_architecture_decision.md` (ADR-001 se genera desde sus secciones 1 a 8); `CLAUDE.md` "El bus de criptografía"; riesgo de EP-01 (la serialización canónica de la auditoría es irreversible y se documenta en el ADR).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** tres documentos con formato fijo (Estado, Contexto, Decisión, Alternativas descartadas, Consecuencias, Cómo se verifica). ADR-001 resume `04_architecture_decision.md`. ADR-002 fija el formato del blob `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`, AAD = id del registro, normalización del índice ciego y la regla `banned-api`. ADR-003 fija el trigger de inmutabilidad y la anulación con motivo. Se incluye además la serialización canónica de la cadena de auditoría (en ADR-002 o un ADR-004 si el equipo prefiere separarla). Cada "Cómo se verifica" apunta a la prueba que lo hace cumplir.
- **Front:** No aplica.

## Criterios de aceptación

1. Existen los tres archivos en `docs/adr/` con las seis secciones nombradas.
2. ADR-002 contiene el formato exacto del blob, la regla de AAD, la función `normalize_for_index` (minúsculas, sin espacios ni puntos) y la lista de imports prohibidos.
3. ADR-003 describe qué columnas puede actualizar el trigger (`voided`, `void_reason`, `voided_by`, `voided_at`), que la anulación es una sola vez y que `DELETE` está prohibido.
4. La serialización canónica usada por `audit.chain_hash` queda escrita con un ejemplo de entrada y su hash esperado.
5. Cada sección "Cómo se verifica" nombra al menos un archivo de prueba existente (por ejemplo `tests/architecture/test_banned_imports.py`, la prueba del trigger de pagos).
6. Cada ADR declara que cambiar la decisión exige detenerse y preguntar (`CLAUDE.md`).

## Escenarios BDD

```gherkin
# language: es
Característica: ADR iniciales

  Escenario: ADR completos
    Dado el directorio "docs/adr"
    Cuando reviso "ADR-001", "ADR-002" y "ADR-003"
    Entonces cada uno tiene Estado, Contexto, Decisión, Alternativas descartadas, Consecuencias y Cómo se verifica

  Escenario: Verificación enlazada a pruebas reales
    Dado el ADR-003
    Cuando busco el archivo de prueba nombrado en "Cómo se verifica"
    Entonces el archivo existe en "api/tests"

  Escenario: ADR incompleto bloquea el PR
    Dado un ADR sin la sección "Consecuencias"
    Cuando corre la revisión del PR
    Entonces el revisor rechaza el PR
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** el ejemplo de hash de la serialización canónica se agrega como prueba unitaria de `audit.chain_hash`.
- **Pruebas:** prueba unitaria del ejemplo de hash; revisión manual del PR.
- **Archivos principales:** `docs/adr/ADR-001-monolito-modular.md`, `docs/adr/ADR-002-bus-de-criptografia.md`, `docs/adr/ADR-003-pagos-inmutables.md`.

## Supuestos

- Supuesto: la serialización canónica de la auditoría se documenta dentro de ADR-002 salvo que el equipo cree ADR-004; EP-13 solo nombra tres ADR.

## Dependencias

- US-016 · Hook de auditoría after_flush (serialización canónica).
- US-025 · Cifrado AES-GCM y formato de blob.
- US-096 · Inmutabilidad de pagos en la base.

## INVEST

- **Independiente:** documenta lo ya construido.
- **Negociable:** estructura de secciones ajustable.
- **Valiosa:** protege decisiones irreversibles.
- **Estimable:** tres documentos.
- **Pequeña:** cabe en un par de días.
- **Testeable:** secciones y pruebas enlazadas verificables.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] Prueba del ejemplo de hash en verde
- [ ] Revisión de PR aprobada
