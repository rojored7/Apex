# 09 · Plan de sprints

Fecha: 21 de octubre de 2026.

Entradas, en orden de precedencia (la de arriba manda):
- `DECISIONES.md`:
  - las secciones B, D y E se tratan como resueltas;
  - la sección A se presenta como bloqueo previo del Sprint 0.
- `CLAUDE.md`.
- `08_implementation_breakdown/`: el README, los 119 desgloses de v0.1 y los 13 `BREAKDOWN.md` de v0.2 a v1.0.
- `07_user_stories/README.md`: 199 historias, sus puntos y el orden sugerido de v0.1.
- `06_epics/README.md`: grafo de épicas y ruta crítica.
- `04_architecture_decision.md`, `05_service_design.md` y `03_context_map.md` sección 4.

## Resumen

- Son **11 sprints**, del Sprint 0 al Sprint 10.
- **v0.1 completa** (EP-00 a EP-13: 119 historias, 379 puntos, 1.720 h relativas) va en cinco sprints, del Sprint 0 al Sprint 4, con slices detallados.
- **v0.2 a v1.0** (EP-14 a EP-26: 80 historias, 311 puntos, 1.310 h relativas) va en un sprint por versión, del Sprint 5 al Sprint 10. No tiene slices detallados: cada sprint se refina cuando llegue.
- Las 199 historias quedan asignadas a exactamente un sprint. Ninguna queda fuera del plan.
- **Estados:**
  - el desglose marca como NEEDS_REFINEMENT o ARCHITECTURAL_GAP_DETECTED 17 historias de v0.1 y 8 de v0.2 a v1.0;
  - `DECISIONES.md` sección E acepta la propuesta por defecto de todas:
    - brechas G-01 a G-10;
    - refinamientos US-004, US-008, US-022, US-024, US-030, US-056, US-057, US-061, US-062, US-110, US-123, US-160, US-166, US-181 y US-197;
  - este plan las trata como READY, y cada sprint nombra la decisión que aplica.
- **Entregable de v0.1, al cerrar el Sprint 4:**
  - `docker compose up` en el servidor del gimnasio;
  - login por rol;
  - socios con datos personales cifrados;
  - planes;
  - venta, renovación, congelación y anulación de membresías;
  - pagos inmutables;
  - auditoría verificable;
  - tablero;
  - worker de vencimientos;
  - backup cifrado y verificado;
  - importación desde Excel.

## Supuestos de dimensionado

- **Quién ejecuta:** Claude Code con agentes, no un equipo de N personas. Se dimensiona por **slice verificable** y por **dependencias**, no por horas-persona.
- **Horas:** las del desglose valen solo como **peso relativo** entre sprints. No son un compromiso de calendario.
- **Tamaño:** cada sprint cabe en una sesión larga de agentes, con 20 a 35 historias de v0.1 o un bloque coherente de una versión posterior.
  - El Sprint 0 pesa menos (203 h relativas): es arranque en frío y los gates nacen dentro del mismo sprint.
  - Los Sprints 1 a 4 pesan entre 365 y 389 h relativas cada uno; la diferencia máxima entre ellos es del 7 %.
- **Waves:** cada sprint las corre en este orden fijo.
  1. Wave 0: infraestructura (`devops-wsl2-docker`).
  2. Wave 3a: tests de backend en rojo (`backend-qa-executor`).
  3. Wave 3b: implementación de backend por slices (`backend-implementor`).
  4. Wave 5a: tests de front en rojo (`frontend-qa-automation`).
  5. Wave 5b: implementación de front por slices (`frontend-ux-engineer`).
  6. Validación: integración, E2E, smoke y lint.
  7. Revisión de seguridad.
- **Slice:**
  - es un grupo de 1 a 4 historias del mismo módulo, o de módulos que se prueban juntos;
  - pasa junto `scripts/workflow/slice-gate.sh` y se confirma con un solo `scripts/workflow/checkpoint-commit.sh`;
  - los slices van en orden de dependencias, y cada uno deja el proyecto en verde.
- **Dependencias:** se distinguen dos clases, siguiendo el propio desglose.
  - **De bloqueo:** la historia no puede empezar sin la otra. Nunca se violan.
  - **De cierre (consumidor):** la otra historia activa un criterio o se conecta después. El desglose la marca como "no bloquea", "suave", "punto de extensión" o "consumidor".
  - Cuando un criterio de una historia solo se cierra en un sprint posterior, el archivo del sprint lo declara como **criterio diferido** y dice en qué sprint se cierra.
- **Migraciones:** van estrictamente de `0001` a `0013`, y los números son definitivos (README del desglose). Ese orden obliga a tres cosas:
  - `0008` a `0011` (membresías, congelaciones, pagos e inmutabilidad) van juntas en el Sprint 3;
  - `0012` (worker) y `0013` (verificaciones de auditoría) van en el Sprint 4;
  - por eso US-113, US-094, US-104 y US-105 están en el Sprint 4, aunque por dependencias funcionales podrían ir antes.
- **Front:** una pantalla entra en el mismo sprint que su API o en el siguiente, nunca antes. Los componentes del kit (EP-06) no son pantallas: entran en cuanto existe el contrato que consumen (`docs/openapi.json`, paginación, envelope de errores).
- **Gate humano previo:** el plan supone que se aprueba `DECISIONES.md` sección A, en especial D1/S1 (el front se construye en `web/` dentro de este flujo).
  - Si D1 no se aprueba, salen las Waves 5a y 5b de todos los sprints y la EP-06 completa (126 h).
  - El backend no cambia de orden.

## Índice de sprints

| Sprint | Versión | Objetivo | Historias | Puntos | Horas relativas | Waves | Entregable demostrable |
|---|---|---|---|---|---|---|---|
| [Sprint 0](SPRINT-00.md) | v0.1 | Terreno, gates y esqueleto ejecutable | 17 | 48 | 203 | 0, 3a, 3b, 5a, 5b | `docker compose up` con `/health` y `/api/v1/health` en verde, `pytest` contra `db_test`, CI con licencias, esqueleto del front |
| [Sprint 1](SPRINT-01.md) | v0.1 | Núcleo de auditoría, bus de criptografía y seguridad de plataforma | 28 | 83 | 365 | 0, 3a, 3b, 5a, 5b | `cli init-keys` y `cli seed`, cadena de auditoría con trigger, blob `apx1.` en la base, rutas sin rol que fallan, CSP con nonce, kit del front |
| [Sprint 2](SPRINT-02.md) | v0.1 | Identidad, configuración, shell del front, primeros socios y planes | 26 | 87 | 374 | 0, 3a, 3b, 5a, 5b | Login por rol, usuarios con activación, configuración, crear socio y verlo cifrado en la base, crear plan |
| [Sprint 3](SPRINT-03.md) | v0.1 | Núcleo comercial: membresías, pagos y ficha del socio | 25 | 78 | 389 | 3a, 3b, 5a, 5b (Wave 0 solo verifica la línea base) | Vender con primer pago, activar por cobertura, renovar, congelar y anular; pago inmutable; ficha con dato enmascarado y revelado auditado |
| [Sprint 4](SPRINT-04.md) | v0.1 | Auditoría, tablero, worker y puesta en marcha (release v0.1) | 23 | 83 | 389 | 0, 3a, 3b, 5a, 5b | Worker de vencimientos, verificación de la cadena, tablero, backup cifrado y verificado, restauración, rotación de llave, importación de Excel |
| [Sprint 5](SPRINT-05.md) | v0.2 | OpenBao, avisos de vencimiento, recibos y exportaciones | 20 | 78 | 323 | todas | KEK en OpenBao, "por avisar hoy" con WhatsApp y correo, recibo PDF, CSV de socios y de pagos |
| [Sprint 6](SPRINT-06.md) | v0.3 | Auditoría firmada, llaves, adjuntos y TLS híbrido | 14 | 53 | 217 | todas | Firma nocturna de la cadena, pantalla de llaves con CBOM, foto y autorización de datos, Caddy con X25519MLKEM768 |
| [Sprint 7](SPRINT-07.md) | v0.4 | Clases, horario y check-in | 11 | 39 | 164 | todas | Horario semanal, sesiones generadas, check-in en tablet con advertencias, descuento de clases |
| [Sprint 8](SPRINT-08.md) | v0.5 | Movimientos, WODs, resultados y TV | 13 | 49 | 213 | todas | WOD del día, resultados en tablet, leaderboard, pantalla de TV con token |
| [Sprint 9](SPRINT-09.md) | v0.6 | Perfil del atleta | 7 | 26 | 109 | 3a, 3b, 5a, 5b | Medidas cifradas, RM derivados y benchmarks en la ficha |
| [Sprint 10](SPRINT-10.md) | v1.0 | Portal del socio y cierre criptográfico post-cuántico | 15 | 66 | 284 | todas | Portal de 5 pestañas, push de récord, backups firmados, DEKs re-envueltas con ML-KEM |
| **Total** | | | **199** | **690** | **3.030** | | |

## Historias por sprint

- **Sprint 0 (17):** US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008, US-009, US-010, US-011, US-012, US-013, US-014, US-017, US-018, US-020.
- **Sprint 1 (28):** US-015, US-016, US-019, US-021, US-022, US-023, US-024, US-025, US-026, US-027, US-028, US-029, US-032, US-033, US-034, US-035, US-036, US-037, US-038, US-039, US-040, US-041, US-059, US-060, US-063, US-064, US-065, US-066.
- **Sprint 2 (26):** US-031, US-042, US-043, US-044, US-045, US-046, US-047, US-048, US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-057, US-058, US-061, US-062, US-067, US-068, US-069, US-070, US-078, US-079, US-107.
- **Sprint 3 (25):** US-056, US-071, US-072, US-073, US-074, US-075, US-076, US-083, US-084, US-085, US-086, US-087, US-088, US-089, US-090, US-091, US-092, US-093, US-095, US-096, US-097, US-098, US-099, US-100, US-101.
- **Sprint 4 (23):** US-030, US-077, US-080, US-081, US-082, US-094, US-102, US-103, US-104, US-105, US-106, US-108, US-109, US-110, US-111, US-112, US-113, US-114, US-115, US-116, US-117, US-118, US-119.
- **Sprint 5 (20):** EP-14 (US-120 a US-132), EP-15 (US-133 a US-136) y EP-16 (US-137 a US-139).
- **Sprint 6 (14):** EP-17 (US-140 a US-142), EP-18 (US-143 a US-146), EP-19 (US-147 a US-151) y EP-20 (US-152 y US-153).
- **Sprint 7 (11):** EP-21 (US-154 a US-164).
- **Sprint 8 (13):** EP-22 (US-165 a US-174) y EP-23 (US-175 a US-177).
- **Sprint 9 (7):** EP-24 (US-178 a US-184).
- **Sprint 10 (15):** EP-25 (US-185 a US-195) y EP-26 (US-196 a US-199).

Historias que cambian de lugar respecto al orden sugerido de `07_user_stories/README.md`, y por qué:
- **US-031** (pruebas de arquitectura criptográfica) pasa al Sprint 2, junto a US-069. El desglose dice que su primera tabla real es `members`.
- **US-030** (rotación de llave por CLI) pasa al Sprint 4, después de US-116 (respaldo de la KEK). Así hay columnas cifradas reales que recifrar, y el runbook pide un respaldo previo.
- **US-107** (auditoría de eventos de seguridad) se adelanta al Sprint 2:
  - todas sus dependencias de bloqueo están en ese sprint;
  - si esperara al Sprint 4, los inicios de sesión de los Sprints 2 y 3 no quedarían auditados.
- **US-056** (medios de pago) pasa al Sprint 3. El desglose deja a US-095 como dueña del router de `payments`, y `GET /payments/methods` vive ahí.
- **US-080, US-081 y US-082** (editar, activar y desactivar, y dar de baja un plan) pasan al Sprint 4:
  - sus pruebas conjuntas con US-084 y con `count_active_by_plan` (US-092) quedan sin dobles;
  - de paso se balancea el Sprint 2.
- **US-094 y US-113** (job de vencimientos y worker) van al Sprint 4 por el orden de migraciones: `0012` va después de `0011`.

## Mapa de dependencias entre sprints

Una flecha `A → B` significa que B necesita a A cerrado.

```
Sprint 0 (EP-00, EP-01 mínimo; 0001)
 └─► Sprint 1 (EP-01 resto, EP-02, EP-03, US-041, kit; 0002–0004)
      └─► Sprint 2 (EP-04, EP-05, shell, socios y planes base, US-107; 0005–0007)
           └─► Sprint 3 (EP-09, EP-10, ficha del socio; 0008–0011)
                └─► Sprint 4 (EP-11, EP-12, EP-13, worker, US-030; 0012–0013) = release v0.1
                     ├─► Sprint 5 (v0.2: EP-15 → EP-14, EP-16; 0020–0039)
                     │    └─► Sprint 6 (v0.3: EP-17, EP-18, EP-19, EP-20; 0040–0059)
                     ├─► Sprint 7 (v0.4: EP-21; 0060–0069)   [solo necesita v0.1]
                     │    └─► Sprint 8 (v0.5: EP-22, EP-23; 0070–0084)
                     │         └─► Sprint 9 (v0.6: EP-24; 0085–0089)
                     └──────────────► Sprint 10 (v1.0: EP-25, EP-26; 0090–0099)
                                       necesita los Sprints 5, 6, 8 y 9
```

Dependencias que saltan más de un sprint:
- **El Sprint 6 necesita el Sprint 5:**
  - EP-17 y EP-18 dependen de EP-15 (OpenBao y `OpenBaoProvider`);
  - EP-17 usa `core/alerts.py` (G-08), que crea US-126 en el Sprint 5.
- **El Sprint 7 solo depende de v0.1** (EP-09, EP-07, EP-05, EP-12 y EP-06).
  - Si el negocio prefiere clases antes que OpenBao, se puede correr antes de los Sprints 5 y 6 sin cambiar su contenido.
  - Los rangos de migración no chocan.
- **El Sprint 10 necesita:**
  - EP-14 y EP-16 (Sprint 5);
  - EP-17, EP-18 y EP-20 (Sprint 6);
  - EP-22 (Sprint 8);
  - EP-24 (Sprint 9).

## Ruta crítica entre sprints

Sprint 0 → Sprint 1 → Sprint 2 → Sprint 3 → Sprint 4 → Sprint 7 → Sprint 8 → Sprint 9 → Sprint 10.

Coincide con la ruta crítica de épicas: EP-00 → EP-01 → EP-02 → EP-07 → EP-09/EP-10 → EP-12 → EP-21 → EP-22 → EP-24 → EP-25. Los Sprints 5 y 6 corren fuera de la ruta crítica, pero tienen que estar cerrados antes del Sprint 10.

Ruta crítica de historias dentro de v0.1:
- Sprint 0: US-001 → US-002 → US-011 → US-012.
- Sprint 1: US-015 → US-016 → US-023/US-024 → US-025 → US-028.
- Sprint 2: US-069.
- Sprint 3: US-084 → US-095 → US-096 → US-085 → US-086 → US-092.
- Sprint 4: US-113 → US-094 y US-108.

## Riesgos por sprint

- **Sprint 0:**
  - [HIGH] El gate humano de `DECISIONES.md` sección A no se aprueba. Cambiar el "Alcance" de `CLAUDE.md` (D1) es requisito de todas las Waves 5.
    - Mitigación: la tarea documental es la primera del sprint y bloquea. Si D1 no pasa, se re-planea sin front.
  - [MEDIUM] Los gates no existen al empezar.
    - Mitigación: US-008 es el segundo slice; antes, la verificación es manual y queda escrita.
  - [MEDIUM] `slice-gate.sh` solo cubre módulos del api.
    - Mitigación: ajuste A-01 de US-008 (ver "Ajustes al flujo").
- **Sprint 1:**
  - [HIGH] Tres formatos son irreversibles: la serialización canónica de la cadena (US-015), el blob `apx1.` (US-025) y la normalización del índice ciego (US-026, N-02).
    - Mitigación: vectores de prueba fijos, ADR en el Sprint 4 y ningún dato real antes del release.
  - [MEDIUM] El `seq` de la auditoría va bajo lock asesor (N-30), y un hueco cuenta como ruptura.
    - Mitigación: prueba de concurrencia de US-015.
- **Sprint 2:**
  - [HIGH] US-069 fija con datos el índice único parcial y el formato cifrado del padrón.
    - Mitigación: US-031 entra en el mismo slice y `test_members_encrypted_at_rest.py` bloquea.
  - [MEDIUM] Refresh con varias pestañas, y reuso de un refresh que revoca todas las sesiones (US-043, N-13).
    - Mitigación: E2E con dos pestañas.
- **Sprint 3:**
  - [HIGH] El nudo membresías–pagos se resuelve completo en este sprint: `EXCLUDE USING gist`, bus transaccional, trigger de inmutabilidad y puerto G-03.
    - Mitigación: slices pequeños en orden estricto y `test_service_import_graph.py` desde US-085.
  - [HIGH] Un trigger de `0011` mal escrito bloquea anulaciones legítimas o deja editar la caja.
    - Mitigación: una prueba por cada columna permitida y por cada columna prohibida (US-096).
- **Sprint 4:**
  - [HIGH] Operaciones irreversibles: rotación (US-030), respaldo de la KEK (US-116) y restauración.
    - Mitigación: US-116 va antes que US-030, la restauración se ensaya en una base limpia y una persona confirma antes de correr cualquiera sobre datos reales.
  - [MEDIUM] Es el sprint con más infraestructura nueva: worker, contenedor de backup, `age` y arranque ordenado.
    - Mitigación: la Wave 0 se completa antes del backend, y el smoke cubre el stack completo.
- **Sprint 5:**
  - [HIGH] Perder 3 de las 5 llaves de desellado equivale a perder todos los datos cifrados.
    - Mitigación: ensayo de desellado, y conservar el backup de la KEK local hasta verificar la migración.
  - [MEDIUM] Canales externos intermitentes (SMTP, Telegram).
- **Sprint 6:**
  - [MEDIUM] OpenBao sin ML-DSA (Q27).
    - Mitigación: la llave nace Ed25519 y se rota después.
  - [MEDIUM] Caddy sin `x25519mlkem768`.
    - Mitigación: fijar la versión 2.10 o superior por digest.
- **Sprint 7:**
  - [MEDIUM] Ciclo `members` ↔ `classes` (G-10).
    - Mitigación: ampliar la lista blanca de G-03 antes de US-163.
  - [MEDIUM] Recorte de `end_date` al agotar las clases (US-160).
- **Sprint 8:**
  - [HIGH] Trigger de `wod_results` e índice parcial `is_current` (Q18).
  - [MEDIUM] Prueba de uso real de la tablet con un coach.
- **Sprint 9:**
  - [MEDIUM] Un RM derivado de un error de digitación queda para siempre.
    - Mitigación: `invalidated_at` (US-181).
- **Sprint 10:**
  - [HIGH] Re-envoltura con ML-KEM, que es irreversible.
  - [HIGH] IDOR en las rutas `/me/*`.
    - Mitigación: prueba de arquitectura anti-IDOR.
  - [MEDIUM] `liboqs` dentro de la imagen.

## Cómo se cierra un sprint (gates)

Por slice, dentro de las Waves 3b y 5b:
1. La Wave 3a (o la 5a) deja las pruebas del slice en rojo.
   - Verifica que fallan por la razón esperada (falta la implementación), no por un error de sintaxis o de import.
   - Las confirma con un commit normal `test(<modulo>): ... (rojo)` en la rama del sprint.
2. La Wave 3b (o la 5b) implementa hasta que pasa `scripts/workflow/slice-gate.sh <modulo>`: ruff, formato, mypy y pytest del módulo. En el front, con el ajuste A-01.
3. Si el slice toca una migración, antes del checkpoint se corre el ciclo `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`.
4. `scripts/workflow/checkpoint-commit.sh "<slice>: <historias>"` confirma el slice. Solo funciona con el sello vigente, nunca en `main` y nunca hace push.

Al cerrar cada wave se corre `scripts/workflow/run-gates.sh`:
- api completo, con cobertura del 80 %;
- si existe `web/package.json`: `npm run lint`, `npx tsc --noEmit`, `npm test -- --run --coverage` y `npm run build`.

Al cerrar el sprint se aplica esta Definición de hecho común (cada sprint agrega la suya):
1. **Suite completa en verde:**
   - `scripts/workflow/run-gates.sh`;
   - `cd api && uv run pytest tests/architecture -q`;
   - el paso de CI de US-021, que comprueba que `docs/openapi.json` está al día;
   - licencias: `pip-licenses` y el chequeo del front (US-004).
2. **Integración y E2E:**
   - pruebas de service con el PostgreSQL de prueba (`db_test` de `compose.dev.yml`);
   - specs de Playwright del sprint contra el stack levantado.
3. **Smoke:**
   - `docker compose -f infra/compose.yml up -d --build`;
   - `scripts/ci/compose-smoke.sh` (US-005);
   - recorrido del criterio de demo del sprint sobre el stack real, con evidencia: salida de `curl`, consultas SQL y capturas.
4. **Revisión de seguridad:** el agente `security-reviewer` revisa el diff del sprint. No pueden quedar hallazgos CRITICAL ni HIGH sin resolver. Checklist mínimo:
   - ningún secreto en el código ni en la imagen (gitleaks, US-039);
   - todos los endpoints con rol (`test_every_route_has_role.py`);
   - ningún dato sensible en claro en la base, en los logs ni en la auditoría;
   - `banned-api` intacto.
5. **Verificación de entrega:** la skill `verify-delivery`, con sus dos pilares.
   - Pilar 1: cada historia queda marcada como entregada, parcial o no entregada, con evidencia. Incluye los criterios diferidos declarados.
   - Pilar 2: prueba contra el sistema corriendo, con una escritura real en el camino que cambió y una comprobación cruzada en la base.
6. **Cierre:**
   - un PR de la rama del sprint a `main`, con CI en verde;
   - un reporte consolidado con los slices, los commits, las desviaciones y los criterios diferidos.

Un sprint no se cierra:
- con un criterio diferido que no esté escrito en su archivo;
- con una prueba en rojo marcada como `skip` sin una historia dueña.

## Ajustes al flujo que este plan pide

- **A-01 · Sello de slice para el front (Sprint 0, dentro de US-008).**
  - Problema: el desglose de US-008 define `slice-gate.sh <modulo>` solo para rutas del api. Como `checkpoint-commit.sh` exige ese sello, los slices de las Waves 5a y 5b no podrían confirmarse.
  - Propuesta: ampliar el mapeo de US-008 con `web/<feature>`.
    - Corre `npm run lint`, `npx tsc --noEmit` y `npm test -- --run src/features/<feature>` (o `src/shared`, `src/core` o `src/layouts`).
    - Escribe el mismo sello que los slices del api.
  - Costo: cerca de 1 h dentro de US-008. No cambia ninguna otra historia.
  - Si no se aprueba: cada slice de front corre `run-gates.sh` completo antes de su checkpoint, que es más lento.
- **A-02 · Commit inicial y rama del Sprint 0.** El repositorio no tiene commits y tiene archivos en el área de preparación. Antes de empezar:
  1. hacer el commit inicial en `main` con `docs/` y `CLAUDE.md`;
  2. crear la rama `chore/sprint-00-cimientos`, porque `checkpoint-commit.sh` rechaza `main` por diseño.

## Historias que quedan fuera y por qué

Ninguna de las 199 historias queda fuera del plan. Lo que queda fuera, a propósito, son estos elementos que aparecen en los documentos:
- **Pantallas de referencia** `Mapa`, `P_Lista`, `P_Ficha` y `P_Formulario`: son patrones, no pantallas (`06_epics/README.md`, cobertura).
- **Rutas que no existen por decisión:**
  - `POST /memberships/{id}/renew` (Q2);
  - `GET /users/{id}/activation-link` (N-12).
- **`GET /members/export` en v0.1:** es de v0.2 (US-138, Sprint 5).
- **Migraciones condicionales:**
  - `0014_audit_subject_member` no hace falta: G-05 está aceptado y la columna nace en `0002`;
  - `0014_payments_registered_by_idx` entra solo si la prueba de rendimiento de US-098 la pide.
- **Mejoras para v1.1, sin historia todavía:**
  - cierre de mes (N-27);
  - separar el rol de recepción del rol "dueño" (P1);
  - coach que también es socio (P6);
  - latido para detectar jobs huérfanos de `crypto_jobs` (riesgo de EP-18).
- **Avisos de bienvenida y de activación (Q13):** los eventos existen, pero ninguna regla los consume. De ese grupo, solo el push de récord entra, en v1.0 (US-195).
- **Si el gate no aprueba D1:** salen las tareas de front de todas las historias y la EP-06 completa. El plan de backend queda igual.

## Verificación del plan

- Cada historia de US-001 a US-199 aparece en exactamente una lista de "Historias del sprint".
- Las sumas del índice cuadran con las fuentes:
  - historias y puntos con `07_user_stories/README.md` (199 historias, 690 puntos);
  - horas con `08_implementation_breakdown/README.md` (3.030 h).
- Las migraciones de v0.1 avanzan en orden estricto entre sprints:
  - Sprint 0: `0001`;
  - Sprint 1: de `0002` a `0004`;
  - Sprint 2: de `0005` a `0007`;
  - Sprint 3: de `0008` a `0011`;
  - Sprint 4: `0012` y `0013`.
- Los 63 endpoints de v0.1 quedan así:
  - Sprint 0: 2;
  - Sprint 1: ninguno;
  - Sprint 2: 29;
  - Sprint 3: 22;
  - Sprint 4: 10.
