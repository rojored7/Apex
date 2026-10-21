# US-008 · Como equipo quiero los cuatro scripts de gate del flujo en `scripts/workflow/` para que cada slice, checkpoint y cierre de wave se verifique automáticamente y no a mano

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`scripts/workflow/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh` y `validate-impact-analysis.sh`
para que los gates del flujo de trabajo dejen de verificarse manualmente y devuelvan un código distinto de 0 cuando fallan

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `05_service_design.md` sección 7; `00b_impact_analysis.md` ("Gate verificado manualmente"); umbral de cobertura de 80 %.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** scripts POSIX (`#!/usr/bin/env bash`, `set -euo pipefail`):
  - `slice-gate.sh <modulo>`: `ruff check`, `ruff format --check` y `mypy` sobre `src/app/modules/<modulo>` (o `core/<x>`) y `pytest tests/<modulo>`.
  - `checkpoint-commit.sh "<mensaje>"`: verifica que `slice-gate` pasó, hace `git add -A` y commit `chore(checkpoint): <mensaje>` sin push; se niega a correr sobre `main`.
  - `run-gates.sh`: suite completa de api (ruff, mypy, pytest con cobertura y umbral 80 %) y de web si existe (lint, test, build).
  - `validate-impact-analysis.sh <archivo>`: verifica que el archivo de análisis de impacto existe y contiene una línea `Veredicto:` con `APROBADO` o `APROBADO CON OBSERVACIONES`.
- **Front:** No aplica.

## Criterios de aceptación

1. Los cuatro scripts existen, tienen permiso de ejecución en git (`git ls-files -s` muestra modo 100755) y muestran ayuda con `-h`.
2. `slice-gate.sh members` termina con código distinto de 0 si ruff, mypy o pytest fallan en ese módulo, y con 0 si todo pasa.
3. `checkpoint-commit.sh` termina con error y no crea commit si la rama actual es `main` o si el gate falla; nunca ejecuta `git push`.
4. `run-gates.sh` falla si la cobertura de `src/` baja de 80 %.
5. `validate-impact-analysis.sh` falla si el archivo no existe o no tiene un veredicto aprobado.
6. Los scripts corren en Git Bash (Windows) y en Linux.

## Escenarios BDD

```gherkin
# language: es
Característica: Gates automáticos del flujo

  Escenario: Slice en verde
    Dado un módulo sin errores de lint, tipos ni pruebas
    Cuando ejecuto "scripts/workflow/slice-gate.sh members"
    Entonces el script termina con código 0

  Escenario: Checkpoint sobre main rechazado
    Dado que estoy en la rama "main"
    Cuando ejecuto "scripts/workflow/checkpoint-commit.sh 'avance'"
    Entonces el script termina con código distinto de 0
    Y no se crea ningún commit

  Escenario: Análisis de impacto sin veredicto
    Dado un archivo de análisis de impacto sin línea "Veredicto:"
    Cuando ejecuto "validate-impact-analysis.sh" sobre ese archivo
    Entonces el script termina con código distinto de 0
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** `scripts/workflow/tests/` con casos de éxito y falla (bats o scripts de prueba simples) ejecutados en CI.
- **Archivos principales:** `scripts/workflow/slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh`, `validate-impact-analysis.sh`.

## Supuestos

- Supuesto: el formato de la línea de veredicto es `Veredicto: APROBADO` (o `APROBADO CON OBSERVACIONES`), igual al que devuelve el agente plan-critic; si el gate prefiere otro formato se ajusta el patrón.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest (las herramientas que invocan).

## INVEST

- **Independiente:** no depende de código de negocio.
- **Negociable:** nombres de parámetros y salida.
- **Valiosa:** convierte el proceso del flujo en verificación automática.
- **Estimable:** cuatro scripts cortos.
- **Pequeña:** dos días.
- **Testeable:** códigos de salida.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] Pruebas de los scripts en verde en CI
- [ ] Probados en Git Bash y Linux
- [ ] Revisión de PR aprobada
