# 08 · Desglose técnico de implementación

Fecha: 21 de octubre de 2026.

Entradas, en orden de precedencia (la de arriba manda):
- `DECISIONES.md`
- `CLAUDE.md`
- `07_user_stories/`
- `06_epics/`
- `05_service_design.md` y `04_architecture_decision.md`
- `03_context_map.md` y `01_product_discovery.md`
- `02_domain_model.md`

Cuando una historia contradice `DECISIONES.md`, el desglose sigue a `DECISIONES.md` y lo anota en la sección "Correcciones aplicadas por DECISIONES.md" como "corregido por DECISIONES N-xx".

## Cómo está organizado

- Hay una carpeta por épica, `EP-NN-<slug>/`, con el mismo slug que `07_user_stories/`.
- **v0.1 (EP-00 a EP-13):** un archivo por historia, `US-NNN-<slug>.md`, con el mismo nombre que la historia original. Cada archivo trae:
  - estado de preparación;
  - correcciones aplicadas por DECISIONES;
  - validación contra el dominio y contra la arquitectura;
  - preguntas abiertas;
  - tareas por capa, con horas por tarea: migración, models, service, schemas, router, tests puros, tests de service con PostgreSQL, tests de router, tests de arquitectura, front, DevOps y seguridad;
  - orden de ejecución, dependencias técnicas, endpoints y riesgos;
  - estimación;
  - "Definición de hecho", con comandos exactos.
- **v0.2 a v1.0 (EP-14 a EP-26):** un `BREAKDOWN.md` por épica, que trae:
  - tablas y migraciones (en el rango reservado de la épica);
  - services y eventos;
  - endpoints;
  - front;
  - worker e infraestructura;
  - dependencias y riesgos;
  - una línea por historia con su estado y sus horas.
- Estados posibles:
  - **READY:** resuelto por la historia más `DECISIONES.md`. Tener dependencias no le quita el READY.
  - **NEEDS_REFINEMENT:** queda una pregunta concreta que cambia contrato, esquema o comportamiento.
  - **ARCHITECTURAL_GAP_DETECTED:** la historia necesita algo que la arquitectura no prevé o que viola sus reglas. Va con una propuesta para cerrarlo.
- Todo el trabajo de front supone que el gate aprueba D1/S1 (front en `web/`). Hoy `CLAUDE.md` dice lo contrario en "Alcance". Si el gate no aprueba D1, las tareas de front de cada historia salen del alcance y EP-06 sale completa (126 h).
- Las horas son de una persona con contexto e incluyen pruebas. No incluyen revisión de PR ni las esperas del gate.

## Resumen de estados

Total: 199 historias. 174 READY, 15 NEEDS_REFINEMENT y 10 ARCHITECTURAL_GAP_DETECTED.

- **v0.1, 119 historias:**
  - 102 READY;
  - 10 NEEDS_REFINEMENT: US-004, US-008, US-022, US-024, US-030, US-056, US-057, US-061, US-062, US-110;
  - 7 ARCHITECTURAL_GAP_DETECTED: US-029, US-034, US-071, US-085, US-106, US-113, US-115.
- **v0.2 a v1.0, 80 historias:**
  - 72 READY;
  - 5 NEEDS_REFINEMENT: US-123, US-160, US-166, US-181, US-197;
  - 3 ARCHITECTURAL_GAP_DETECTED: US-126, US-145, US-163.
- **Horas estimadas:** v0.1, 1.720 h; v0.2 a v1.0, 1.310 h; total, 3.030 h.

### Por épica

| Épica | Versión | Historias | READY | NEEDS_REFINEMENT | ARCHITECTURAL_GAP | Horas |
|---|---|---|---|---|---|---|
| [EP-00-cimientos](EP-00-cimientos/) | v0.1 | 10 | 8 | 2 | 0 | 124 |
| [EP-01-nucleo-compartido](EP-01-nucleo-compartido/) | v0.1 | 12 | 11 | 1 | 0 | 140 |
| [EP-02-bus-de-criptografia](EP-02-bus-de-criptografia/) | v0.1 | 9 | 6 | 2 | 1 | 176 |
| [EP-03-seguridad-de-la-plataforma](EP-03-seguridad-de-la-plataforma/) | v0.1 | 9 | 8 | 0 | 1 | 91 |
| [EP-04-identidad-y-acceso](EP-04-identidad-y-acceso/) | v0.1 | 13 | 13 | 0 | 0 | 156 |
| [EP-05-configuracion-del-gimnasio](EP-05-configuracion-del-gimnasio/) | v0.1 | 5 | 3 | 2 | 0 | 59 |
| [EP-06-layout-y-componentes-front](EP-06-layout-y-componentes-front/) | v0.1 | 10 | 8 | 2 | 0 | 126 |
| [EP-07-padron-de-socios](EP-07-padron-de-socios/) | v0.1 | 9 | 8 | 0 | 1 | 176 |
| [EP-08-catalogo-de-planes](EP-08-catalogo-de-planes/) | v0.1 | 5 | 5 | 0 | 0 | 77 |
| [EP-09-membresias](EP-09-membresias/) | v0.1 | 12 | 11 | 0 | 1 | 192 |
| [EP-10-pagos](EP-10-pagos/) | v0.1 | 7 | 7 | 0 | 0 | 105 |
| [EP-11-auditoria](EP-11-auditoria/) | v0.1 | 6 | 5 | 0 | 1 | 94 |
| [EP-12-tablero-de-inicio](EP-12-tablero-de-inicio/) | v0.1 | 3 | 2 | 1 | 0 | 50 |
| [EP-13-puesta-en-marcha-y-continuidad](EP-13-puesta-en-marcha-y-continuidad/) | v0.1 | 9 | 7 | 0 | 2 | 154 |
| [EP-14-avisos-de-vencimiento](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | v0.2 | 13 | 11 | 1 | 1 | 186 |
| [EP-15-custodia-de-llaves-openbao](EP-15-custodia-de-llaves-openbao/BREAKDOWN.md) | v0.2 | 4 | 4 | 0 | 0 | 83 |
| [EP-16-recibos-y-exportaciones](EP-16-recibos-y-exportaciones/BREAKDOWN.md) | v0.2 | 3 | 3 | 0 | 0 | 54 |
| [EP-17-auditoria-firmada](EP-17-auditoria-firmada/BREAKDOWN.md) | v0.3 | 3 | 3 | 0 | 0 | 54 |
| [EP-18-administracion-de-llaves](EP-18-administracion-de-llaves/BREAKDOWN.md) | v0.3 | 4 | 3 | 0 | 1 | 59 |
| [EP-19-adjuntos-y-autorizacion-de-datos](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | v0.3 | 5 | 5 | 0 | 0 | 75 |
| [EP-20-acceso-cifrado-tls](EP-20-acceso-cifrado-tls/BREAKDOWN.md) | v0.3 | 2 | 2 | 0 | 0 | 29 |
| [EP-21-clases-y-check-in](EP-21-clases-y-check-in/BREAKDOWN.md) | v0.4 | 11 | 9 | 1 | 1 | 164 |
| [EP-22-entrenamiento-wods-y-resultados](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | v0.5 | 10 | 9 | 1 | 0 | 178 |
| [EP-23-pantalla-de-tv](EP-23-pantalla-de-tv/BREAKDOWN.md) | v0.5 | 3 | 3 | 0 | 0 | 35 |
| [EP-24-perfil-del-atleta](EP-24-perfil-del-atleta/BREAKDOWN.md) | v0.6 | 7 | 6 | 1 | 0 | 109 |
| [EP-25-portal-del-socio](EP-25-portal-del-socio/BREAKDOWN.md) | v1.0 | 11 | 11 | 0 | 0 | 184 |
| [EP-26-cierre-criptografico-post-cuantico](EP-26-cierre-criptografico-post-cuantico/BREAKDOWN.md) | v1.0 | 4 | 3 | 1 | 0 | 100 |


## Índice de historias

### v0.1 (un archivo por historia)

| Historia | Título | Estado | Horas |
|---|---|---|---|
| [US-001](EP-00-cimientos/US-001-repositorio-git-y-estructura.md) | Repositorio git y estructura | READY | 7 |
| [US-002](EP-00-cimientos/US-002-proyecto-api-uv-ruff-mypy-pytest.md) | Proyecto api con uv, ruff, mypy, pytest y pre-commit | READY | 12 |
| [US-003](EP-00-cimientos/US-003-pipeline-ci.md) | Pipeline de CI con PostgreSQL 16 y build de imágenes | READY | 12 |
| [US-004](EP-00-cimientos/US-004-chequeo-de-licencias-y-notice.md) | Chequeo de licencias en CI y archivo NOTICE | NEEDS_REFINEMENT | 11 |
| [US-005](EP-00-cimientos/US-005-dockerfile-api-y-compose.md) | Imagen del api y Compose de producción y desarrollo | READY | 20 |
| [US-006](EP-00-cimientos/US-006-nginx-e-imagen-del-front.md) | Nginx con proxy al api e imagen del front | READY | 12 |
| [US-007](EP-00-cimientos/US-007-env-example-y-readme.md) | `.env.example` completo y README de arranque | READY | 5 |
| [US-008](EP-00-cimientos/US-008-scripts-de-gate-del-flujo.md) | Scripts de gate del flujo en `scripts/workflow/` | NEEDS_REFINEMENT | 13 |
| [US-009](EP-00-cimientos/US-009-esqueleto-del-front.md) | Esqueleto del front con tokens y fuentes locales | READY | 18 |
| [US-010](EP-00-cimientos/US-010-componentes-base-button-field-statustag.md) | Componentes base Button, Field y StatusTag | READY | 14 |
| [US-011](EP-01-nucleo-compartido/US-011-configuracion-desde-env.md) | Configuración desde `.env` validada al arrancar | READY | 10 |
| [US-012](EP-01-nucleo-compartido/US-012-base-de-datos-y-alembic-multiesquema.md) | Base de datos async, columnas comunes y Alembic multiesquema | READY | 16 |
| [US-013](EP-01-nucleo-compartido/US-013-reloj-y-fecha-de-bogota.md) | Reloj `Clock` y `today_bogota()` | READY | 7 |
| [US-014](EP-01-nucleo-compartido/US-014-bus-de-eventos-transaccional.md) | Bus de eventos en memoria dentro de la transacción | READY | 11 |
| [US-015](EP-01-nucleo-compartido/US-015-tabla-de-auditoria-y-cadena-de-hashes.md) | Tabla de auditoría append-only y cadena de hashes | READY | 18 |
| [US-016](EP-01-nucleo-compartido/US-016-hook-de-auditoria-after-flush.md) | Hook de auditoría en `after_flush` | READY | 20 |
| [US-017](EP-01-nucleo-compartido/US-017-envelope-de-errores.md) | Envelope único de errores | READY | 10 |
| [US-018](EP-01-nucleo-compartido/US-018-logging-json-sin-datos-sensibles.md) | Logs JSON a stdout sin datos sensibles | READY | 10 |
| [US-019](EP-01-nucleo-compartido/US-019-contrato-de-paginacion.md) | Contrato común de listas con `limit` y `offset` | READY | 10 |
| [US-020](EP-01-nucleo-compartido/US-020-create-app-migraciones-y-health.md) | `create_app()`, migraciones al arrancar y `/health` | READY | 15 |
| [US-021](EP-01-nucleo-compartido/US-021-exportacion-de-openapi.md) | Exportación de `docs/openapi.json` verificada en CI | READY | 7 |
| [US-022](EP-01-nucleo-compartido/US-022-prueba-arquitectura-sin-models-cruzados.md) | Prueba de arquitectura sin `models` cruzados | NEEDS_REFINEMENT | 6 |
| [US-023](EP-02-bus-de-criptografia/US-023-keyprovider-y-proveedor-local.md) | KeyProvider y proveedor local de KEK | READY | 22 |
| [US-024](EP-02-bus-de-criptografia/US-024-tablas-crypto-keys-ops-jobs.md) | Tablas crypto_keys, crypto_ops y crypto_jobs | NEEDS_REFINEMENT | 13 |
| [US-025](EP-02-bus-de-criptografia/US-025-cifrado-aes-gcm-y-formato-de-blob.md) | Cifrado AES-256-GCM y formato de blob | READY | 26 |
| [US-026](EP-02-bus-de-criptografia/US-026-indice-ciego-hmac.md) | Índice ciego HMAC-SHA-256 | READY | 12 |
| [US-027](EP-02-bus-de-criptografia/US-027-firma-y-verificacion-en-el-bus.md) | Firma y verificación en el bus | READY | 9 |
| [US-028](EP-02-bus-de-criptografia/US-028-tipos-de-columna-encrypted-y-blindindexed.md) | Tipos de columna Encrypted y BlindIndexed | READY | 23 |
| [US-029](EP-02-bus-de-criptografia/US-029-bitacora-crypto-ops-por-lote.md) | Bitácora crypto_ops por lote | ARCHITECTURAL_GAP_DETECTED | 21 |
| [US-030](EP-02-bus-de-criptografia/US-030-rotacion-de-llave-por-cli.md) | Rotación de llave por CLI | NEEDS_REFINEMENT | 41 |
| [US-031](EP-02-bus-de-criptografia/US-031-pruebas-de-arquitectura-criptografica.md) | Pruebas de arquitectura criptográfica | READY | 9 |
| [US-032](EP-03-seguridad-de-la-plataforma/US-032-hash-de-contrasenas-argon2id.md) | Hash de contraseñas con argon2id | READY | 8 |
| [US-033](EP-03-seguridad-de-la-plataforma/US-033-jwt-ed25519.md) | JWT Ed25519 y refresh tokens opacos | READY | 13 |
| [US-034](EP-03-seguridad-de-la-plataforma/US-034-dependencias-current-user-y-require-role.md) | Dependencias current_user y require_role | ARCHITECTURAL_GAP_DETECTED | 14 |
| [US-035](EP-03-seguridad-de-la-plataforma/US-035-prueba-de-rutas-con-rol.md) | Prueba de arquitectura de rutas con rol | READY | 8 |
| [US-036](EP-03-seguridad-de-la-plataforma/US-036-rate-limit-login-y-forgot.md) | Rate limit de login y forgot | READY | 11 |
| [US-037](EP-03-seguridad-de-la-plataforma/US-037-cors-cerrado.md) | CORS cerrado a CORS_ORIGINS | READY | 5 |
| [US-038](EP-03-seguridad-de-la-plataforma/US-038-cabeceras-de-seguridad-y-csp.md) | Cabeceras de seguridad y CSP con nonce en Nginx | READY | 11 |
| [US-039](EP-03-seguridad-de-la-plataforma/US-039-gestion-de-secretos.md) | Gestión de secretos y validación al arrancar | READY | 10 |
| [US-040](EP-03-seguridad-de-la-plataforma/US-040-matriz-de-permisos-del-front.md) | Matriz de permisos única del front | READY | 11 |
| [US-041](EP-04-identidad-y-acceso/US-041-cuentas-de-usuario-y-admin-inicial.md) | Cuentas de usuario y admin inicial | READY | 16 |
| [US-042](EP-04-identidad-y-acceso/US-042-iniciar-sesion.md) | Iniciar sesión | READY | 21 |
| [US-043](EP-04-identidad-y-acceso/US-043-renovar-sesion-automaticamente.md) | Renovar sesión automáticamente | READY | 15 |
| [US-044](EP-04-identidad-y-acceso/US-044-cerrar-sesion.md) | Cerrar sesión | READY | 4 |
| [US-045](EP-04-identidad-y-acceso/US-045-ver-mi-cuenta-y-cambiar-contrasena.md) | Ver mi cuenta y cambiar contraseña | READY | 9 |
| [US-046](EP-04-identidad-y-acceso/US-046-listar-usuarios.md) | Listar usuarios | READY | 12 |
| [US-047](EP-04-identidad-y-acceso/US-047-crear-usuario-con-enlace-de-activacion.md) | Crear usuario con enlace de activación | READY | 11 |
| [US-048](EP-04-identidad-y-acceso/US-048-activar-cuenta-y-restablecer-contrasena.md) | Activar cuenta y restablecer contraseña | READY | 18 |
| [US-049](EP-04-identidad-y-acceso/US-049-editar-y-dar-de-baja-usuario.md) | Editar y dar de baja usuario | READY | 13 |
| [US-050](EP-04-identidad-y-acceso/US-050-bloquear-y-desbloquear-usuario.md) | Bloquear y desbloquear usuario | READY | 10 |
| [US-051](EP-04-identidad-y-acceso/US-051-cerrar-sesiones-de-un-usuario.md) | Cerrar sesiones de un usuario | READY | 8 |
| [US-052](EP-04-identidad-y-acceso/US-052-reenviar-enlace-de-activacion.md) | Reenviar enlace de activación o recuperación | READY | 7 |
| [US-053](EP-04-identidad-y-acceso/US-053-guardas-de-ruta-por-rol.md) | Guardas de ruta por rol | READY | 12 |
| [US-054](EP-05-configuracion-del-gimnasio/US-054-secciones-de-configuracion-validadas.md) | Secciones de configuración validadas | READY | 15 |
| [US-055](EP-05-configuracion-del-gimnasio/US-055-datos-del-gimnasio.md) | Datos del gimnasio | READY | 16 |
| [US-056](EP-05-configuracion-del-gimnasio/US-056-etiquetas-de-medios-de-pago.md) | Etiquetas de medios de pago | NEEDS_REFINEMENT | 12 |
| [US-057](EP-05-configuracion-del-gimnasio/US-057-version-de-politica-de-privacidad.md) | Versión de la política de privacidad | NEEDS_REFINEMENT | 8 |
| [US-058](EP-05-configuracion-del-gimnasio/US-058-parametros-de-membresias.md) | Parámetros de membresías | READY | 8 |
| [US-059](EP-06-layout-y-componentes-front/US-059-cliente-api-y-tipos-generados.md) | Cliente API y tipos generados | READY | 12 |
| [US-060](EP-06-layout-y-componentes-front/US-060-formato-de-dinero-y-fechas.md) | Formato de dinero y fechas | READY | 7 |
| [US-061](EP-06-layout-y-componentes-front/US-061-panel-layout-topbar-y-sidenav.md) | Panel layout, TopBar y SideNav | NEEDS_REFINEMENT | 17 |
| [US-062](EP-06-layout-y-componentes-front/US-062-layouts-portal-gym-y-tv.md) | Layouts de portal, gimnasio y TV | NEEDS_REFINEMENT | 15 |
| [US-063](EP-06-layout-y-componentes-front/US-063-tabla-paginacion-filtros-y-chips.md) | Tabla, paginación, filtros y chips | READY | 20 |
| [US-064](EP-06-layout-y-componentes-front/US-064-encabezado-pestanas-y-kpi.md) | Encabezado, pestañas y KPI | READY | 10 |
| [US-065](EP-06-layout-y-componentes-front/US-065-panel-lateral-y-modal-de-confirmacion.md) | Panel lateral y modal de confirmación | READY | 11 |
| [US-066](EP-06-layout-y-componentes-front/US-066-valor-enmascarado-e-historial.md) | Valor enmascarado e historial | READY | 11 |
| [US-067](EP-06-layout-y-componentes-front/US-067-mapa-de-rutas.md) | Mapa de rutas | READY | 7 |
| [US-068](EP-06-layout-y-componentes-front/US-068-temas-accesibilidad-y-capturas.md) | Temas, accesibilidad y capturas | READY | 16 |
| [US-069](EP-07-padron-de-socios/US-069-registrar-socio.md) | Registrar socio | READY | 45 |
| [US-070](EP-07-padron-de-socios/US-070-buscar-y-listar-socios.md) | Buscar y listar socios | READY | 26 |
| [US-071](EP-07-padron-de-socios/US-071-filtrar-socios-por-estado-de-membresia-y-plan.md) | Filtrar socios por estado de membresía y plan | ARCHITECTURAL_GAP_DETECTED | 17 |
| [US-072](EP-07-padron-de-socios/US-072-lista-de-socios-en-celular.md) | Lista de socios en celular | READY | 9 |
| [US-073](EP-07-padron-de-socios/US-073-ver-ficha-del-socio.md) | Ver ficha del socio | READY | 16 |
| [US-074](EP-07-padron-de-socios/US-074-mostrar-dato-sensible-auditado.md) | Mostrar dato sensible auditado | READY | 15 |
| [US-075](EP-07-padron-de-socios/US-075-editar-socio.md) | Editar socio | READY | 24 |
| [US-076](EP-07-padron-de-socios/US-076-dar-de-baja-socio.md) | Dar de baja socio | READY | 16 |
| [US-077](EP-07-padron-de-socios/US-077-contacto-para-avisos-auditado.md) | Contacto para avisos auditado | READY | 8 |
| [US-078](EP-08-catalogo-de-planes/US-078-crear-plan.md) | Crear plan | READY | 25 |
| [US-079](EP-08-catalogo-de-planes/US-079-listar-planes.md) | Listar planes | READY | 14 |
| [US-080](EP-08-catalogo-de-planes/US-080-editar-plan-sin-afectar-vendidas.md) | Editar plan sin afectar vendidas | READY | 15 |
| [US-081](EP-08-catalogo-de-planes/US-081-activar-y-desactivar-plan.md) | Activar y desactivar plan | READY | 12 |
| [US-082](EP-08-catalogo-de-planes/US-082-dar-de-baja-plan-sin-membresias-activas.md) | Dar de baja plan sin membresías activas | READY | 11 |
| [US-083](EP-09-membresias/US-083-reglas-puras-de-fechas-y-estados.md) | Reglas puras de fechas, estados y cobertura | READY | 10 |
| [US-084](EP-09-membresias/US-084-vender-membresia.md) | Vender membresía | READY | 30 |
| [US-085](EP-09-membresias/US-085-vender-con-primer-pago.md) | Vender con primer pago | ARCHITECTURAL_GAP_DETECTED | 20 |
| [US-086](EP-09-membresias/US-086-activar-por-cobertura-de-pagos.md) | Activar por cobertura de pagos | READY | 10 |
| [US-087](EP-09-membresias/US-087-revertir-activacion-al-anular-pago.md) | Revertir activación al anular un pago | READY | 6 |
| [US-088](EP-09-membresias/US-088-renovar-membresia.md) | Renovar membresía | READY | 19 |
| [US-089](EP-09-membresias/US-089-congelar-membresia.md) | Congelar membresía | READY | 25 |
| [US-090](EP-09-membresias/US-090-anular-membresia.md) | Anular membresía | READY | 12 |
| [US-091](EP-09-membresias/US-091-listar-membresias.md) | Listar membresías | READY | 18 |
| [US-092](EP-09-membresias/US-092-resumen-y-consultas-de-estado.md) | Resumen y consultas de estado | READY | 15 |
| [US-093](EP-09-membresias/US-093-pestana-membresias-de-la-ficha.md) | Pestaña Membresías de la ficha | READY | 10 |
| [US-094](EP-09-membresias/US-094-job-diario-de-vencimientos.md) | Job diario de vencimientos | READY | 17 |
| [US-095](EP-10-pagos/US-095-registrar-pago.md) | Registrar pago | READY | 31 |
| [US-096](EP-10-pagos/US-096-inmutabilidad-de-pagos-en-la-base.md) | Inmutabilidad de pagos en la base | READY | 12 |
| [US-097](EP-10-pagos/US-097-anular-pago.md) | Anular pago | READY | 15 |
| [US-098](EP-10-pagos/US-098-listar-y-buscar-pagos.md) | Listar y buscar pagos | READY | 20 |
| [US-099](EP-10-pagos/US-099-ver-detalle-de-pago.md) | Ver detalle de pago | READY | 6 |
| [US-100](EP-10-pagos/US-100-resumen-mensual-de-pagos.md) | Resumen mensual de pagos | READY | 12 |
| [US-101](EP-10-pagos/US-101-pestana-pagos-de-la-ficha.md) | Pestaña Pagos de la ficha | READY | 9 |
| [US-102](EP-11-auditoria/US-102-consultar-auditoria.md) | Consultar auditoría | READY | 21 |
| [US-103](EP-11-auditoria/US-103-ver-detalle-antes-y-despues.md) | Ver detalle antes y después | READY | 9 |
| [US-104](EP-11-auditoria/US-104-verificar-cadena-desde-pantalla.md) | Verificar cadena desde pantalla | READY | 26 |
| [US-105](EP-11-auditoria/US-105-verificar-cadena-por-cli.md) | Verificar cadena por CLI | READY | 8 |
| [US-106](EP-11-auditoria/US-106-historial-del-socio.md) | Historial del socio | ARCHITECTURAL_GAP_DETECTED | 17 |
| [US-107](EP-11-auditoria/US-107-auditoria-de-eventos-de-seguridad.md) | Auditoría de eventos de seguridad | READY | 13 |
| [US-108](EP-12-tablero-de-inicio/US-108-contrato-del-tablero.md) | Contrato del tablero | READY | 15 |
| [US-109](EP-12-tablero-de-inicio/US-109-kpis-de-membresias-e-ingresos.md) | KPIs de membresías e ingresos | READY | 15 |
| [US-110](EP-12-tablero-de-inicio/US-110-ultimos-movimientos.md) | Últimos movimientos | NEEDS_REFINEMENT | 20 |
| [US-111](EP-13-puesta-en-marcha-y-continuidad/US-111-datos-de-demostracion.md) | Datos de demostración | READY | 19 |
| [US-112](EP-13-puesta-en-marcha-y-continuidad/US-112-importar-socios-desde-excel.md) | Importar socios desde Excel | READY | 28 |
| [US-113](EP-13-puesta-en-marcha-y-continuidad/US-113-proceso-worker-programado.md) | Proceso worker programado | ARCHITECTURAL_GAP_DETECTED | 21 |
| [US-114](EP-13-puesta-en-marcha-y-continuidad/US-114-backup-nocturno-cifrado.md) | Backup nocturno cifrado | READY | 21 |
| [US-115](EP-13-puesta-en-marcha-y-continuidad/US-115-verificacion-de-backup.md) | Verificación de backup | ARCHITECTURAL_GAP_DETECTED | 17 |
| [US-116](EP-13-puesta-en-marcha-y-continuidad/US-116-respaldo-de-kek-y-prueba-de-restauracion.md) | Respaldo de la KEK y prueba de restauración | READY | 18 |
| [US-117](EP-13-puesta-en-marcha-y-continuidad/US-117-despliegue-seguro.md) | Despliegue seguro | READY | 12 |
| [US-118](EP-13-puesta-en-marcha-y-continuidad/US-118-arranque-ordenado.md) | Arranque ordenado | READY | 9 |
| [US-119](EP-13-puesta-en-marcha-y-continuidad/US-119-adr-iniciales.md) | ADR iniciales | READY | 9 |

### v0.2 a v1.0 (un BREAKDOWN.md por épica)

| Historia | Título | Estado | Horas |
|---|---|---|---|
| [US-120](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Plantillas de aviso | READY | 22 |
| [US-121](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Reglas de aviso | READY | 21 |
| [US-122](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Configurar canales de aviso | READY | 9 |
| [US-123](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Preferencias de canal del socio | NEEDS_REFINEMENT | 13 |
| [US-124](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Generar avisos del día | READY | 23 |
| [US-125](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Enviar avisos por correo | READY | 20 |
| [US-126](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Enviar avisos por Telegram | ARCHITECTURAL_GAP_DETECTED | 12 |
| [US-127](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Por avisar hoy y enlace de WhatsApp | READY | 23 |
| [US-128](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Omitir aviso con motivo | READY | 8 |
| [US-129](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Historial de envíos | READY | 12 |
| [US-130](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Pestaña avisos de la ficha | READY | 7 |
| [US-131](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | Recuperar y activar cuenta por correo | READY | 12 |
| [US-132](EP-14-avisos-de-vencimiento/BREAKDOWN.md) | KPI por avisar en Inicio | READY | 4 |
| [US-133](EP-15-custodia-de-llaves-openbao/BREAKDOWN.md) | Servicio OpenBao con Transit | READY | 20 |
| [US-134](EP-15-custodia-de-llaves-openbao/BREAKDOWN.md) | Proveedor OpenBao | READY | 30 |
| [US-135](EP-15-custodia-de-llaves-openbao/BREAKDOWN.md) | Migrar proveedor de llaves | READY | 20 |
| [US-136](EP-15-custodia-de-llaves-openbao/BREAKDOWN.md) | Estado degradado con OpenBao sellado | READY | 13 |
| [US-137](EP-16-recibos-y-exportaciones/BREAKDOWN.md) | Descargar recibo de pago | READY | 23 |
| [US-138](EP-16-recibos-y-exportaciones/BREAKDOWN.md) | Exportar socios a CSV | READY | 19 |
| [US-139](EP-16-recibos-y-exportaciones/BREAKDOWN.md) | Exportar pagos a CSV | READY | 12 |
| [US-140](EP-17-auditoria-firmada/BREAKDOWN.md) | Registro de firmas de auditoría | READY | 12 |
| [US-141](EP-17-auditoria-firmada/BREAKDOWN.md) | Firma nocturna de la cadena | READY | 20 |
| [US-142](EP-17-auditoria-firmada/BREAKDOWN.md) | Verificación con firmas y estado en pantalla | READY | 22 |
| [US-143](EP-18-administracion-de-llaves/BREAKDOWN.md) | Inventario de llaves | READY | 12 |
| [US-144](EP-18-administracion-de-llaves/BREAKDOWN.md) | Bitácora y trabajos criptográficos | READY | 13 |
| [US-145](EP-18-administracion-de-llaves/BREAKDOWN.md) | Rotar llave desde la pantalla | ARCHITECTURAL_GAP_DETECTED | 24 |
| [US-146](EP-18-administracion-de-llaves/BREAKDOWN.md) | Exportar CBOM | READY | 10 |
| [US-147](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | Almacenamiento seguro de adjuntos | READY | 24 |
| [US-148](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | Subir foto del socio | READY | 12 |
| [US-149](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | Registrar autorización de datos | READY | 18 |
| [US-150](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | Pestaña adjuntos y descarga auditada | READY | 13 |
| [US-151](EP-19-adjuntos-y-autorizacion-de-datos/BREAKDOWN.md) | Socios sin autorización registrada | READY | 8 |
| [US-152](EP-20-acceso-cifrado-tls/BREAKDOWN.md) | TLS automático con Caddy híbrido | READY | 18 |
| [US-153](EP-20-acceso-cifrado-tls/BREAKDOWN.md) | Redirección HTTPS, HSTS y modo LAN | READY | 11 |
| [US-154](EP-21-clases-y-check-in/BREAKDOWN.md) | Configurar horas y clases | READY | 9 |
| [US-155](EP-21-clases-y-check-in/BREAKDOWN.md) | Horario semanal de franjas | READY | 20 |
| [US-156](EP-21-clases-y-check-in/BREAKDOWN.md) | Generar sesiones desde el horario | READY | 18 |
| [US-157](EP-21-clases-y-check-in/BREAKDOWN.md) | Sesiones de la semana | READY | 22 |
| [US-158](EP-21-clases-y-check-in/BREAKDOWN.md) | Cancelar sesiones futuras de una franja | READY | 7 |
| [US-159](EP-21-clases-y-check-in/BREAKDOWN.md) | Check-in en tablet | READY | 36 |
| [US-160](EP-21-clases-y-check-in/BREAKDOWN.md) | Descontar y devolver clases | NEEDS_REFINEMENT | 13 |
| [US-161](EP-21-clases-y-check-in/BREAKDOWN.md) | Borrar asistencia | READY | 8 |
| [US-162](EP-21-clases-y-check-in/BREAKDOWN.md) | Reportes de asistencia | READY | 14 |
| [US-163](EP-21-clases-y-check-in/BREAKDOWN.md) | Filtro de última asistencia | ARCHITECTURAL_GAP_DETECTED | 9 |
| [US-164](EP-21-clases-y-check-in/BREAKDOWN.md) | KPIs de asistencia en Inicio | READY | 8 |
| [US-165](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Catálogo de movimientos | READY | 20 |
| [US-166](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Crear y editar WOD | NEEDS_REFINEMENT | 40 |
| [US-167](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Calendario de WODs | READY | 12 |
| [US-168](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | WOD del día y asignación a sesiones | READY | 13 |
| [US-169](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Registrar resultados en tablet | READY | 38 |
| [US-170](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Corregir resultado | READY | 12 |
| [US-171](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Leaderboard del día | READY | 20 |
| [US-172](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Detalle de WOD | READY | 11 |
| [US-173](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Pestaña Resultados de la ficha | READY | 8 |
| [US-174](EP-22-entrenamiento-wods-y-resultados/BREAKDOWN.md) | Tarjeta WOD de hoy en Inicio | READY | 4 |
| [US-175](EP-23-pantalla-de-tv/BREAKDOWN.md) | Token de dispositivo de TV | READY | 8 |
| [US-176](EP-23-pantalla-de-tv/BREAKDOWN.md) | Endpoint público de TV | READY | 13 |
| [US-177](EP-23-pantalla-de-tv/BREAKDOWN.md) | Pantalla de TV | READY | 14 |
| [US-178](EP-24-perfil-del-atleta/BREAKDOWN.md) | Registrar medidas corporales cifradas | READY | 22 |
| [US-179](EP-24-perfil-del-atleta/BREAKDOWN.md) | Mostrar medida en claro auditada | READY | 7 |
| [US-180](EP-24-perfil-del-atleta/BREAKDOWN.md) | Registrar récords manuales | READY | 14 |
| [US-181](EP-24-perfil-del-atleta/BREAKDOWN.md) | Récord derivado por carga | NEEDS_REFINEMENT | 22 |
| [US-182](EP-24-perfil-del-atleta/BREAKDOWN.md) | Récord derivado de benchmark | READY | 11 |
| [US-183](EP-24-perfil-del-atleta/BREAKDOWN.md) | Comparar benchmarks | READY | 13 |
| [US-184](EP-24-perfil-del-atleta/BREAKDOWN.md) | Perfil del atleta en la ficha | READY | 20 |
| [US-185](EP-25-portal-del-socio/BREAKDOWN.md) | Crear cuenta de portal | READY | 20 |
| [US-186](EP-25-portal-del-socio/BREAKDOWN.md) | Autorización propia en rutas me | READY | 12 |
| [US-187](EP-25-portal-del-socio/BREAKDOWN.md) | Inicio del portal | READY | 13 |
| [US-188](EP-25-portal-del-socio/BREAKDOWN.md) | Mis pagos y recibos | READY | 11 |
| [US-189](EP-25-portal-del-socio/BREAKDOWN.md) | Mis WODs y enviar resultado | READY | 20 |
| [US-190](EP-25-portal-del-socio/BREAKDOWN.md) | Validar resultados enviados | READY | 18 |
| [US-191](EP-25-portal-del-socio/BREAKDOWN.md) | Mi progreso | READY | 20 |
| [US-192](EP-25-portal-del-socio/BREAKDOWN.md) | Mis datos y contraseña | READY | 20 |
| [US-193](EP-25-portal-del-socio/BREAKDOWN.md) | Mis avisos y canales | READY | 12 |
| [US-194](EP-25-portal-del-socio/BREAKDOWN.md) | Suscripción web push | READY | 24 |
| [US-195](EP-25-portal-del-socio/BREAKDOWN.md) | Aviso de récord nuevo | READY | 14 |
| [US-196](EP-26-cierre-criptografico-post-cuantico/BREAKDOWN.md) | Firma de backups | READY | 24 |
| [US-197](EP-26-cierre-criptografico-post-cuantico/BREAKDOWN.md) | CBOM CycloneDX | NEEDS_REFINEMENT | 12 |
| [US-198](EP-26-cierre-criptografico-post-cuantico/BREAKDOWN.md) | Envoltura de llaves con ML-KEM | READY | 40 |
| [US-199](EP-26-cierre-criptografico-post-cuantico/BREAKDOWN.md) | Re-envoltura reanudable de DEKs | READY | 24 |


## Migraciones de v0.1, en orden

Va una migración por cada cambio de tabla, con `downgrade`. Nunca se edita una migración ya aplicada. Las migraciones de datos (seed, importación, recifrado) son comandos de `cli.py`.

1. **`0001_core_schemas` (US-012):**
   - `CREATE SCHEMA` de `audit`, `crypto`, `auth`, `settings`, `members`, `plans`, `memberships`, `payments` y `worker`;
   - `CREATE EXTENSION btree_gist` (lo exige Q1);
   - sin `pg_trgm`: US-070 no lo necesita.
2. **`0002_audit_log` (US-015):** crea `audit.audit_log` con:
   - `seq BIGINT NOT NULL UNIQUE`, asignado como el último más 1 bajo `pg_advisory_xact_lock`. No es `bigserial`, porque una secuencia deja huecos y N-30 cuenta un hueco como ruptura;
   - `at`, `user_id`, `action` (su CHECK incluye `download`, N-08), `table_name`, `record_id`, `before`, `after`, `prev_hash` y `hash`;
   - columnas comunes, con un CHECK que obliga a que coincidan con `at` y con `user_id`;
   - la función y el trigger `audit.forbid_mutation()`, que rechazan UPDATE, DELETE y TRUNCATE;
   - los índices `at`, `(table_name, record_id)`, `user_id` y `(table_name, seq DESC)`;
   - **condicional:** si el gate aprueba la brecha G-05, además `subject_member_id UUID NULL`, incluida en la serialización canónica, con índice `(subject_member_id, seq DESC)`. Mientras la tabla no tenga datos va aquí; si ya tiene datos, va en `0014_audit_subject_member`.
3. **`0003_crypto` (US-024):** crea `crypto_keys`, `crypto_ops` y `crypto_jobs`.
   - `crypto_keys`: índice único parcial de una sola llave `active` por (`purpose`, `data_class`), CHECK de coherencia entre propósito y algoritmo, y trigger que controla las transiciones de `state` e impide editar `wrapped_material`.
   - `crypto_ops`: columnas `count` (N-05) y `purpose` (N-01, N-21), `user_id NOT NULL` (N-15), el verbo `export` en el CHECK, y triggers append-only.
   - `crypto_jobs`: `kind` incluye `rewrap` (N-05), con índice único parcial de un solo job en curso por clase de dato.
   - El esquema lo crea `0001`; el `downgrade` de esta migración no lo borra.
4. **`0004_auth` (US-041):** crea `users`, `refresh_tokens` y `one_time_tokens`.
   - Índice único parcial `users(email) WHERE deleted_at IS NULL`.
   - `users.last_login_at` (US-046) y `refresh_tokens.replaced_by_id` (detecta el reuso de un refresh, N-13).
   - INSERT del usuario técnico `SYSTEM_USER_ID = 00000000-0000-0000-0000-000000000001` (`system@apex.local`, `admin`, `is_active = false`, N-15).
   - **Condicional:** `users.display_name`, si el gate acepta la pregunta 1 de US-110.
5. **`0005_settings` (US-054):** `settings.settings_sections`, con índice único en `key`, `version` (N-17) y `updated_by`. Los valores por defecto salen del esquema Pydantic con `version: 0`; no se siembran filas.
6. **`0006_members` (US-069):** crea `members.members`.
   - Campos cifrados en texto blob, con sus `*_idx`. No hay columnas `*_hint` (N-01).
   - `sex`, `data_consent_at` y `data_consent_version` (S7).
   - Índice único parcial `document_idx WHERE deleted_at IS NULL`; índices no únicos `phone_idx` y `email_idx`.
7. **`0007_plans` (US-078):** `plans.plans`, con los CHECK de `validate_plan`, el índice único parcial `name WHERE deleted_at IS NULL` (N-22) y el índice `ix_plans_active_alive` (US-079).
8. **`0008_memberships` (US-084):** crea `memberships.memberships`.
   - `EXCLUDE USING gist (member_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')` (Q1).
   - CHECK de fechas, de clases y de cancelación (motivo, autor y fecha).
   - Índices `(status, end_date)` y `(member_id, status, start_date)`.
   - Sin las columnas `frozen_*` ni los contadores, que pasan a `membership_freezes` (N-25).
9. **`0009_membership_freezes` (US-089, N-25):** una fila por congelación, con `frozen_from`, `frozen_to` y `days`. CHECK `frozen_from <= frozen_to`, y `EXCLUDE` por `membership_id` para que haya una sola congelación a la vez.
10. **`0010_payments` (US-095):** crea `payments.payments`.
    - `amount_cop` con CHECK mayor que 0.
    - `method` con CHECK `cash`, `nequi` o `breb`.
    - `reference`, `paid_at`, `registered_by` y las cuatro columnas de anulación, con un CHECK de coherencia entre ellas y `void_reason` de hasta 500 caracteres.
    - `member_id UUID NOT NULL`: copia inmutable del socio de la membresía, que usan US-098, US-101 y G-05.
    - Índices `paid_at`, `membership_id` y `(member_id, paid_at DESC)`.
11. **`0011_payments_immutability` (US-096):** función `payments.forbid_mutation()` y trigger `BEFORE UPDATE OR DELETE`.
    - Deja pasar una sola transición: la anulación, una sola vez y únicamente sobre las columnas de anulación.
    - Otro trigger bloquea `TRUNCATE`.
12. **`0012_worker_job_runs` (US-113):** `worker.job_runs`, con `job_name`, `run_date` (fecha de Bogotá), `started_at`, `finished_at`, `result`, `error` y `details JSONB`.
    - Índice único `(job_name, run_date)`.
    - Los reintentos del día se guardan en `details.attempts`.
    - El model vive en `core/jobs.py` (brecha G-06).
13. **`0013_audit_verifications` (US-104 y US-105, N-30):** `audit.verifications`, append-only, con `started_at`, `finished_at`, `through_seq`, `ok`, `broken_at_seq`, `triggered_by`, `rows_checked` y `source` (`api` o `cli`).

Condicionales, solo si se dispara su condición:
- `0014_audit_subject_member`: la columna de G-05, si `0002` ya tiene datos cuando se apruebe.
- `0014_payments_registered_by_idx`: solo si la prueba de rendimiento de US-098 la pide.
- **Ya no hacen falta:**
  - `0014_crypto_ops_purpose` (US-073): `purpose` ya está en `0003`.
  - `0014_crypto_ops_export_verb` (US-114): `export` ya está en el CHECK de `0003`.

Rangos reservados para v0.2 a v1.0 (el número definitivo se fija al implementar):
- EP-14: 0020 a 0029
- EP-15: 0030 a 0034
- EP-16: 0035 a 0039
- EP-17: 0040 a 0044
- EP-18: 0045 a 0049
- EP-19: 0050 a 0054
- EP-20: 0055 a 0059
- EP-21: 0060 a 0069
- EP-22: 0070 a 0079
- EP-23: 0080 a 0084
- EP-24: 0085 a 0089
- EP-25: 0090 a 0094
- EP-26: 0095 a 0099

Cada `BREAKDOWN.md` lista sus migraciones.

## Endpoints de v0.1

Todos van bajo `/api/v1`, salvo `/health`, que también está en la raíz (N-16). Las rutas fijas se registran antes que las de parámetro: `/audit/verify/last` antes de `/audit/{seq}`, y `/payments/summary` y `/payments/methods` antes de `/payments/{id}`. `GET /plans` para coach solo admite `active=true`. Estas rutas quedan fuera de v0.1:
- `GET /users/{id}/activation-link`: no existe (N-12).
- `POST /memberships/{id}/renew`: no existe (Q2).
- `GET /members/export`: es de v0.2.

| Método y ruta | Roles | Historias |
|---|---|---|
| `GET /api/v1/audit` | admin | US-102 |
| `GET /api/v1/audit/{seq}` | admin | US-103 |
| `POST /api/v1/audit/verify` | admin | US-104 |
| `GET /api/v1/audit/verify/last` | admin | US-104 |
| `POST /api/v1/auth/forgot` | público (lista blanca), límite 5 por minuto por IP | US-036, US-048 |
| `POST /api/v1/auth/login` | público (lista blanca), límite 5 por minuto por IP | US-036, US-042 |
| `POST /api/v1/auth/logout` | admin, coach, member | US-044 |
| `GET /api/v1/auth/me` | admin, coach, member | US-045 |
| `POST /api/v1/auth/me/password` | admin, coach, member | US-045 |
| `POST /api/v1/auth/refresh` | público (lista blanca) | US-043 |
| `POST /api/v1/auth/reset` | público (lista blanca) | US-048 |
| `GET /api/v1/dashboard` | admin, coach | US-108, US-109, US-110 |
| `GET /api/v1/health` | ninguno (lista blanca) | US-020, US-115, US-118 |
| `GET /api/v1/members` | admin, coach | US-070, US-071, US-072 |
| `POST /api/v1/members` | admin, coach | US-069 |
| `DELETE /api/v1/members/{id}` | admin | US-076 |
| `GET /api/v1/members/{id}` | admin, coach | US-073 |
| `PATCH /api/v1/members/{id}` | admin, coach | US-075 |
| `GET /api/v1/members/{id}/audit` | admin, coach | US-106 |
| `GET /api/v1/members/{id}/memberships` | admin, coach | US-093 |
| `POST /api/v1/members/{id}/memberships` | admin, coach | US-084, US-085, US-088 |
| `GET /api/v1/members/{id}/memberships/renewal-preview` | admin, coach | US-088 |
| `GET /api/v1/members/{id}/payments` | admin, coach | US-101 |
| `POST /api/v1/members/{id}/reactivate` | admin | US-076 |
| `POST /api/v1/members/{id}/reveal` | admin, coach | US-074 |
| `GET /api/v1/memberships` | admin, coach | US-091 |
| `GET /api/v1/memberships/{id}` | admin, coach | US-091 |
| `POST /api/v1/memberships/{id}/cancel` | admin | US-090 |
| `POST /api/v1/memberships/{id}/freeze` | admin, coach | US-089 |
| `POST /api/v1/memberships/{id}/payments` | admin, coach | US-095 |
| `GET /api/v1/memberships/summary` | admin, coach | US-092 |
| `GET /api/v1/payments` | admin, coach | US-098 |
| `GET /api/v1/payments/{id}` | admin, coach | US-099 |
| `POST /api/v1/payments/{id}/void` | admin | US-097 |
| `GET /api/v1/payments/methods` | admin, coach | US-056 |
| `GET /api/v1/payments/summary` | admin, coach | US-100 |
| `GET /api/v1/plans` | admin, coach | US-079 |
| `POST /api/v1/plans` | admin | US-078 |
| `DELETE /api/v1/plans/{id}` | admin | US-082 |
| `GET /api/v1/plans/{id}` | admin, coach | US-079 |
| `PATCH /api/v1/plans/{id}` | admin | US-080 |
| `POST /api/v1/plans/{id}/activate` | admin | US-081 |
| `POST /api/v1/plans/{id}/deactivate` | admin | US-081 |
| `GET /api/v1/settings/{section}` | admin | US-054 |
| `PATCH /api/v1/settings/{section}` | admin | US-054 |
| `GET /api/v1/settings/gym` | admin | US-055 |
| `PATCH /api/v1/settings/gym` | admin | US-055 |
| `GET /api/v1/settings/memberships` | admin | US-058 |
| `PATCH /api/v1/settings/memberships` | admin | US-058 |
| `GET /api/v1/settings/payment_methods` | admin | US-056 |
| `PATCH /api/v1/settings/payment_methods` | admin | US-056 |
| `GET /api/v1/settings/privacy` | admin | US-057 |
| `PATCH /api/v1/settings/privacy` | admin | US-057 |
| `GET /api/v1/users` | admin | US-046 |
| `POST /api/v1/users` | admin | US-047 |
| `DELETE /api/v1/users/{id}` | admin | US-049 |
| `GET /api/v1/users/{id}` | admin | US-049 |
| `PATCH /api/v1/users/{id}` | admin | US-049 |
| `POST /api/v1/users/{id}/lock` | admin | US-050 |
| `POST /api/v1/users/{id}/resend-link` | admin | US-052 |
| `POST /api/v1/users/{id}/revoke-sessions` | admin | US-051 |
| `POST /api/v1/users/{id}/unlock` | admin | US-050 |
| `GET /health` | ninguno (lista blanca) | US-020, US-115, US-118 |


## Tests de arquitectura (`api/tests/architecture/`)

Estos son los nombres que proponen los desgloses. Varios cubren lo mismo con nombres distintos, porque salieron de lotes paralelos. Al implementar, se consolidan así:
- **Dirección de imports de `core`:** un solo `test_core_import_direction.py` (US-015) que absorbe `test_core_does_not_import_modules.py`, `test_core_import_graph.py` y `test_core_jobs_imports.py`. Verifica tres cosas:
  - `core` no importa `app.modules`;
  - `core/crypto` no importa `core/audit`;
  - `core/audit` solo toma `core/crypto/digest`.
- **Grafo entre services:** un solo `test_service_import_graph.py` (US-071 o US-085, el que llegue primero) que absorbe `test_service_import_cycles.py`, `test_payments_memberships_cycle.py`, `test_payments_does_not_import_memberships.py` y `test_payments_dependencies.py`. Hace tres cosas:
  - exige un grafo acíclico en el nivel de módulo;
  - admite imports perezosos solo en la lista blanca de G-03;
  - importa cada service en un subproceso limpio.
- **Ningún dato sensible en claro:**
  - `test_no_plaintext_at_rest.py` (genérico, US-028/US-031);
  - `test_members_encrypted_at_rest.py` (caso concreto de `members`).

  Se conservan los dos.

| Test | Historias que lo crean o amplían |
|---|---|
| `api/tests/architecture/test_adr_docs.py` | US-119 |
| `api/tests/architecture/test_audit_subject.py` | US-106 |
| `api/tests/architecture/test_audited_tables.py` | US-024, US-107 |
| `api/tests/architecture/test_auth_routes.py` | US-052 |
| `api/tests/architecture/test_banned_imports.py` | US-023, US-031, US-032, US-033, US-083, US-115, US-116, US-119 |
| `api/tests/architecture/test_core_does_not_import_modules.py` | US-034 |
| `api/tests/architecture/test_core_import_direction.py` | US-014, US-015 |
| `api/tests/architecture/test_core_import_graph.py` | US-029 |
| `api/tests/architecture/test_core_jobs_imports.py` | US-113 |
| `api/tests/architecture/test_crypto_bus_importers.py` | US-077 |
| `api/tests/architecture/test_error_responses_in_openapi.py` | US-017 |
| `api/tests/architecture/test_every_route_has_role.py` | US-035 |
| `api/tests/architecture/test_find_forbidden_imports.py` | US-022 |
| `api/tests/architecture/test_gates_registered.py` | US-085 |
| `api/tests/architecture/test_import_analyzer.py` | US-031 |
| `api/tests/architecture/test_list_routes_use_page_params.py` | US-019 |
| `api/tests/architecture/test_list_rows_without_sensitive_fields.py` | US-070 |
| `api/tests/architecture/test_members_encrypted_at_rest.py` | US-069 |
| `api/tests/architecture/test_no_create_all.py` | US-012, US-118 |
| `api/tests/architecture/test_no_cross_models.py` | US-022, US-054, US-084, US-111, US-112, US-119 |
| `api/tests/architecture/test_no_cross_schema_sql.py` | US-091 |
| `api/tests/architecture/test_no_direct_now.py` | US-013 |
| `api/tests/architecture/test_no_os_environ.py` | US-011 |
| `api/tests/architecture/test_no_physical_delete_users.py` | US-041 |
| `api/tests/architecture/test_no_physical_delete.py` | US-076 |
| `api/tests/architecture/test_no_plaintext_at_rest.py` | US-031 |
| `api/tests/architecture/test_no_sensitive_in_logs.py` | US-018 |
| `api/tests/architecture/test_payment_method_codes.py` | US-056 |
| `api/tests/architecture/test_payments_dependencies.py` | US-098 |
| `api/tests/architecture/test_payments_does_not_import_memberships.py` | US-085, US-095 |
| `api/tests/architecture/test_payments_immutability_code.py` | US-096 |
| `api/tests/architecture/test_read_modules.py` | US-108, US-110 |
| `api/tests/architecture/test_route_guard_unit.py` | US-035 |
| `api/tests/architecture/test_routes_under_api_v1.py` | US-020 |
| `api/tests/architecture/test_ruff_banned_api.py` | US-002 |
| `api/tests/architecture/test_service_import_cycles.py` | US-071, US-073, US-082 |
| `api/tests/architecture/test_service_import_graph.py` | US-085 |
| `api/tests/architecture/test_settings_no_secrets.py` | US-054, US-055 |


## Brechas arquitectónicas detectadas y propuesta para cerrarlas

Cada brecha se decide en el gate. La propuesta es la opción por defecto; mientras no se apruebe, la historia no empieza.

- **G-01 · Contexto de actor y lote sin lugar neutral en `core` (US-029; lo usan también US-015, US-016, US-034, el worker y el CLI).**
  - Problema:
    - `crypto_ops` y la auditoría necesitan saber quién actúa.
    - Si el contextvar vive en `core/audit.py`, se cierra el ciclo `core/crypto` → `core/db` → `core/audit` → `core/crypto`, porque la auditoría usa `digest` (N-06).
  - Propuesta:
    - Crear `core/context.py`, que solo usa la biblioteca estándar, con `SYSTEM_USER_ID`, `current_actor`, `current_batch`, `request_id_var`, `actor_scope()` y `batch_scope()`.
    - `core/audit.py` importa `core/crypto/digest.py` (sin dependencias), no el bus completo.
    - `core/db.py` no importa la auditoría; `install_audit_listeners()` se llama desde `create_app`, el worker, el CLI y `conftest`.
    - Se agrega `core/context.py` a la estructura de `CLAUDE.md`.
- **G-02 · `current_user` en `core/security` necesitaría `auth.service` (US-034).**
  - Problema: core dependería de un módulo y habría un ciclo con `auth.service`, que importa `core.security`.
  - Propuesta:
    - `core/security` define `Principal(user_id, role, member_id)`, el `Protocol` `PrincipalLoader` y `register_principal_loader()`.
    - `auth.service.get_principal` lo implementa y se registra al arrancar.
    - El arranque falla si no hay cargador.
    - El rol que vale es el de la base, no el del claim. `SYSTEM_USER_ID` se rechaza.
    - Se agrega el puerto a la tabla de `05_service_design.md` sección 1.
- **G-03 · Ciclos de imports entre services sin regla documentada (US-085; también US-071, US-082 y, en v0.4, US-163).**
  - Ciclos detectados: `memberships` ↔ `payments`, `members` ↔ `memberships`, `plans` ↔ `memberships` y `members` ↔ `classes`.
  - Propuesta: una regla nueva en `CLAUDE.md`, "Dependencias mutuas entre services", con tres puntos:
    1. Si el sentido minoritario solo valida o consulta, se invierte con un puerto que registra el módulo dueño al importarse, igual que `subscribe`. Por ejemplo, `payments.set_membership_gate(...)` devuelve `MembershipPayability(exists, cancelled, member_id)` (US-085, con US-095 ya alineada).
    2. Si es una lectura de presentación (members → memberships para `status_for`; plans → memberships para `count_active_by_plan`; members → classes), se permite un import perezoso del módulo (`from app.modules.x import service as x_service` dentro de la función), con un comentario. Solo vale para los pares de una lista blanca.
    3. `test_service_import_graph.py` hace cumplir las dos cosas.
  - Esto se documenta en ADR-001 (US-119).
- **G-04 · Lecturas compuestas fuera de los módulos de lectura (US-071; el mismo patrón aparece en US-091, US-098, US-099, US-137 y US-139).**
  - Problema: la lista de socios con `plan_name` recorre members → memberships → plans, y la regla de no encadenar tres services está escrita para acciones.
  - Propuesta: precisar en `03_context_map.md` sección 5 que una **lectura** puede recorrer aristas que ya existen hasta profundidad 2, con consultas por lote, sin escribir ni emitir eventos y llamando a un solo service desde el router. La prohibición de tres services sigue para escrituras.
  - En concreto:
    - `memberships.service.status_for` devuelve `{status, plan_id, plan_name}`, resolviendo los nombres con `plans.service.names_for`.
    - US-092 agrega `member_ids_by_status(statuses, plan_id) -> set[UUID]`. No incluye el valor `none`; Members lo resuelve como complemento.
- **G-05 · Historial del socio con membresías y pagos (US-106, N-31).**
  - Problema: sin un cambio de modelo, `members` tendría que encadenar memberships, payments y audit, y además members ↔ payments quedarían en ciclo.
  - Propuesta:
    - Columna `audit_log.subject_member_id`, llenada por el hook a partir del atributo de clase `__audit_subject__` (`Member` → `id`, `Membership` → `member_id`, `Payment` → `member_id`), dentro de la serialización canónica.
    - Más `payments.member_id` (ya en `0010`).
    - `GET /members/{id}/audit` pasa a ser una sola consulta: `audit.service.list_for_subject(member_id)`.
    - Se cubre con `test_audit_subject.py`.
  - Alternativa descartada: un módulo nuevo de solo lectura `modules/history`, que `CLAUDE.md` no prevé.
- **G-06 · El model de `worker.job_runs` no tiene ubicación (US-113).**
  - Problema: lo escribe el worker y lo lee `/health` del api. `CLAUDE.md` no tiene `worker/models.py`, y ponerlo ahí obligaría al api a importar APScheduler.
  - Propuesta:
    - `core/jobs.py`, con `JobRun`, `claim_run`, `finish_run` y `last_run`, siguiendo el precedente de `core/audit.py`.
    - Solo lo importan `app/worker/**` y el chequeo de salud.
    - Se agrega a la estructura de `CLAUDE.md`.
- **G-07 · El bus no tiene SHA-256 de archivo en streaming ni verificación de archivos `age` (US-115; v1.0 lo reutiliza en US-196).**
  - Propuesta:
    - `core/crypto/archive.py`, expuesto en el bus como `digest_file(path)` y `verify_age_archive(path, identity_path)`.
    - Llama al binario `age` (BSD-3) por `subprocess`, solo desde `core/crypto`, y la salida se descarta.
    - Queda en `crypto_ops` con el verbo `verify` y la clase de dato `backup.archive`, que se agrega a `registry.py`.
    - La imagen del api incluye `age`.
- **G-08 · Alertas internas sin puerto (US-126, v0.2; afecta a US-136 y US-141).**
  - Problema: N-34 pone `core/alerts.py` → `TelegramChannel`, pero el canal vive en `modules/notifications`.
  - Propuesta:
    - `core/alerts.py` define el `Protocol` `AlertSink`, `register_sink()`, `alert(kind, text)` y un `LogAlertSink` por defecto.
    - `TelegramAlertSink`, con httpx directo, vive en `modules/notifications/channels/telegram.py` y se registra en `main.py` y `worker/main.py`.
    - Telegram deja de ser adaptador de `NotificationChannel`.
- **G-09 · La rotación de `attachment.sensitive` no llega a los archivos (US-145, v0.3).**
  - Problema: el recifrado por lotes de US-030 solo recorre columnas. Sin solución, esa llave nunca se retira.
  - Propuesta:
    - Un puerto `Reencryptor` (`count_pending`, `reencrypt_batch`) en `core/crypto/registry.py`, que cada módulo registra al importarse.
    - `attachments.key_id` en `0050`.
    - Mientras no se apruebe, se responde 409 `rotation_not_supported` para esa clase.
- **G-10 · Ciclo `members` ↔ `classes` para el filtro de última asistencia (US-163, v0.4).** Se cierra con la regla de G-03: import perezoso en la lista blanca.

## Historias NEEDS_REFINEMENT y su pregunta

Cada pregunta trae una propuesta por defecto, y los desgloses ya están escritos con esa propuesta. Si el gate la acepta, la historia pasa a READY sin cambiar las horas.

v0.1:
- **US-004 (licencias):** ¿se agrega `PSF-2.0` a la lista permitida, como N-49 hizo con 0BSD, ISC y OFL-1.1?
  - Motivo: `typing_extensions`, obligatoria para Pydantic, FastAPI y SQLAlchemy, es PSF-2.0, y `greenlet` declara MIT y PSF. Sin esto, `pip-licenses --allow-only` falla desde la primera corrida.
  - Por defecto: sí.
  - De paso: confirmar MPL-2.0 sin modificar para `certifi` y `axe-core`.
- **US-008 (scripts de gate):** ¿qué veredictos acepta `validate-impact-analysis.sh`?
  - Por defecto:
    - pasan APROBADO, APROBADO CON OBSERVACIONES y VERDE;
    - AMARILLO pasa solo con `--allow-amber`;
    - el resto falla.
  - Motivo: `00b_impact_analysis.md` trae AMARILLO.
- **US-022 (prueba de imports cruzados):** ¿un módulo puede importar `schemas.py` y `exceptions.py` de otro para tipar y capturar lo que devuelve su service?
  - Por defecto: sí. La prueba prohíbe solo `models` ajenos, `models` desde un `router.py` y el router de otro módulo.
- **US-024 (tablas crypto):** ¿`crypto_keys.rotate_by` es el usuario que rotó (`uuid`) o una fecha límite para rotar?
  - Por defecto: el usuario. Si después se quiere una fecha límite, entra como `rotate_before` en EP-18.
- **US-030 (rotación de llave):** ¿los blobs que la auditoría guarda en `before`/`after`, que son inmutables, impiden retirar la llave anterior?
  - Por defecto: no cuentan.
  - La llave `retired` conserva su material envuelto, pero el bus no descifra con ella.
  - El historial muestra "valor cifrado modificado".
- **US-056 (medios de pago):** el coach lee las etiquetas de medios de pago "por el endpoint de pagos", que no existe.
  - Por defecto: `GET /api/v1/payments/methods` (admin y coach), que delega en `settings.service.payment_methods()`.
- **US-057 (política de privacidad):** N-18 no trae `effective_from` ni `policy_url`, ni dice si `policy_text` es obligatorio ni el rango de `retention_years`.
  - Por defecto:
    - `policy_text` obligatorio, de 1 a 20.000 caracteres;
    - `retention_years` de 1 a 20;
    - "vigente desde" se toma del `updated_at` de la sección.
- **US-061 (TopBar):** el coach debe ver el nombre del gimnasio, pero `GET /settings/gym` es solo para admin.
  - Por defecto: agregar `gym_name` a `GET /auth/me` (US-045), con "APEX" como respaldo.
- **US-062 (layouts):** la historia pide un menú de portal de 6 destinos a 390 px; el diseño dibuja 5 en una columna de 600 px como máximo.
  - Por defecto: seguir el diseño, con los destinos en `PORTAL_TABS`.
- **US-110 (últimos movimientos):** dos preguntas.
  - ¿Se agrega `auth.users.display_name`, con "Sistema" para `SYSTEM_USER_ID`, para frases como "Ana P. registró…"?
    - Por defecto: sí.
    - Si se rechaza, se usa la parte local del correo.
  - ¿Se excluyen las entradas de `SYSTEM_USER_ID`, para que el job de vencimientos no llene los 10 movimientos?
    - Por defecto: sí.

v0.2 a v1.0:
- **US-123 (preferencias de canal, N-33):** un socio sin fila de preferencias pero con `data_consent_at`, ¿recibe correo automático?
  - Por defecto: no. El correo exige opt-in explícito y `data_consent_at`; sin filas de preferencias, solo `whatsapp_link`.
- **US-160 (descontar clases):** cuando una tiquetera llega a 0 clases con `end_date` futuro, ¿se recorta `end_date` a la fecha del consumo, guardando el original en `original_end_date`?
  - Por defecto: sí.
  - La renovación empieza al día siguiente.
  - Al devolver la clase se restaura el fin solo si no se solapa con otra membresía.
- **US-166 (WODs):** N-46 crea el catálogo `wods.benchmarks`, pero ninguna historia lo mantiene. ¿Se agrega un CRUD mínimo `/benchmarks` (admin y coach) y `cli seed-benchmarks`, con el `score_type` del WOD igual al de su benchmark?
  - Por defecto: sí.
- **US-181 (récords derivados):** si se corrige un resultado que ya derivó un RM, ¿se marca el récord como invalidado?
  - Por defecto: sí. `WodResultSuperseded` pone `invalidated_at` en el récord, sin borrarlo.
- **US-197 (CBOM en v1.0):** ¿se mantiene CycloneDX como formato adicional de `GET /crypto/cbom`?
  - Por defecto: sí, como extensión, sin cambiar el JSON de US-146.

## Contradicciones entre historias que el gate debe resolver

Los desgloses ya siguen la opción indicada. Hay que corregir las historias originales para que coincidan.

Contratos de services y eventos:
- **US-016 y SYSTEM_ACTOR_ID:**
  - US-016 todavía nombra `SYSTEM_ACTOR_ID`, y US-029, US-077 y US-105 dejan `user_id` nulo para el worker y el CLI. Con N-15 es siempre `SYSTEM_USER_ID` o `--as`.
  - Las rutas sin JWT que escriben en tablas auditadas (login con bloqueo, activación, reset) abren `actor_scope` con el dueño de la cuenta o con `SYSTEM_USER_ID`.
- **El hook de auditoría (US-016) necesita cuatro cosas:**
  - soportar `__audit_redact__`, para que `password_hash` quede como `"***"`;
  - soportar `__audit_exclude__`, para `last_login_at`;
  - auditar en `update` solo las columnas que cambiaron;
  - guardar el blob `apx1.` de las columnas `Encrypted`, nunca el texto en claro (guarda `PlaintextInAuditError`).
  - Además, `crypto_keys.wrapped_material` no puede llegar a la auditoría.
- **Login (US-107):** el login emite `LoginAttempted(user_id, result)` y US-107 se suscribe. Si `login` llamara a `audit.record` directo, como dice el texto de US-107, la fila quedaría duplicada.
- **Revelar un dato (`SensitiveFieldRevealed`):** el catálogo del dominio lo suscribe a audit, pero US-074 escribe la fila `reveal` directamente. No hay suscriptor; si lo hubiera, la fila se duplicaría.
- **Contratos que se fijaron en el desglose y deben quedar en las historias dueñas:**
  - US-069: `members.service.get_ref`/`ref`, `ensure_exists` e `id_by_document`.
  - US-070: `members.service.search_ids` y `names_for`, que incluye a los dados de baja y el sexo; US-171 lo reutiliza y no crea `public_names`.
  - US-079: `plans.service.names_for`, `get_including_deleted` y `get(for_share=True)`; US-084 debe leer el plan con ese bloqueo.
  - US-084: `memberships.service.get_payment_target` y `refs_for`.
  - US-086 y US-095: `payments.service.sum_not_voided`. Hay que hacer `flush` del pago antes de emitir `PaymentRegistered`.
  - US-041: `auth.service.names_for`, que devuelve el correo, o `display_name` si se aprueba US-110; además `get_principal`, `ids_by_email` y `active_admin_id_by_email`.
- **Lecturas de Settings:**
  - Memberships lee los límites con `settings.service.memberships_policy()` (US-058), no con `get_section`.
  - La política de privacidad se lee con `current_privacy_version()` y el campo `policy_version` (US-057). US-149 decía `current_version`.
- **Venta con fecha pasada:** `sell(..., max_retroactive_days: int | None)`. El router pasa el valor de Settings, y el seed y la importación pasan `None` (N-24).
- **Pagar una membresía cancelada:** responde 409 `membership_cancelled` (US-095), no 422 como dice US-090.
- **Rangos de Settings:** US-058 trae otros valores; mandan los de N-18 (0 a 180 días y 0 a 12 congelaciones).
- **Nombre del campo de verificación:** es `broken_at_seq`, no `broken_seq` (US-104).
- **Clave del tablero:** es `notifications_today`, no `to_notify_today` (US-132).

Seguridad y configuración:
- **Códigos 401 (US-034 y US-043):** 401 `token_expired` solo para un access token vencido con firma válida, y 401 `unauthorized` para todo lo demás. `invalid_token` queda reservado para el 400 de los tokens de un solo uso (N-11).
- **Funciones de token en `core.security` (US-033):** expone `new_opaque_token()` y `hash_opaque_token()`. Nadie genera hoy la llave JWT Ed25519; queda en el README de operación, o como subcomando de `cli init-keys` si se pide en US-023.
- **Variables de entorno (US-011):** hay que reconciliarlo con US-007, US-035, US-036 y US-037.
  - `JWT_PUBLIC_KEY_PATH` pasa a opcional (se deriva de la privada).
  - `CORS_ORIGINS` es `list[str]`, sin `AnyHttpUrl`.
  - Se agregan `ENV`, `TRUSTED_PROXIES`, `COOKIE_SECURE` y `FRONT_BASE_URL`.
  - `DATABASE_URL` es `SecretStr`.
  - La lista `NON_API_ENV_VARS` evita que `extra="forbid"` rompa el arranque.
  - Las variables del admin inicial se llaman `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` (DECISIONES E; un solo uso, se borra del `.env` tras el seed), no `SEED_ADMIN_*` (US-007 original) ni `APEX_SEED_ADMIN_*` (US-041 original).
- **Nombres de permisos del front:** son `members.*` (US-040). US-066 y US-072 los escriben en singular.
- **Nginx:**
  - sobrescribe `X-Forwarded-For` con `$remote_addr`;
  - no registra en el log las query strings de `/api/v1/tv/`, `/tv`, `/restablecer/` ni la `q` de `/members`;
  - sirve `index.html` con `no-store`, por el nonce de la CSP;
  - sube `client_max_body_size` a 6 MB solo en la ruta de subida (v0.3), porque el multipart de un archivo de 5 MB pasa de 5 MB.
- **Archivos `.pem` en la imagen (US-039):** "ningún `.pem` en la imagen" es imposible, por las CA públicas de `certifi`. Se buscan llaves privadas por contenido en toda la imagen y cualquier `.pem` o `.key` bajo `/app`.
- **ShellCheck:** es GPL. Los scripts se revisan con `bash -n`.
- **`defusedxml`:** su licencia (PSF) no está permitida. La importación de Excel limita el archivo a 10 MB y 5.000 filas.

v0.2 en adelante:
- **Canal Telegram (N-34):** US-123 y US-193 deben quitar `telegram` de los canales del socio. El CHECK de `notification_rules.channel` empieza en (`email`, `whatsapp_link`) y EP-25 le agrega `push`.
- **`notifications.membership_id` (N-37):** nace `NOT NULL` en v0.2, y EP-25 lo vuelve nulo.
- **Trigger de `crypto_keys`:** EP-15 y EP-26 necesitan una migración en su rango que reemplace la función de guarda de `0003`, para poder cambiar `wrapped_material` y `provider` al migrar de proveedor o re-envolver.
- **`KeyProvider`:** `wrap(key_ref, dek)` y `unwrap(key_ref, wrapped)`. Cada DEK se abre con el proveedor de su fila, para que una migración pueda quedar a medias.
- **Contratos entre EP-21 y EP-22:** EP-21 expone `classes.service.attendees`, que excluye las asistencias con `removed_at`, el filtro `wod_id` en la lista de sesiones y un único `PATCH /class-sessions/{id}` (N-41).
- **Correo de activación de la cuenta del portal (US-185):** usa el propósito `auth_link` y se envía directo (N-21, N-36), no `portal_account` encolado.
- **Firma de backups (US-196):** usa `digest_file` (G-07). La firma la pone un job del worker, no el contenedor de backup.

## Ruta crítica de v0.1 (por dependencias técnicas)

1. US-001 → US-002 → US-005.
2. US-011 → US-012 → US-013, US-014 → US-015 (con `core/crypto/digest.py` de US-027, que se entrega antes) → US-016.
3. US-023 → US-024 → US-025, US-026 → US-028 → US-029 (G-01).
4. US-032, US-033 → US-034 (G-02) → US-041.
5. US-054 → US-058.
6. US-069 → US-070.
7. US-078 → US-079.
8. US-083 → US-084 ↔ US-095 → US-096 → US-085 (G-03) → US-086 → US-087 → US-092.
9. US-113 → US-094.
10. US-106 (G-05), US-108 → US-110.

En paralelo desde el paso 2: EP-06 (front compartido), EP-03 y EP-00 restante.

## Verificación

El script [`verificar.mjs`](verificar.mjs) comprueba lo siguiente:
- cada historia de v0.1 tiene su archivo;
- cada archivo tiene una línea de estado válida, la línea `**Total: NN h**`, la sección "Definición de hecho" y las secciones obligatorias, y no tiene tablas;
- cada `BREAKDOWN.md` tiene una línea por historia y su total coincide con la suma.

También extrae los endpoints y los tests de arquitectura de este índice. Se corre así:

```
node docs/ddd/08_implementation_breakdown/verificar.mjs .
```

Resultado de la última corrida: 119 de 119 archivos de v0.1 y 13 de 13 `BREAKDOWN.md`, sin errores.
