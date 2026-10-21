# US-001 · Repositorio git y estructura — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-001-repositorio-git-y-estructura.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`./`, `api/`, `web/`, `infra/`, `docs/adr/`, `scripts/workflow/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La historia no toca dominio ni contrato. Todo lo que pide es configuración conocida de git y de GitHub. El único supuesto (remoto privado en GitHub) ya está confirmado en el terreno: existe `.git` con `origin` en `https://github.com/rojored7/Apex.git`, rama `main` sin commits y un `.gitignore` en la raíz. El riesgo de plan de GitHub para la protección de rama se anota en Riesgos.

## Resumen

Dejar el repositorio con un primer commit Conventional Commits en `main`, las cinco carpetas de `CLAUDE.md` versionadas, un `.gitignore` que nunca deje entrar `.env` ni llaves, la convención de ramas documentada y la regla de protección de `main` activa en el remoto (PR obligatorio, sin push directo ni force push). Como `git init`, el remoto y el `.gitignore` ya existen, el trabajo es verificar, completar y proteger, no crear desde cero.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Ajuste por el estado real del terreno (no por DECISIONES): `git init` y el remoto ya existen; la tarea pasa de "inicializar" a "verificar y completar". El `.gitignore` actual ya cubre `.env`, `.env.*` con `!.env.example`, `*.pem`, `*.key`, `keys/`, `node_modules/`, `.venv/`, `web/dist/` y `__pycache__/`.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos involucrados.
- Confirmado: la historia no introduce reglas de negocio.

## Validación contra la arquitectura

- Estructura de carpetas: coincide con `CLAUDE.md` ("Estructura del repositorio") y con `05_service_design.md` sección 2 (`api/`, `web/`, `infra/`, `docs/adr/`) más `scripts/workflow/` de la sección 7.
- `web/` existe como carpeta aunque su contenido depende de D1 (front en este repo); crearla vacía con `.gitkeep` no compromete nada si el gate rechaza D1.
- Sin módulos, sin bus de criptografía, sin roles, sin paginación ni auditoría: no aplica.
- "Calidad y Git" de `CLAUDE.md`: `main` protegida, ramas `feat/`, `fix/`, `chore/`, Conventional Commits. Confirmado.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (todavía no existe `api/tests/architecture/`; la crea US-002).

### Front
- No aplica.

### DevOps
- [ ] T1 · Verificar el estado del repositorio local: `git status`, `git remote -v` (debe mostrar `origin` → `rojored7/Apex`), rama actual `main`; documentar en el PR que el repositorio ya estaba inicializado — 0,5 h
- [ ] T2 · Revisar y completar `.gitignore` de la raíz: confirmar `.env`, `.env.*`, `!.env.example`, `*.key`, `*.pem`, `keys/`, `node_modules/`, `.venv/`, `web/dist/`, `__pycache__/`; agregar `*.kek`, `api/.coverage`, `api/coverage.xml`, `web/.vite/` y `scripts/workflow/tests/tmp/` si faltan — 0,5 h
- [ ] T3 · Crear las carpetas versionadas `api/`, `web/`, `infra/`, `docs/adr/`, `scripts/workflow/`, cada una con un `README.md` de una línea que diga qué vive ahí (o `.gitkeep` en `docs/adr/` y `scripts/workflow/`) — 0,5 h
- [ ] T4 · Agregar `.gitattributes` en la raíz con `* text=auto`, `*.sh text eol=lf`, `*.woff2 binary`, `*.png binary` (los scripts de US-008 corren en Linux y fallan con CRLF; las fuentes de US-009 son binarias) — 0,5 h
- [ ] T5 · Escribir `CONTRIBUTING.md`: convención de ramas `feat/`, `fix/`, `chore/`; formato Conventional Commits con los tipos `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`; prohibición de push directo a `main`; regla de actualizar `NOTICE` al agregar dependencias (la completa US-004) — 1 h
- [ ] T6 · Actualizar el `README.md` de la raíz con un enlace a `CONTRIBUTING.md` y una sección corta "Estructura" (el arranque en 5 minutos lo escribe US-007) — 0,5 h
- [ ] T7 · Primer commit `chore: estructura inicial` en una rama `chore/estructura-inicial`, push y PR hacia `main` (el primer commit de `main` se crea con el merge del PR o, si GitHub exige una rama base existente, con un commit inicial vacío `chore: inicio del repositorio` empujado antes de activar la protección) — 1 h
- [ ] T8 · Configurar la protección de `main` en GitHub (ruleset o branch protection): PR obligatorio con al menos 1 aprobación, bloquear force push y borrado de la rama, "Require status checks" vacío por ahora (US-003 agrega `api`, `web`, `images`); comando de referencia `gh api -X PUT repos/rojored7/Apex/branches/main/protection --input infra/github/main-protection.json` con el JSON versionado en `infra/github/main-protection.json` — 1,5 h

### Seguridad
- [ ] T9 · Verificar que no hay secretos en el historial (`git log -p --all | grep -i "BEGIN PRIVATE KEY"` sin resultados) y que un `.env` de prueba no aparece en `git status`; probar un `git push origin main` directo con un commit de control y registrar el rechazo en la descripción del PR — 1 h

## Orden de ejecución
1. T1 (estado real del repositorio)
2. T2, T4 (ignorar y normalizar fin de línea antes de agregar archivos)
3. T3, T5, T6 (contenido del primer commit)
4. T7 (primer commit y PR)
5. T8 (protección de `main` una vez existe la rama en el remoto)
6. T9 (verificación de secretos y push rechazado)

## Dependencias técnicas
- Ninguna.

## Endpoints
- Ninguno.

## Riesgos
- Protección de rama en repositorio privado: GitHub Free no ofrece branch protection ni rulesets en repositorios privados de cuentas personales; sin plan Pro, Team o Enterprise el criterio 4 (push directo rechazado) no se puede cumplir — mitigación: confirmar el plan de la cuenta `rojored7` antes de T8; si es Free, pasar la cuenta a Pro o el repositorio a una organización con Team; un hook local `pre-push` no sustituye la protección del servidor y no se acepta como cierre del criterio.
- Primer commit con la protección ya activa: si la protección se activa antes de que exista un commit en `main`, el primer PR no tiene rama base — mitigación: el orden T7 antes de T8.
- Fin de línea en Windows: sin `.gitattributes` los `.sh` llegan con CRLF y fallan en CI — mitigación: T4 antes de cualquier script.
- `_entregas/` tiene el zip original del diseño: el `.gitignore` ya excluye `_entregas/**/*.zip`; verificar en T9 que no entra por error.

## Estimación
- Backend: 0 h
- Front: 0 h
- Pruebas: 1 h
- DevOps / seguridad: 6 h
- **Total: 7 h**

## Definición de hecho
- [ ] `git log --oneline -1` muestra un commit con formato Conventional Commits en `main`
- [ ] `git ls-files api web infra docs/adr scripts/workflow` lista al menos un archivo en cada carpeta
- [ ] `echo "X=1" > .env && git status --porcelain | grep -c "\.env$"` devuelve 0 (y se borra el `.env` de prueba)
- [ ] `git check-ignore -v keys/kek.bin web/dist/index.html api/.venv/x` devuelve una regla para cada ruta
- [ ] `git log -p --all | grep -ci "BEGIN PRIVATE KEY"` devuelve 0
- [ ] `git push origin HEAD:main` con un commit de control es rechazado por el remoto (salida pegada en el PR)
- [ ] `gh api repos/rojored7/Apex/branches/main/protection` responde 200 con `required_pull_request_reviews` y `allow_force_pushes.enabled = false`
- [ ] `CONTRIBUTING.md` contiene las cadenas `feat/`, `fix/`, `chore/` y "Conventional Commits"
