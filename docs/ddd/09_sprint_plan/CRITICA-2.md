# Crítica del plan de sprints (plan-critic, iteración 2)

Fecha: 21 de octubre de 2026. Verifica la reescritura del plan contra `CRITICA.md`.

## Veredicto: APROBADO CON OBSERVACIONES

Los tres bloqueantes quedan resueltos en lo esencial; B-3 queda parcial por un problema de orden dentro del Sprint 0. La reescritura introdujo tres inversiones de orden nuevas (N-1 a N-3) y dos medias (N-4, N-5), todas de pocas líneas. Con ellas corregidas el plan queda aprobado sin reservas.

## Estado de cada hallazgo de la primera crítica

- B-1 rojo y verde por slice: RESUELTO (`README.md` 51 a 57 y 167 a 177; 215 a 222; todos los sprints usan Rojo / Verde / Gate con archivos del Rojo).
- B-2 mapeo y notación: RESUELTO (`README.md` 224 a 244; sin `web/features` ni `core/main` en ningún sprint).
- B-3 imagen sin `uv` ni `migrations`: PARCIAL (contenido corregido en `SPRINT-00.md` 171 a 185 y demos sin `uv run`; queda el orden N-2).
- A-1 llave JWT: RESUELTO (`SPRINT-01.md` 27 a 33, 141, 149).
- A-2 rama y push: RESUELTO (`README.md` 253 a 260 y 205; `SPRINT-00.md` 6, 40, 48).
- A-3: RESUELTO (`SPRINT-00.md` 191 y 216).
- A-4 línea base: PARCIAL (S0-W0-0 existe en `SPRINT-00.md` 109 a 122; `WEB_PORT` tiene el problema N-4).
- A-5: RESUELTO (`README.md` 216 a 218).
- A-6: RESUELTO (`SPRINT-02.md` 148, `SPRINT-03.md` 197, `SPRINT-01.md` 299 a 305).
- M-1 a M-8: RESUELTOS. M-8 recalculado: 4A y 4B suman 23 historias, 83 puntos y 389 h; `0012` (S4A-B1) antes de `0013` (S4A-B3); 4B no migra; dependencias de 4B satisfechas; el cuadre US-109/US-111 queda diferido en 4A y lo cierra 4B.
- Bajas: RESUELTAS (`SPRINT-00.md` 62 y 156; `SPRINT-01.md` 69 y 90; `SPRINT-03.md` 122).

## Hallazgos nuevos

### Altos (inversiones de orden que impiden pasar el gate del slice)
- **N-1.** S0-W0-3 depende de una base que nace en S0-W0-4: el gate `slice-gate.sh architecture tests/test_ci_database.py` exige `TEST_DATABASE_URL` (`SPRINT-00.md` 156 y 162), pero `db_test` se crea en `compose.dev.yml` en W0-4 (181 a 185). Corrección: mover `test_ci_database.py` al gate de S0-W0-4.
- **N-2.** S0-W0-4 copia y prueba `alembic.ini` y `migrations/` (`SPRINT-00.md` 171 a 175, gate `test_api_image.sh` en 190) que crea US-012 en S0-B2 (238). Corrección: W0-4 crea un `alembic.ini` y un `migrations/env.py` mínimos (sin versiones) que US-012 completa; `alembic heads` devuelve vacío con código 0.
- **N-3.** S4A-W0-1 quita el perfil `worker` (`SPRINT-04A.md` 82 a 87) antes de que exista `app/worker/main.py` (S4A-B1, 91 a 99); el contenedor entraría en bucle de reinicios. Corrección: dejar el perfil hasta cerrar S4A-B1 y mover el smoke y el healthcheck a después de B1.

### Medios
- **N-4.** `${WEB_PORT:-80}` en Compose no lee el `.env` de la raíz: Compose interpola desde `infra/` (US-005 113). Corrección: `--env-file .env` en la convención de comandos.
- **N-5.** Los volcados `docs/scratch/*.dump` entrarían al repositorio con `git add -A`. Corrección: `*.dump` en `.gitignore`.

### Observaciones (no bloquean)
- **O-1.** `npx tsc --noEmit <archivos>` ignora `tsconfig.json`. Usar un `tsconfig.slice.json` temporal con `include`, o el proyecto completo (con stubs pasa).
- **O-2.** Ruta de la prueba de imagen: `scripts/ci/test_api_image.sh` (`SPRINT-00.md` 168) frente a `scripts/ci/tests/test_api_image.sh` (US-005). Unificar.
- **O-3.** El `pg_dump` de S1-B1 es sobre una base casi vacía; inocuo. El que importa es el de `0011`.

## Qué hacer antes de ejecutar
1. Corregir N-1 y N-2 antes del Sprint 0; N-3 antes del Sprint 4A.
2. Resolver N-4 (convención de comandos) y N-5 (`.gitignore`).
3. Aplicar O-1 y O-2 al redactar US-008 y US-005.
