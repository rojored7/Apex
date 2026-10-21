# US-001 · Como equipo quiero un repositorio git con `main` protegida y la estructura de carpetas acordada para que todo el trabajo posterior tenga un lugar fijo y revisado

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (terreno: `api/`, `web/`, `infra/`, `docs/`, `scripts/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero un repositorio git con `main` protegida, la convención de ramas `feat/`, `fix/`, `chore/` y la estructura de carpetas de `CLAUDE.md`
para que ningún cambio entre a la rama principal sin PR y cada archivo tenga un lugar predecible

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** sección "Calidad y Git" de `CLAUDE.md` (rama `main` protegida, Conventional Commits); riesgo 3 de `00b_impact_analysis.md` (hoy no hay repositorio).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `git init`, `.gitignore` (Python, Node, `.env`, `keys/`, `web/dist`, volúmenes), carpetas `api/`, `web/`, `infra/`, `docs/adr/`, `scripts/workflow/` con un `README.md` o `.gitkeep` cada una, primer commit `chore: estructura inicial`, remoto privado en GitHub y regla de protección de `main` (PR obligatorio, CI obligatorio cuando exista US-003, sin push directo ni force push).
- **Front:** No aplica.

## Criterios de aceptación

1. Existe un repositorio git en la raíz del proyecto con la rama `main` y al menos un commit con formato Conventional Commits.
2. Existen las carpetas `api/`, `web/`, `infra/`, `docs/adr/` y `scripts/workflow/`, cada una versionada.
3. `.gitignore` excluye `.env`, cualquier archivo de llave (`*.key`, `keys/`), `node_modules/`, `.venv/`, `web/dist/` y `__pycache__/`; un `git status` tras crear un `.env` de prueba no lo muestra.
4. La rama `main` del remoto rechaza un `git push` directo y exige PR.
5. `CONTRIBUTING.md` o el `README.md` documenta la convención de ramas `feat/`, `fix/`, `chore/` y el formato de commit.
6. Ningún secreto ni llave queda en el historial (verificado con `git log -p | grep -i "BEGIN PRIVATE KEY"` sin resultados).

## Escenarios BDD

```gherkin
# language: es
Característica: Repositorio con rama principal protegida

  Escenario: Estructura inicial versionada
    Dado un clon limpio del repositorio
    Cuando listo las carpetas de la raíz
    Entonces veo "api", "web", "infra", "docs/adr" y "scripts/workflow"
    Y el último commit sigue el formato Conventional Commits

  Escenario: Push directo a main rechazado
    Dado un desarrollador con permisos de escritura
    Cuando intenta "git push origin main" con un commit nuevo
    Entonces el remoto rechaza el push
    Y le indica que debe abrir un PR

  Escenario: Archivo de secretos ignorado
    Dado que creo un archivo ".env" con una contraseña de prueba
    Cuando ejecuto "git status"
    Entonces el archivo ".env" no aparece como archivo nuevo
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** protección de rama en GitHub (configuración del remoto, no del código).
- **Funciones puras a probar:** ninguna.
- **Pruebas:** verificación manual documentada en el PR (push rechazado) y chequeo de `.gitignore`.
- **Archivos principales:** `.gitignore`, `README.md`, `CONTRIBUTING.md`, `docs/adr/.gitkeep`, `scripts/workflow/.gitkeep`.

## Supuestos

- Supuesto: el remoto es un repositorio privado de GitHub (lo implica GitHub Actions en `CLAUDE.md`); el dueño de la cuenta configura la protección de rama.

## Dependencias

- Ninguna.

## INVEST

- **Independiente:** es la raíz del grafo.
- **Negociable:** el contenido exacto de `.gitignore` y del documento de contribución.
- **Valiosa:** sin repositorio no hay CI, ni revisión, ni historial auditable del código.
- **Estimable:** tareas conocidas y acotadas.
- **Pequeña:** menos de un día.
- **Testeable:** push rechazado, carpetas presentes, `.env` ignorado.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] Estructura y `.gitignore` en `main` vía PR
- [ ] Protección de rama activa y verificada
- [ ] Sin secretos en el historial
- [ ] Revisión de PR aprobada
