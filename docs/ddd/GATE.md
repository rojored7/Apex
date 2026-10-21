# Paquete del gate humano único (Fases 0 a 3)

Fecha: 21 de octubre de 2026. Una sola aprobación autoriza ejecutar los Sprints 0 a 10 de punta a punta con gates automáticos.

## 1. Veredicto de impacto (Fase 0)
AMARILLO: greenfield sin código; sin scripts de gate (se crean en el Sprint 0); cinco decisiones de producto abiertas. Nada ROJO. `docs/ddd/00b_impact_analysis.md`.

## 2. Dominio (Fase 1)
- 17 reglas de negocio con nombre (RN-01 a RN-17): dinero entero en COP, pago inmutable, activación por cobertura, precio pactado, estados por fecha de Bogotá, congelar extiende, check-in nunca bloquea, un resultado por WOD y socio, récord derivado, datos sensibles cifrados con índice ciego, borrado lógico, rol por endpoint, cadena de auditoría, aviso idempotente.
- 15 aggregates en 16 bounded contexts (8 de negocio, 5 de soporte, 3 de lectura). Eventos en memoria dentro de la misma transacción.
- `docs/ddd/01_product_discovery.md`, `02_domain_model.md`, `03_context_map.md`.

## 3. Arquitectura (Fase 2)
- Monolito modular FastAPI + un PostgreSQL con esquema por contexto + worker en la misma imagen + React estático en Nginx. Descartados: microservicios, BaaS, cola externa.
- Trade-offs aceptados: un proceso (bug tumba todo; compensado con tests y healthcheck), DEK en memoria hasta OpenBao en v0.2, TV pública en LAN con token rotable.
- `docs/ddd/04_architecture_decision.md`, `05_service_design.md`.

## 4. Plan de trabajo (Fase 3)
- 27 épicas, 199 historias (690 puntos), desglose técnico por historia para v0.1 (119 historias, 63 endpoints, 13 migraciones) y por épica para v0.2 a v1.0.
- 12 sprints: 0, 1, 2, 3, 4A, 4B (v0.1 completa, release) y 5 a 10 (una versión por sprint). Ruta crítica 0 → 1 → 2 → 3 → 4A → 4B → 7 → 8 → 9 → 10.
- Crítica de plan-critic: iteración 1 RECHAZADO (3 bloqueantes mecánicos), corregido; iteración 2 APROBADO CON OBSERVACIONES, con las cinco observaciones ya aplicadas. `docs/ddd/09_sprint_plan/` (`README.md`, `SPRINT-*.md`, `CRITICA.md`, `CRITICA-2.md`).

## 5. Decisiones que requieren su aprobación (DECISIONES.md sección A)
- **D1.** El front se construye en este repositorio, en `web/`, dentro de este flujo. Hoy `CLAUDE.md` dice lo contrario en "Alcance"; se reescribe en la primera tarea del Sprint 0. Si NO: salen las waves de front y la épica EP-06 (126 h), y el plan se regenera.
- **D2.** El API pagina con `limit`/`offset` (máximo 200), como manda `CLAUDE.md`; `DESIGN.md` y `ROUTES.md` se corrigen.
- **D5.** Vender y renovar pasan por una sola operación `sell` y un solo endpoint `POST /members/{id}/memberships` con primer pago opcional; el pago sigue siendo inmutable y la activación por evento.
- **P5.** El correo de inicio de sesión se guarda en claro en `auth.users.email` (es credencial); el correo del padrón sigue cifrado.
- **P7.** v0.1 solo en LAN por HTTP; TLS con Caddy en v0.3. Si habrá dominio público desde el inicio, Caddy entra en el Sprint 0.
- **Estructura.** Tres épicas de núcleo (base de datos y eventos, bus de criptografía, seguridad) en lugar de una.
- **P1, P3, P4.** No cambian el plan: quién atiende recepción (informativo), destino del backup (S3 compatible por `.env`, si no, local), recibo PDF en v0.2.

## 6. Decisiones tomadas por el orquestador (reversibles ahora, costosas después)
Secciones B, D y E de `DECISIONES.md`: 28 huecos de épicas, 50 supuestos de historias y 10 brechas arquitectónicas. Las que fijan formatos irreversibles con datos reales: normalización del índice ciego (sin tildes, puntos, guiones ni espacios; teléfono solo dígitos sin 57), sin fragmentos en claro de datos cifrados (el enmascarado se calcula en memoria), usuario técnico único `system@apex.local`, congelaciones como tabla propia, catálogo de benchmarks, Telegram solo como alerta interna, check-in que nunca responde error.

## 7. Qué pasa al aprobar
Sprint 0 arranca sin más confirmaciones: tarea documental (aplicar DECISIONES a `CLAUDE.md`, `PLAN.md`, `BRECHAS.md`, dominio, diseño), línea base del entorno (Docker, WSL2, `uv`, puertos), rama `chore/sprint-00-cimientos`, y los slices de cimientos hasta dejar `docker compose up` con `/health` verde y `pytest` contra la base de prueba. Cada sprint termina con reporte consolidado y un paso humano de push y PR.
