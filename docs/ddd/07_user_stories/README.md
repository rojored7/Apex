# 07 · Historias de usuario

Fecha: 21 de octubre de 2026.
Entradas: `02_domain_model.md` (modelo de dominio), `04_architecture_decision.md` y `05_service_design.md` (arquitectura), `06_epics/` (épicas), `01_product_discovery.md` y `03_context_map.md` (reglas RN-01 a RN-17, relaciones y eventos), `DECISIONES.md` (manda sobre todo lo anterior), `CLAUDE.md`, `docs/design/ROUTES.md` y `docs/design/SCREENS-INDEX.md`.

## Resumen

- Son **199 historias** (US-001 a US-199) en 27 carpetas, una por épica (EP-00 a EP-26), con **690 puntos** en la escala 1, 2, 3, 5, 8.
- **v0.1 (EP-00 a EP-13): 119 historias, 379 puntos.** Están completamente refinadas y en estado **"Lista para sprint"**. Cada una trae criterios de aceptación numerados, al menos 3 escenarios BDD (camino feliz, error de validación y rol denegado; en las técnicas, la falla del gate o de la regla) y la "Definición de listo" marcada.
- **v0.2 a v1.0 (EP-14 a EP-26): 80 historias, 311 puntos.** Están en estado **"Criterios completos; BDD solo de flujo principal"**. Los criterios de aceptación están completos y se pueden verificar. Los escenarios BDD cubren el camino feliz y el error principal (al menos 2). El rol denegado puede quedar solo como criterio de aceptación. No llevan "Definición de listo": se refinan al planear su versión.
- Las épicas técnicas (EP-00, EP-01, EP-02, EP-03 y EP-06) tienen como actor al **equipo**. Las demás son slices verticales: cada historia de negocio incluye backend y front cuando la pantalla existe.
- Ninguna historia inventa reglas de negocio. Cuando una historia necesitó una decisión que no está en el dominio ni en `DECISIONES.md`, la dejó en su sección "Supuestos". Todas esas decisiones quedan recogidas en "Preguntas abiertas nuevas", al final de este archivo.
- Este backlog supone que el gate aprueba **D1 / S1**: el front se construye en `web/`, dentro de este repositorio. El párrafo "Alcance" de `CLAUDE.md` dice hoy lo contrario. Si el gate no aprueba S1, la parte de front de cada historia sale del alcance y EP-06 sale completa.

## Formato de cada historia

Archivo `EP-NN-<slug>/US-NNN-<slug>.md`. Cada historia lleva estas secciones, en este orden:

- Encabezado con épica, bounded context, versión, actor, tamaño, prioridad, nivel de refinamiento y pantalla.
- Historia ("Como ... quiero ... para ...").
- Contexto de dominio: aggregate, reglas RN-xx y decisiones Qxx, eventos que emite y consume, funciones puras.
- Alcance, separado en backend y front.
- Criterios de aceptación numerados.
- Escenarios BDD en Gherkin con `# language: es` (Dado / Cuando / Entonces).
- Endpoints, con rol, entrada, salida y códigos.
- Pantalla del diseño.
- Notas técnicas: migración, trigger, función pura a probar, pruebas y archivos.
- Supuestos.
- Dependencias.
- INVEST verificado.
- Definición de listo (solo v0.1) y Definición de terminado.

Las reglas transversales quedan escritas en los criterios de cada historia que las toca:

- **Listas:** paginación con `limit` (1 a 200, 25 por defecto) y `offset`.
- **Dinero:** entero en COP.
- **Fechas:** UTC en el API y `today_bogota()` para calcular "hoy".
- **Roles:** cada endpoint declara el suyo.
- **Pagos:** inmutables.
- **Borrado:** lógico en socios, planes y usuarios.
- **Datos sensibles:** siempre cifrados por el bus.
- **Auditoría:** las tablas auditadas llevan `__audited__ = True`.

Las rutas usan el contrato de `05_service_design.md` sección 4, con las correcciones de `DECISIONES.md`. Por ejemplo, renovar es `POST /members/{id}/memberships` con `renew: true`, y registrar un pago es `POST /memberships/{id}/payments`.

## Conteo por épica

v0.1:
- EP-00 · Cimientos del repositorio: 10 historias, 31 puntos.
- EP-01 · Núcleo compartido: 12 historias, 31 puntos.
- EP-02 · Bus de criptografía: 9 historias, 36 puntos.
- EP-03 · Seguridad de la plataforma: 9 historias, 21 puntos.
- EP-04 · Identidad y acceso: 13 historias, 38 puntos.
- EP-05 · Configuración del gimnasio: 5 historias, 12 puntos.
- EP-06 · Layout y componentes front: 10 historias, 36 puntos.
- EP-07 · Padrón de socios: 9 historias, 34 puntos.
- EP-08 · Catálogo de planes: 5 historias, 15 puntos.
- EP-09 · Membresías: 12 historias, 42 puntos.
- EP-10 · Pagos: 7 historias, 20 puntos.
- EP-11 · Auditoría: 6 historias, 20 puntos.
- EP-12 · Tablero de inicio: 3 historias, 9 puntos.
- EP-13 · Puesta en marcha y continuidad: 9 historias, 34 puntos.

v0.2:
- EP-14 · Avisos de vencimiento: 13 historias, 44 puntos.
- EP-15 · Custodia de llaves con OpenBao: 4 historias, 21 puntos.
- EP-16 · Recibos y exportaciones: 3 historias, 13 puntos.

v0.3:
- EP-17 · Auditoría firmada: 3 historias, 13 puntos.
- EP-18 · Administración de llaves: 4 historias, 14 puntos.
- EP-19 · Adjuntos y autorización de datos: 5 historias, 18 puntos.
- EP-20 · Acceso cifrado con TLS híbrido: 2 historias, 8 puntos.

v0.4:
- EP-21 · Clases, horario y check-in: 11 historias, 39 puntos.

v0.5:
- EP-22 · Entrenamiento (movimientos, WODs, resultados): 10 historias, 41 puntos.
- EP-23 · Pantalla de TV: 3 historias, 8 puntos.

v0.6:
- EP-24 · Perfil del atleta: 7 historias, 26 puntos.

v1.0:
- EP-25 · Portal del socio: 11 historias, 45 puntos.
- EP-26 · Cierre criptográfico post-cuántico: 4 historias, 21 puntos.

## Índice y trazabilidad (historia → épica → bounded context → versión → pantalla)

| Historia | Título | Épica | Bounded context | Versión | Pantalla | Tamaño |
|---|---|---|---|---|---|---|
| [US-001](EP-00-cimientos/US-001-repositorio-git-y-estructura.md) | Como equipo quiero un repositorio git con `main` protegida y la estructura de carpetas acordada para que todo el trabajo posterior tenga un lugar fijo y revisado | EP-00 | ninguno (terreno) | v0.1 | ninguna | 2 |
| [US-002](EP-00-cimientos/US-002-proyecto-api-uv-ruff-mypy-pytest.md) | Como equipo quiero el proyecto `api` con uv, ruff con `banned-api`, mypy estricto, pytest y pre-commit para que el código defectuoso o que salta el bus de criptografía no pase del primer commit | EP-00 | ninguno (terreno) | v0.1 | ninguna | 3 |
| [US-003](EP-00-cimientos/US-003-pipeline-ci.md) | Como equipo quiero un pipeline de CI que corra lint, tipos, pruebas con PostgreSQL 16 y el build de imágenes en cada PR para que nada roto llegue a `main` | EP-00 | ninguno (terreno) | v0.1 | ninguna | 3 |
| [US-004](EP-00-cimientos/US-004-chequeo-de-licencias-y-notice.md) | Como equipo quiero que CI rechace cualquier dependencia con licencia prohibida y mantenga un `NOTICE` para que el gimnasio nunca quede atado a obligaciones GPL, LGPL, AGPL, BSL o SSPL | EP-00 | ninguno (terreno) | v0.1 | ninguna | 3 |
| [US-005](EP-00-cimientos/US-005-dockerfile-api-y-compose.md) | Como equipo quiero la imagen del api y los archivos de Compose de producción y desarrollo con healthchecks para que el sistema se levante con un solo comando en el servidor del gimnasio y en cualquier máquina de desarrollo | EP-00 | ninguno (terreno) | v0.1 | ninguna | 5 |
| [US-006](EP-00-cimientos/US-006-nginx-e-imagen-del-front.md) | Como equipo quiero un Nginx que sirva el build del front y haga proxy de `/api/` al api, empaquetado en su imagen, para que el navegador use un solo origen y las subidas queden limitadas a 5 MB | EP-00 | ninguno (terreno) | v0.1 | ninguna | 3 |
| [US-007](EP-00-cimientos/US-007-env-example-y-readme.md) | Como equipo quiero un `.env.example` completo y un README de arranque en 5 minutos para que cualquiera levante el proyecto sin preguntar qué variables faltan | EP-00 | ninguno (terreno) | v0.1 | ninguna | 1 |
| [US-008](EP-00-cimientos/US-008-scripts-de-gate-del-flujo.md) | Como equipo quiero los cuatro scripts de gate del flujo en `scripts/workflow/` para que cada slice, checkpoint y cierre de wave se verifique automáticamente y no a mano | EP-00 | ninguno (terreno) | v0.1 | ninguna | 3 |
| [US-009](EP-00-cimientos/US-009-esqueleto-del-front.md) | Como equipo quiero el esqueleto de `web/` con Vite, React 19, TypeScript estricto, pruebas, tokens de diseño y fuentes locales para que cada pantalla nueva nazca con el diseño aprobado y sin colores inventados | EP-00 | ninguno (terreno) | v0.1 | ninguna | 5 |
| [US-010](EP-00-cimientos/US-010-componentes-base-button-field-statustag.md) | Como equipo quiero los componentes base `Button`, `Field` y `StatusTag` accesibles y probados para que los primeros formularios y listas se construyan sobre piezas comunes y no con HTML suelto | EP-00 | ninguno (terreno) | v0.1 | ninguna (base) | 3 |
| [US-011](EP-01-nucleo-compartido/US-011-configuracion-desde-env.md) | Como equipo quiero toda la configuración en `Settings` leída desde `.env` y validada al arrancar para que el sistema nunca arranque a medias con una variable faltante | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-012](EP-01-nucleo-compartido/US-012-base-de-datos-y-alembic-multiesquema.md) | Como equipo quiero el acceso asíncrono a PostgreSQL con columnas comunes, un esquema por contexto y Alembic multiesquema para que cada módulo tenga su espacio y toda tabla nazca con `id`, `created_at`, `updated_at` y `created_by` | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 3 |
| [US-013](EP-01-nucleo-compartido/US-013-reloj-y-fecha-de-bogota.md) | Como equipo quiero un puerto `Clock` con reloj de sistema, reloj congelado y `today_bogota()` para que "hoy" sea siempre la fecha civil de Bogotá y las reglas de fechas se prueben sin esperar días | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-014](EP-01-nucleo-compartido/US-014-bus-de-eventos-transaccional.md) | Como equipo quiero un bus de eventos en memoria que ejecute los handlers en la misma transacción del emisor para que vender, cobrar y activar sean atómicos sin acoplar los módulos | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 3 |
| [US-015](EP-01-nucleo-compartido/US-015-tabla-de-auditoria-y-cadena-de-hashes.md) | Como equipo quiero la tabla de auditoría append-only con su cadena de hashes y serialización canónica para que cualquier fila alterada rompa la cadena y se pueda demostrar | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 3 |
| [US-016](EP-01-nucleo-compartido/US-016-hook-de-auditoria-after-flush.md) | Como equipo quiero que toda tabla marcada `__audited__ = True` escriba su auditoría automáticamente en el `after_flush` para que ningún módulo pueda olvidarse de auditar un cambio | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 5 |
| [US-017](EP-01-nucleo-compartido/US-017-envelope-de-errores.md) | Como equipo quiero que todo error del API salga con el mismo envelope `{ error: { code, message, field?, existing_id? } }` para que el front muestre siempre el mensaje correcto en el campo correcto | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-018](EP-01-nucleo-compartido/US-018-logging-json-sin-datos-sensibles.md) | Como equipo quiero logs en JSON a stdout que nunca impriman campos cifrados ni tokens para que diagnosticar un problema no exponga datos personales | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-019](EP-01-nucleo-compartido/US-019-contrato-de-paginacion.md) | Como equipo quiero un contrato común de listas con `limit` y `offset` para que toda lista del API pagine igual y ninguna consulta devuelva miles de filas sin límite | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-020](EP-01-nucleo-compartido/US-020-create-app-migraciones-y-health.md) | Como equipo quiero `create_app()` que aplique las migraciones al arrancar y exponga `/health` para que el sistema no acepte tráfico con un esquema viejo y el operador sepa en un vistazo si está sano | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 3 |
| [US-021](EP-01-nucleo-compartido/US-021-exportacion-de-openapi.md) | Como equipo quiero que CI regenere `docs/openapi.json` y falle si el archivo versionado está desactualizado para que el front genere sus tipos siempre desde el contrato real | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-022](EP-01-nucleo-compartido/US-022-prueba-arquitectura-sin-models-cruzados.md) | Como equipo quiero una prueba de arquitectura que falle si un módulo importa los `models` de otro para que las fronteras entre bounded contexts no se rompan con el tiempo | EP-01 | core (db, events, audit hook) | v0.1 | ninguna | 2 |
| [US-023](EP-02-bus-de-criptografia/US-023-keyprovider-y-proveedor-local.md) | Como equipo quiero un puerto KeyProvider con un proveedor local de KEK para envolver las llaves de datos sin atar el código a un custodio concreto | EP-02 | Crypto | v0.1 | ninguna | 5 |
| [US-024](EP-02-bus-de-criptografia/US-024-tablas-crypto-keys-ops-jobs.md) | Como equipo quiero las tablas crypto_keys, crypto_ops y crypto_jobs para registrar qué llave protege cada clase de dato, cada uso del bus y el progreso de los trabajos masivos | EP-02 | Crypto | v0.1 | ninguna | 3 |
| [US-025](EP-02-bus-de-criptografia/US-025-cifrado-aes-gcm-y-formato-de-blob.md) | Como equipo quiero cifrar y descifrar campos con AES-256-GCM en un blob autodescriptivo para que ningún dato personal quede en claro en la base | EP-02 | Crypto | v0.1 | ninguna | 5 |
| [US-026](EP-02-bus-de-criptografia/US-026-indice-ciego-hmac.md) | Como equipo quiero un índice ciego HMAC-SHA-256 sobre el valor normalizado para buscar socios por documento, teléfono o correo sin descifrar la tabla | EP-02 | Crypto | v0.1 | ninguna | 3 |
| [US-027](EP-02-bus-de-criptografia/US-027-firma-y-verificacion-en-el-bus.md) | Como equipo quiero firmar y verificar datos por clase de dato a través del bus para que auditoría y backups usen firmas sin conocer la llave ni el algoritmo | EP-02 | Crypto | v0.1 | ninguna | 2 |
| [US-028](EP-02-bus-de-criptografia/US-028-tipos-de-columna-encrypted-y-blindindexed.md) | Como equipo quiero tipos de columna Encrypted y BlindIndexed para que un modelo declare un campo cifrado en una línea y nunca lo escriba en claro por error | EP-02 | Crypto | v0.1 | ninguna | 5 |
| [US-029](EP-02-bus-de-criptografia/US-029-bitacora-crypto-ops-por-lote.md) | Como equipo quiero que cada operación del bus quede en la bitácora crypto_ops, agrupada por lote cuando es masiva, para demostrar quién usó qué llave sin multiplicar escrituras | EP-02 | Crypto | v0.1 | ninguna | 3 |
| [US-030](EP-02-bus-de-criptografia/US-030-rotacion-de-llave-por-cli.md) | Como equipo quiero rotar la llave de una clase de dato por CLI con recifrado por lotes y progreso para responder a una sospecha de filtración sin dejar datos ilegibles | EP-02 | Crypto | v0.1 | ninguna | 8 |
| [US-031](EP-02-bus-de-criptografia/US-031-pruebas-de-arquitectura-criptografica.md) | Como equipo quiero pruebas de arquitectura que fallen si un módulo usa primitivas criptográficas fuera del bus o si un dato sensible queda en claro en la base | EP-02 | Crypto | v0.1 | ninguna | 2 |
| [US-032](EP-03-seguridad-de-la-plataforma/US-032-hash-de-contrasenas-argon2id.md) | Como equipo quiero hashear y verificar contraseñas con argon2id para que una base filtrada no revele las contraseñas del equipo ni de los socios | EP-03 | core/security | v0.1 | ninguna | 2 |
| [US-033](EP-03-seguridad-de-la-plataforma/US-033-jwt-ed25519.md) | Como equipo quiero emitir y validar JWT firmados con Ed25519 de 15 minutos y refresh tokens opacos de 7 días para que una sesión robada dure poco y un token manipulado nunca pase | EP-03 | core/security | v0.1 | ninguna | 3 |
| [US-034](EP-03-seguridad-de-la-plataforma/US-034-dependencias-current-user-y-require-role.md) | Como equipo quiero las dependencias current_user y require_role para que cada endpoint declare quién puede usarlo y el API lo haga cumplir siempre | EP-03 | core/security | v0.1 | ninguna | 3 |
| [US-035](EP-03-seguridad-de-la-plataforma/US-035-prueba-de-rutas-con-rol.md) | Como equipo quiero una prueba de arquitectura que falle si una ruta no declara rol para que ningún endpoint nuevo quede público por descuido | EP-03 | core/security | v0.1 | ninguna | 2 |
| [US-036](EP-03-seguridad-de-la-plataforma/US-036-rate-limit-login-y-forgot.md) | Como equipo quiero limitar a 5 intentos por minuto por IP el login y la recuperación para frenar la adivinación de contraseñas desde la LAN | EP-03 | core/security | v0.1 | ninguna | 2 |
| [US-037](EP-03-seguridad-de-la-plataforma/US-037-cors-cerrado.md) | Como equipo quiero CORS limitado a los orígenes de CORS_ORIGINS para que ninguna página ajena pueda llamar al API con la sesión de un usuario | EP-03 | core/security | v0.1 | ninguna | 1 |
| [US-038](EP-03-seguridad-de-la-plataforma/US-038-cabeceras-de-seguridad-y-csp.md) | Como equipo quiero que Nginx envíe las cabeceras de seguridad y una CSP con nonce para que el front no pueda ser incrustado ni ejecutar scripts inyectados | EP-03 | core/security | v0.1 | ninguna | 3 |
| [US-039](EP-03-seguridad-de-la-plataforma/US-039-gestion-de-secretos.md) | Como equipo quiero que ningún secreto viva en el código ni en las imágenes y que su presencia se valide al arrancar para que copiar el repositorio o una imagen no entregue las llaves del gimnasio | EP-03 | core/security | v0.1 | ninguna | 2 |
| [US-040](EP-03-seguridad-de-la-plataforma/US-040-matriz-de-permisos-del-front.md) | Como equipo quiero una matriz de permisos única en el front para que cada pantalla oculte las acciones que el rol no puede usar, sabiendo que el API vuelve a verificar | EP-03 | core/security | v0.1 | ninguna (todas) | 3 |
| [US-041](EP-04-identidad-y-acceso/US-041-cuentas-de-usuario-y-admin-inicial.md) | Como administrador quiero que existan las cuentas de usuario y un admin inicial creado por comando para poder entrar al sistema el primer día | EP-04 | Auth | v0.1 | ninguna | 3 |
| [US-042](EP-04-identidad-y-acceso/US-042-iniciar-sesion.md) | Como administrador o coach quiero iniciar sesión con mi correo y contraseña para usar el panel según mi rol | EP-04 | Auth | v0.1 | Login (/login) | 5 |
| [US-043](EP-04-identidad-y-acceso/US-043-renovar-sesion-automaticamente.md) | Como administrador o coach quiero que mi sesión se renueve sola mientras trabajo para no tener que volver a ingresar cada 15 minutos | EP-04 | Auth | v0.1 | ninguna (transversal) | 3 |
| [US-044](EP-04-identidad-y-acceso/US-044-cerrar-sesion.md) | Como administrador o coach quiero cerrar mi sesión para que nadie use mi cuenta en el computador de recepción | EP-04 | Auth | v0.1 | TopBar | 1 |
| [US-045](EP-04-identidad-y-acceso/US-045-ver-mi-cuenta-y-cambiar-contrasena.md) | Como administrador o coach quiero ver mi cuenta y cambiar mi contraseña para mantener mi acceso seguro sin pedirle ayuda a nadie | EP-04 | Auth | v0.1 | TopBar (menú de usuario) | 2 |
| [US-046](EP-04-identidad-y-acceso/US-046-listar-usuarios.md) | Como administrador quiero ver la lista de usuarios del sistema con su rol y estado para saber quién tiene acceso hoy | EP-04 | Auth | v0.1 | Usuarios (/sistema/usuarios) | 3 |
| [US-047](EP-04-identidad-y-acceso/US-047-crear-usuario-con-enlace-de-activacion.md) | Como administrador quiero crear la cuenta de un coach y obtener su enlace de activación para darle acceso sin conocer su contraseña | EP-04 | Auth | v0.1 | Usuarios | 3 |
| [US-048](EP-04-identidad-y-acceso/US-048-activar-cuenta-y-restablecer-contrasena.md) | Como coach quiero activar mi cuenta o restablecer mi contraseña con un enlace de un solo uso para entrar al sistema con una contraseña que solo yo conozco | EP-04 | Auth | v0.1 | Login (/restablecer/:token, /recuperar) | 5 |
| [US-049](EP-04-identidad-y-acceso/US-049-editar-y-dar-de-baja-usuario.md) | Como administrador quiero editar el correo o el rol de un usuario y darlo de baja cuando ya no trabaja en el box para que solo el equipo actual tenga acceso | EP-04 | Auth | v0.1 | Usuarios | 3 |
| [US-050](EP-04-identidad-y-acceso/US-050-bloquear-y-desbloquear-usuario.md) | Como administrador quiero bloquear y desbloquear a un usuario para cortar su acceso de inmediato ante cualquier sospecha | EP-04 | Auth | v0.1 | Usuarios | 3 |
| [US-051](EP-04-identidad-y-acceso/US-051-cerrar-sesiones-de-un-usuario.md) | Como administrador quiero cerrar todas las sesiones abiertas de un usuario para obligarlo a ingresar de nuevo si dejó la sesión abierta en otro equipo | EP-04 | Auth | v0.1 | Usuarios | 2 |
| [US-052](EP-04-identidad-y-acceso/US-052-reenviar-enlace-de-activacion.md) | Como administrador quiero generar de nuevo el enlace de activación o de recuperación de un usuario para entregárselo cuando lo perdió o venció | EP-04 | Auth | v0.1 | Usuarios | 2 |
| [US-053](EP-04-identidad-y-acceso/US-053-guardas-de-ruta-por-rol.md) | Como administrador o coach quiero que el front solo me deje entrar a las pantallas de mi rol para no ver opciones que no puedo usar | EP-04 | Auth | v0.1 | todas | 3 |
| [US-054](EP-05-configuracion-del-gimnasio/US-054-secciones-de-configuracion-validadas.md) | Como administrador quiero que la configuración del gimnasio se guarde por secciones validadas y auditadas para cambiarla sin romper el sistema y con rastro de quién la cambió | EP-05 | Settings | v0.1 | ninguna | 3 |
| [US-055](EP-05-configuracion-del-gimnasio/US-055-datos-del-gimnasio.md) | Como administrador quiero editar los datos de mi gimnasio desde la pantalla de configuración para que aparezcan correctos en el sistema sin pedirle a nadie que toque archivos | EP-05 | Settings | v0.1 | Config (/sistema/configuracion, pestaña gimnasio) | 3 |
| [US-056](EP-05-configuracion-del-gimnasio/US-056-etiquetas-de-medios-de-pago.md) | Como administrador quiero ponerle nombre visible a los medios de pago para que recepción los reconozca al registrar cada pago | EP-05 | Settings | v0.1 | Config (medios de pago) | 2 |
| [US-057](EP-05-configuracion-del-gimnasio/US-057-version-de-politica-de-privacidad.md) | Como administrador quiero registrar la versión vigente de la política de tratamiento de datos para saber qué texto aceptó cada socio | EP-05 | Settings | v0.1 | Config (privacidad) | 2 |
| [US-058](EP-05-configuracion-del-gimnasio/US-058-parametros-de-membresias.md) | Como administrador quiero ajustar cuántos días antes se considera "por vencer" y los límites de congelación para que las membresías sigan las políticas de mi gimnasio | EP-05 | Settings | v0.1 | Config (membresías) | 2 |
| [US-059](EP-06-layout-y-componentes-front/US-059-cliente-api-y-tipos-generados.md) | Como equipo quiero un cliente HTTP único con tipos generados desde el contrato para que el front nunca use un campo que el API no tiene | EP-06 | presentación (web/) | v0.1 | ninguna | 3 |
| [US-060](EP-06-layout-y-componentes-front/US-060-formato-de-dinero-y-fechas.md) | Como equipo quiero funciones únicas de formato de dinero y fechas para que todo monto y toda hora se vean igual y en hora de Bogotá | EP-06 | presentación (web/) | v0.1 | ninguna | 2 |
| [US-061](EP-06-layout-y-componentes-front/US-061-panel-layout-topbar-y-sidenav.md) | Como equipo quiero el layout del panel con barra superior y menú lateral filtrado por rol para que admin y coach naveguen igual en todas las pantallas | EP-06 | presentación (web/) | v0.1 | base de panel | 5 |
| [US-062](EP-06-layout-y-componentes-front/US-062-layouts-portal-gym-y-tv.md) | Como equipo quiero los layouts de portal, tablet del box y TV para que cada dispositivo tenga su marco listo antes de que lleguen sus pantallas | EP-06 | presentación (web/) | v0.1 | base de portal, tablet y TV | 5 |
| [US-063](EP-06-layout-y-componentes-front/US-063-tabla-paginacion-filtros-y-chips.md) | Como equipo quiero la tabla, la paginación por offset, la barra de filtros y los chips compartidos para que todas las listas paginen y filtren igual contra el API | EP-06 | presentación (web/) | v0.1 | P_Lista | 5 |
| [US-064](EP-06-layout-y-componentes-front/US-064-encabezado-pestanas-y-kpi.md) | Como equipo quiero el encabezado de página, las pestañas y la tarjeta KPI compartidos para que fichas y tablero se armen con piezas iguales | EP-06 | presentación (web/) | v0.1 | P_Ficha | 3 |
| [US-065](EP-06-layout-y-componentes-front/US-065-panel-lateral-y-modal-de-confirmacion.md) | Como equipo quiero el panel lateral y el modal de confirmación con motivo para que crear, editar y anular se hagan con el mismo patrón en todo el sistema | EP-06 | presentación (web/) | v0.1 | P_Formulario | 3 |
| [US-066](EP-06-layout-y-componentes-front/US-066-valor-enmascarado-e-historial.md) | Como equipo quiero el valor enmascarado con botón mostrar y el panel de historial para que los datos sensibles nunca se vean sin una acción explícita y auditada | EP-06 | presentación (web/) | v0.1 | P_Ficha | 3 |
| [US-067](EP-06-layout-y-componentes-front/US-067-mapa-de-rutas.md) | Como equipo quiero el mapa de rutas del front con habilitación por épica para que cada pantalla aparezca solo cuando su API existe | EP-06 | presentación (web/) | v0.1 | Mapa (referencia) | 2 |
| [US-068](EP-06-layout-y-componentes-front/US-068-temas-accesibilidad-y-capturas.md) | Como equipo quiero temas claro y oscuro, chequeo automático de accesibilidad y capturas por ancho para que ningún componente salga con contraste pobre, desbordes o colores literales | EP-06 | presentación (web/) | v0.1 | todas | 5 |
| [US-069](EP-07-padron-de-socios/US-069-registrar-socio.md) | Como recepción (administrador o coach) quiero registrar un socio nuevo con sus datos personales cifrados para tenerlo en el padrón sin exponer su cédula ni su teléfono | EP-07 | Members | v0.1 | Socio_Form (/socios/nuevo) | 8 |
| [US-070](EP-07-padron-de-socios/US-070-buscar-y-listar-socios.md) | Como recepción quiero buscar socios por nombre, documento, teléfono o correo para encontrar a cualquiera en segundos sin descifrar la tabla | EP-07 | Members | v0.1 | Socios_Lista (/socios) | 5 |
| [US-071](EP-07-padron-de-socios/US-071-filtrar-socios-por-estado-de-membresia-y-plan.md) | Como recepción quiero filtrar socios por estado de membresía y por plan para ver de un vistazo quién está al día, quién vence y quién debe plata | EP-07 | Members (+ Memberships) | v0.1 | Socios_Lista (chips) | 3 |
| [US-072](EP-07-padron-de-socios/US-072-lista-de-socios-en-celular.md) | Como dueño (administrador) o coach quiero consultar la lista de socios desde el celular para buscar a alguien cuando no estoy en recepción | EP-07 | Members | v0.1 | Socios_Movil | 2 |
| [US-073](EP-07-padron-de-socios/US-073-ver-ficha-del-socio.md) | Como recepción quiero abrir la ficha de un socio con sus datos sensibles enmascarados para ver su información sin exponerla a quien esté al lado | EP-07 | Members | v0.1 | Socio_Ficha (/socios/:id) | 3 |
| [US-074](EP-07-padron-de-socios/US-074-mostrar-dato-sensible-auditado.md) | Como recepción quiero mostrar en claro un dato sensible del socio cuando lo necesito para llamarlo o verificar su cédula, dejando constancia de quién lo vio | EP-07 | Members | v0.1 | Socio_Ficha (MaskedValue) | 3 |
| [US-075](EP-07-padron-de-socios/US-075-editar-socio.md) | Como recepción quiero editar los datos de un socio para corregir un teléfono o un correo sin perder el cifrado ni el rastro del cambio | EP-07 | Members | v0.1 | Socio_Form (/socios/:id/editar) | 5 |
| [US-076](EP-07-padron-de-socios/US-076-dar-de-baja-socio.md) | Como administrador quiero dar de baja a un socio con borrado lógico para sacarlo del padrón activo sin perder su historial de pagos ni su auditoría | EP-07 | Members | v0.1 | Socio_Ficha (modal) | 3 |
| [US-077](EP-07-padron-de-socios/US-077-contacto-para-avisos-auditado.md) | Como administrador quiero que cada descifrado del contacto de un socio para enviarle un aviso quede auditado con su propósito para demostrar el uso legítimo de sus datos | EP-07 | Members | v0.1 | ninguna | 2 |
| [US-078](EP-08-catalogo-de-planes/US-078-crear-plan.md) | Como administrador quiero crear un plan con precio en pesos y tipo por días o por clases para definir qué vende el gimnasio | EP-08 | Plans | v0.1 | Planes (/planes, SidePanel) | 5 |
| [US-079](EP-08-catalogo-de-planes/US-079-listar-planes.md) | Como administrador o coach quiero ver la lista de planes para saber qué se vende y a qué precio | EP-08 | Plans | v0.1 | Planes | 2 |
| [US-080](EP-08-catalogo-de-planes/US-080-editar-plan-sin-afectar-vendidas.md) | Como administrador quiero editar un plan sin afectar las membresías ya vendidas para subir precios sin cambiar lo pactado con cada socio | EP-08 | Plans | v0.1 | Planes (SidePanel) | 3 |
| [US-081](EP-08-catalogo-de-planes/US-081-activar-y-desactivar-plan.md) | Como administrador quiero activar y desactivar un plan para dejar de venderlo sin perder su historia | EP-08 | Plans | v0.1 | Planes | 3 |
| [US-082](EP-08-catalogo-de-planes/US-082-dar-de-baja-plan-sin-membresias-activas.md) | Como administrador quiero dar de baja un plan que no tiene membresías activas para limpiar el catálogo sin perder historia | EP-08 | Plans (+ Memberships) | v0.1 | Planes | 2 |
| [US-083](EP-09-membresias/US-083-reglas-puras-de-fechas-y-estados.md) | Como administrador quiero que el sistema calcule la fecha de fin, el estado y la cobertura de cada membresía con reglas fijas para no sacar fechas a mano ni equivocarme | EP-09 | Memberships | v0.1 | ninguna | 3 |
| [US-084](EP-09-membresias/US-084-vender-membresia.md) | Como administrador o coach quiero venderle una membresía a un socio para que quede registrado qué plan tiene, desde cuándo y hasta cuándo | EP-09 | Memberships | v0.1 | Membresia_Vender (/membresias/vender) | 5 |
| [US-085](EP-09-membresias/US-085-vender-con-primer-pago.md) | Como administrador o coach quiero registrar el primer pago en la misma venta para cobrar y activar la membresía en un solo paso | EP-09 | Memberships (+ Payments) | v0.1 | Membresia_Vender | 3 |
| [US-086](EP-09-membresias/US-086-activar-por-cobertura-de-pagos.md) | Como administrador o coach quiero que la membresía se active sola cuando los pagos cubren el precio pactado para no tener que cambiar estados a mano | EP-09 | Memberships | v0.1 | ninguna (efecto visible en listas) | 3 |
| [US-087](EP-09-membresias/US-087-revertir-activacion-al-anular-pago.md) | Como administrador quiero que al anular un pago la membresía vuelva a pendiente si ya no está cubierta para que el estado nunca muestre al día a quien no pagó | EP-09 | Memberships | v0.1 | ninguna | 2 |
| [US-088](EP-09-membresias/US-088-renovar-membresia.md) | Como administrador o coach quiero renovar la membresía de un socio antes o después de que venza para que no pierda días ni quede con dos planes encimados | EP-09 | Memberships | v0.1 | Membresia_Vender (?socio=:id&renovar=1) | 5 |
| [US-089](EP-09-membresias/US-089-congelar-membresia.md) | Como administrador o coach quiero congelar una membresía entre dos fechas para que el socio no pierda los días que no puede entrenar | EP-09 | Memberships | v0.1 | Membresias (modal congelar) | 5 |
| [US-090](EP-09-membresias/US-090-anular-membresia.md) | Como administrador quiero anular una membresía con un motivo para corregir una venta equivocada dejando rastro de por qué | EP-09 | Memberships | v0.1 | Membresias (modal anular) | 3 |
| [US-091](EP-09-membresias/US-091-listar-membresias.md) | Como administrador o coach quiero ver y filtrar las membresías por estado, plan y fecha de vencimiento para saber quién vence esta semana y a quién cobrar | EP-09 | Memberships | v0.1 | Membresias (/membresias) | 3 |
| [US-092](EP-09-membresias/US-092-resumen-y-consultas-de-estado.md) | Como administrador o coach quiero contar cuántos socios están al día, por vencer, vencidos, congelados y pendientes de pago para saber en segundos cómo está el gimnasio | EP-09 | Memberships | v0.1 | ninguna (alimenta Inicio y Socios) | 3 |
| [US-093](EP-09-membresias/US-093-pestana-membresias-de-la-ficha.md) | Como administrador o coach quiero ver todas las membresías de un socio en su ficha para conocer su historia y renovar o congelar desde ahí | EP-09 | Memberships | v0.1 | Socio_Ficha (pestaña Membresías) | 2 |
| [US-094](EP-09-membresias/US-094-job-diario-de-vencimientos.md) | Como administrador quiero que cada mañana el sistema actualice solo los estados de las membresías para ver al abrir quién vence y quién ya venció | EP-09 | Memberships (worker) | v0.1 | ninguna | 5 |
| [US-095](EP-10-pagos/US-095-registrar-pago.md) | Como coach o administrador quiero registrar un pago contra una membresía para que cada peso recibido quede anotado una sola vez y active la membresía cuando cubra el precio | EP-10 | Payments | v0.1 | Pagos (SidePanel) | 5 |
| [US-096](EP-10-pagos/US-096-inmutabilidad-de-pagos-en-la-base.md) | Como administrador quiero que la base de datos impida editar o borrar un pago para que la caja no se pueda alterar ni por error de programación ni a mano | EP-10 | Payments | v0.1 | ninguna | 3 |
| [US-097](EP-10-pagos/US-097-anular-pago.md) | Como administrador quiero anular un pago con motivo para corregir un error de caja sin borrar el rastro del pago original | EP-10 | Payments | v0.1 | Pagos (modal anular) | 3 |
| [US-098](EP-10-pagos/US-098-listar-y-buscar-pagos.md) | Como coach o administrador quiero listar y filtrar los pagos para revisar la caja por fecha, medio, persona que registró o socio | EP-10 | Payments | v0.1 | Pagos (/pagos) | 3 |
| [US-099](EP-10-pagos/US-099-ver-detalle-de-pago.md) | Como coach o administrador quiero ver el detalle de un pago para confirmar sus datos y, si fue anulado, quién lo anuló y por qué | EP-10 | Payments | v0.1 | Pagos (modal detalle) | 1 |
| [US-100](EP-10-pagos/US-100-resumen-mensual-de-pagos.md) | Como coach o administrador quiero ver el resumen de ingresos del mes por medio de pago para cuadrar la caja sin hacer sumas a mano | EP-10 | Payments | v0.1 | Pagos (resumen) | 3 |
| [US-101](EP-10-pagos/US-101-pestana-pagos-de-la-ficha.md) | Como coach o administrador quiero ver los pagos de un socio en su ficha para responderle qué ha pagado sin salir de su registro | EP-10 | Payments | v0.1 | Socio_Ficha (pestaña Pagos) | 2 |
| [US-102](EP-11-auditoria/US-102-consultar-auditoria.md) | Como administrador quiero consultar la auditoría con filtros para responder quién hizo qué, cuándo y sobre qué registro | EP-11 | Audit | v0.1 | Auditoria (/sistema/auditoria) | 5 |
| [US-103](EP-11-auditoria/US-103-ver-detalle-antes-y-despues.md) | Como administrador quiero ver el antes y el después de un cambio auditado para entender exactamente qué se modificó sin exponer datos cifrados | EP-11 | Audit | v0.1 | Auditoria (detalle) | 2 |
| [US-104](EP-11-auditoria/US-104-verificar-cadena-desde-pantalla.md) | Como administrador quiero verificar la integridad de la cadena de auditoría desde la pantalla para demostrar que el historial no fue alterado | EP-11 | Audit | v0.1 | Auditoria (botón Verificar) | 5 |
| [US-105](EP-11-auditoria/US-105-verificar-cadena-por-cli.md) | Como administrador quiero verificar la cadena de auditoría desde la línea de comandos para comprobar la integridad sin entrar al sistema web | EP-11 | Audit | v0.1 | ninguna | 2 |
| [US-106](EP-11-auditoria/US-106-historial-del-socio.md) | Como coach o administrador quiero ver el historial de cambios de un socio en su ficha para saber quién modificó o consultó sus datos | EP-11 | Audit (+ Members) | v0.1 | Socio_Ficha (pestaña Historial, HistoryAside) | 3 |
| [US-107](EP-11-auditoria/US-107-auditoria-de-eventos-de-seguridad.md) | Como administrador quiero que las consultas en claro, los inicios de sesión, los bloqueos y los cierres de sesión queden en la auditoría para tener rastro de los eventos de seguridad, no solo de los cambios de datos | EP-11 | Audit | v0.1 | ninguna | 3 |
| [US-108](EP-12-tablero-de-inicio/US-108-contrato-del-tablero.md) | Como coach o administrador quiero un tablero con un contrato estable desde v0.1 para ver los números del día en una sola llamada y que cada versión solo llene sus campos | EP-12 | Dashboard | v0.1 | Inicio (/) | 3 |
| [US-109](EP-12-tablero-de-inicio/US-109-kpis-de-membresias-e-ingresos.md) | Como coach o administrador quiero ver en Inicio las tarjetas de socios al día, por vencer, vencidos e ingresos del mes para saber en 10 segundos cómo está el gimnasio | EP-12 | Dashboard | v0.1 | Inicio | 3 |
| [US-110](EP-12-tablero-de-inicio/US-110-ultimos-movimientos.md) | Como coach o administrador quiero ver en Inicio los últimos movimientos del gimnasio en frases claras para enterarme de lo que pasó sin abrir la auditoría | EP-12 | Dashboard (+ Audit) | v0.1 | Inicio | 3 |
| [US-111](EP-13-puesta-en-marcha-y-continuidad/US-111-datos-de-demostracion.md) | Como administrador quiero cargar datos de demostración con un comando para capacitar al equipo sin tocar socios reales | EP-13 | Members, Plans, Memberships, Payments | v0.1 | ninguna | 5 |
| [US-112](EP-13-puesta-en-marcha-y-continuidad/US-112-importar-socios-desde-excel.md) | Como administrador quiero importar los socios que ya tengo en Excel para pasar del cuaderno al sistema en un día | EP-13 | Members (+ Crypto) | v0.1 | ninguna | 8 |
| [US-113](EP-13-puesta-en-marcha-y-continuidad/US-113-proceso-worker-programado.md) | Como administrador quiero un proceso worker que corra los trabajos diarios a las 7:00 hora de Bogotá para que vencimientos y verificaciones ocurran sin que nadie se acuerde | EP-13 | worker | v0.1 | ninguna | 3 |
| [US-114](EP-13-puesta-en-marcha-y-continuidad/US-114-backup-nocturno-cifrado.md) | Como administrador quiero un respaldo nocturno cifrado de la base y los adjuntos para no perder la información si el servidor se daña | EP-13 | backup | v0.1 | ninguna | 5 |
| [US-115](EP-13-puesta-en-marcha-y-continuidad/US-115-verificacion-de-backup.md) | Como administrador quiero que el sistema verifique cada mañana que el último backup existe, es reciente y se puede descifrar para enterarme a tiempo si los respaldos dejaron de funcionar | EP-13 | worker, backup | v0.1 | ninguna | 3 |
| [US-116](EP-13-puesta-en-marcha-y-continuidad/US-116-respaldo-de-kek-y-prueba-de-restauracion.md) | Como administrador quiero un procedimiento probado para respaldar la KEK y restaurar un backup para que el respaldo sirva de verdad el día que lo necesite | EP-13 | Crypto, backup | v0.1 | ninguna | 3 |
| [US-117](EP-13-puesta-en-marcha-y-continuidad/US-117-despliegue-seguro.md) | Como administrador quiero actualizar el sistema con un solo comando que respalda antes y verifica después para no quedar con el gimnasio sin sistema por una actualización fallida | EP-13 | ninguno (operación) | v0.1 | ninguna | 3 |
| [US-118](EP-13-puesta-en-marcha-y-continuidad/US-118-arranque-ordenado.md) | Como administrador quiero que los servicios arranquen en orden y solo reciban tráfico cuando la base y las migraciones estén listas para que un reinicio del servidor no deje el sistema a medias | EP-13 | ninguno (operación) | v0.1 | ninguna | 2 |
| [US-119](EP-13-puesta-en-marcha-y-continuidad/US-119-adr-iniciales.md) | Como equipo quiero los ADR iniciales de monolito modular, bus de criptografía y pagos inmutables para que las decisiones irreversibles queden escritas y nadie las cambie sin saberlo | EP-13 | ninguno (operación) | v0.1 | ninguna | 2 |
| [US-120](EP-14-avisos-de-vencimiento/US-120-plantillas-de-aviso.md) | Como administrador quiero mantener plantillas de aviso con variables para que cada recordatorio diga lo correcto sin escribirlo a mano | EP-14 | Notifications | v0.2 | Notif_Reglas (pestaña Plantillas) | 5 |
| [US-121](EP-14-avisos-de-vencimiento/US-121-reglas-de-aviso.md) | Como administrador quiero definir reglas de aviso relativas al vencimiento para que el sistema sepa cuándo y por qué canal recordar a cada socio | EP-14 | Notifications | v0.2 | Notif_Reglas (/avisos/reglas) | 5 |
| [US-122](EP-14-avisos-de-vencimiento/US-122-configurar-canales-de-aviso.md) | Como administrador quiero configurar los canales de aviso sin guardar secretos en la base para habilitar correo y WhatsApp de forma segura | EP-14 | Settings | v0.2 | Config (canales) | 2 |
| [US-123](EP-14-avisos-de-vencimiento/US-123-preferencias-de-canal-del-socio.md) | Como coach quiero registrar por qué canales acepta avisos cada socio para no escribirle por donde no quiere | EP-14 | Members | v0.2 | Socio_Ficha (pestaña Avisos) | 3 |
| [US-124](EP-14-avisos-de-vencimiento/US-124-generar-avisos-del-dia.md) | Como administrador quiero que cada mañana se genere la lista de avisos del día sin duplicados para no olvidar a nadie ni repetir mensajes | EP-14 | Notifications | v0.2 | ninguna | 5 |
| [US-125](EP-14-avisos-de-vencimiento/US-125-enviar-avisos-por-correo.md) | Como administrador quiero que los avisos por correo se envíen solos y que los fallos queden registrados para que nadie tenga que mandarlos uno por uno | EP-14 | Notifications | v0.2 | ninguna | 5 |
| [US-126](EP-14-avisos-de-vencimiento/US-126-enviar-avisos-por-telegram.md) | Como administrador quiero recibir en el chat del equipo, por Telegram, el resumen diario de avisos y las alertas del worker para enterarme sin entrar al sistema | EP-14 | Notifications | v0.2 | ninguna | 3 |
| [US-127](EP-14-avisos-de-vencimiento/US-127-por-avisar-hoy-y-enlace-de-whatsapp.md) | Como coach quiero ver a quién hay que avisar hoy y abrir el WhatsApp con el mensaje listo para avisar en segundos | EP-14 | Notifications | v0.2 | PorAvisarHoy (/avisos/hoy) | 5 |
| [US-128](EP-14-avisos-de-vencimiento/US-128-omitir-aviso-con-motivo.md) | Como coach quiero omitir un aviso con motivo para no molestar a un socio que ya sé que va a renovar y dejar el porqué registrado | EP-14 | Notifications | v0.2 | PorAvisarHoy | 2 |
| [US-129](EP-14-avisos-de-vencimiento/US-129-historial-de-envios.md) | Como administrador quiero consultar el historial de avisos con filtros para saber a quién se le avisó, cuándo, por dónde y con qué resultado | EP-14 | Notifications | v0.2 | Notif_Historial (/avisos/historial) | 3 |
| [US-130](EP-14-avisos-de-vencimiento/US-130-pestana-avisos-de-la-ficha.md) | Como coach quiero ver en la ficha del socio los avisos que se le han enviado para saber si ya se le recordó antes de hablarle | EP-14 | Notifications | v0.2 | Socio_Ficha (pestaña Avisos) | 2 |
| [US-131](EP-14-avisos-de-vencimiento/US-131-recuperar-y-activar-cuenta-por-correo.md) | Como coach quiero recibir por correo el enlace para activar mi cuenta o recuperar mi contraseña para no depender de que el administrador me lo pase a mano | EP-14 | Auth (+ Notifications) | v0.2 | Login (/recuperar, /restablecer/:token) | 3 |
| [US-132](EP-14-avisos-de-vencimiento/US-132-kpi-por-avisar-en-inicio.md) | Como administrador quiero ver en Inicio cuántos avisos quedan por gestionar hoy para no olvidar llamar a nadie | EP-14 | Dashboard | v0.2 | Inicio | 1 |
| [US-133](EP-15-custodia-de-llaves-openbao/US-133-servicio-openbao-con-transit.md) | Como administrador quiero un OpenBao con motor Transit en el Compose del gimnasio para que la llave maestra deje de vivir en un archivo del servidor de aplicación | EP-15 | Crypto | v0.2 | ninguna | 5 |
| [US-134](EP-15-custodia-de-llaves-openbao/US-134-proveedor-openbao.md) | Como administrador quiero que el bus de criptografía use OpenBao como proveedor de llaves para que envolver y desenvolver las DEK ocurra en el custodio y quede registrado | EP-15 | Crypto | v0.2 | ninguna | 8 |
| [US-135](EP-15-custodia-de-llaves-openbao/US-135-migrar-proveedor-de-llaves.md) | Como administrador quiero migrar las llaves del proveedor local a OpenBao sin recifrar datos para pasar a la custodia segura en minutos y sin riesgo para la información | EP-15 | Crypto | v0.2 | ninguna | 5 |
| [US-136](EP-15-custodia-de-llaves-openbao/US-136-estado-degradado-con-openbao-sellado.md) | Como administrador quiero que el sistema me diga claramente cuando OpenBao está sellado para saber que debo desellarlo en lugar de ver errores confusos | EP-15 | Crypto (core) | v0.2 | ninguna | 3 |
| [US-137](EP-16-recibos-y-exportaciones/US-137-descargar-recibo-de-pago.md) | Como coach quiero descargar el recibo en PDF de un pago para entregarle al socio un comprobante de lo que pagó | EP-16 | Payments | v0.2 | Pagos (detalle) y Socio_Ficha (Pagos) | 5 |
| [US-138](EP-16-recibos-y-exportaciones/US-138-exportar-socios-a-csv.md) | Como administrador quiero exportar la lista de socios a CSV para usarla en contabilidad o como respaldo propio, dejando rastro de la salida de datos | EP-16 | Members | v0.2 | Socios_Lista (botón Exportar) | 5 |
| [US-139](EP-16-recibos-y-exportaciones/US-139-exportar-pagos-a-csv.md) | Como administrador quiero exportar los pagos filtrados a CSV para cuadrar la caja con contabilidad sin copiar a mano | EP-16 | Payments | v0.2 | Pagos (botón Exportar) | 3 |
| [US-140](EP-17-auditoria-firmada/US-140-registro-de-firmas-de-auditoria.md) | Como administrador quiero un registro inmutable de firmas de la cadena de auditoría con su propia llave para poder probar que la historia no fue reescrita | EP-17 | Audit (+ Crypto) | v0.3 | ninguna | 3 |
| [US-141](EP-17-auditoria-firmada/US-141-firma-nocturna-de-la-cadena.md) | Como administrador quiero que cada noche se firme el último eslabón de la cadena de auditoría para sellar lo ocurrido en el día | EP-17 | Audit (+ Crypto) | v0.3 | ninguna | 5 |
| [US-142](EP-17-auditoria-firmada/US-142-verificacion-con-firmas-y-estado-en-pantalla.md) | Como administrador quiero que la verificación de auditoría compruebe también las firmas y me muestre la última firma válida para demostrar que nadie reescribió la historia | EP-17 | Audit (+ Crypto) | v0.3 | Auditoria (estado de firma) | 5 |
| [US-143](EP-18-administracion-de-llaves/US-143-inventario-de-llaves.md) | Como administrador quiero ver el inventario de llaves de cifrado para saber qué llave protege cada clase de dato y cuándo se rotó | EP-18 | Crypto | v0.3 | Llaves (/sistema/llaves) | 3 |
| [US-144](EP-18-administracion-de-llaves/US-144-bitacora-y-trabajos-criptograficos.md) | Como administrador quiero consultar la bitácora de operaciones criptográficas y el progreso de los trabajos para saber quién usó cada llave y cómo va una rotación | EP-18 | Crypto | v0.3 | Llaves (bitácora, jobs) | 3 |
| [US-145](EP-18-administracion-de-llaves/US-145-rotar-llave-desde-la-pantalla.md) | Como administrador quiero rotar una llave desde la pantalla con confirmación y motivo para reaccionar a una sospecha de filtración sin abrir una terminal | EP-18 | Crypto | v0.3 | Llaves (modal rotar) | 5 |
| [US-146](EP-18-administracion-de-llaves/US-146-exportar-cbom.md) | Como administrador quiero exportar el inventario criptográfico (CBOM) para entregárselo a quien audite la protección de datos | EP-18 | Crypto | v0.3 | Llaves (botón Exportar CBOM) | 3 |
| [US-147](EP-19-adjuntos-y-autorizacion-de-datos/US-147-almacenamiento-seguro-de-adjuntos.md) | Como administrador quiero que los archivos adjuntos se guarden validados, con nombre aleatorio y cifrados cuando son sensibles para que la foto y la autorización de un socio no puedan filtrarse ni suplantarse | EP-19 | Attachments (+ Members) | v0.3 | ninguna | 5 |
| [US-148](EP-19-adjuntos-y-autorizacion-de-datos/US-148-subir-foto-del-socio.md) | Como coach quiero subir la foto del socio al crearlo o editarlo para reconocerlo en recepción y en el check-in | EP-19 | Attachments (+ Members) | v0.3 | Socio_Form (foto) | 3 |
| [US-149](EP-19-adjuntos-y-autorizacion-de-datos/US-149-registrar-autorizacion-de-datos.md) | Como administrador quiero registrar la autorización de tratamiento de datos de cada socio nuevo para demostrar su consentimiento ante un reclamo bajo la Ley 1581 | EP-19 | Attachments, Members | v0.3 | Socio_Form (autorización) | 5 |
| [US-150](EP-19-adjuntos-y-autorizacion-de-datos/US-150-pestana-adjuntos-y-descarga-auditada.md) | Como coach quiero ver y descargar los adjuntos de un socio desde su ficha con rastro de auditoría para consultar su autorización sin exponerla sin control | EP-19 | Attachments (+ Members) | v0.3 | Socio_Ficha (pestaña Adjuntos) | 3 |
| [US-151](EP-19-adjuntos-y-autorizacion-de-datos/US-151-socios-sin-autorizacion-registrada.md) | Como administrador quiero ver cuántos socios no tienen autorización registrada para ir recogiéndolas sin bloquear la operación | EP-19 | Members, Dashboard | v0.3 | Inicio y Socio_Ficha | 2 |
| [US-152](EP-20-acceso-cifrado-tls/US-152-tls-automatico-con-caddy-hibrido.md) | Como administrador quiero que el sistema se sirva por HTTPS con TLS automático e intercambio híbrido post-cuántico para usarlo desde fuera del local sin que las contraseñas ni los datos viajen en claro | EP-20 | ninguno (borde) | v0.3 | ninguna | 5 |
| [US-153](EP-20-acceso-cifrado-tls/US-153-redireccion-https-hsts-y-modo-lan.md) | Como administrador quiero que toda petición HTTP se redirija a HTTPS con HSTS y que el modo LAN siga funcionando sin dominio para no exponer tokens por error y no romper el gimnasio si no hay internet | EP-20 | ninguno (borde) | v0.3 | ninguna | 3 |
| [US-154](EP-21-clases-y-check-in/US-154-configurar-horas-y-clases.md) | Como administrador quiero configurar las horas de atención y los valores por defecto de las clases para que el horario y el check-in usen las reglas de mi gimnasio | EP-21 | Settings | v0.4 | Config (horas, clases) | 2 |
| [US-155](EP-21-clases-y-check-in/US-155-horario-semanal-de-franjas.md) | Como administrador quiero definir el horario semanal de franjas para que las clases se generen solas con su hora, cupo y coach | EP-21 | Classes | v0.4 | Horario (/clases/horario) | 5 |
| [US-156](EP-21-clases-y-check-in/US-156-generar-sesiones-desde-el-horario.md) | Como administrador quiero que las sesiones de las próximas dos semanas se generen solas desde el horario para no crear cada clase a mano | EP-21 | Classes | v0.4 | ninguna | 5 |
| [US-157](EP-21-clases-y-check-in/US-157-sesiones-de-la-semana.md) | Como coach quiero ver las sesiones de la semana, crear una sesión extra y cancelar una sesión con motivo para organizar las clases reales del box | EP-21 | Classes | v0.4 | Sesiones (/clases) | 5 |
| [US-158](EP-21-clases-y-check-in/US-158-cancelar-sesiones-futuras-de-una-franja.md) | Como administrador quiero cancelar de una vez las sesiones futuras de una franja para aplicar un cambio de horario sin cancelar clase por clase | EP-21 | Classes | v0.4 | Horario | 2 |
| [US-159](EP-21-clases-y-check-in/US-159-check-in-en-tablet.md) | Como coach quiero hacer check-in de los socios en la tablet sin que nunca se bloquee por su membresía para no frenar la fila y saber quién entrena vencido | EP-21 | Classes | v0.4 | CheckIn (/clases/:id/checkin) | 8 |
| [US-160](EP-21-clases-y-check-in/US-160-descontar-y-devolver-clases.md) | Como administrador quiero que cada asistencia descuente una clase de los planes por clases y que borrarla la devuelva para que la tiquetera del socio cuadre sin contar a mano | EP-21 | Memberships (+ Classes) | v0.4 | ninguna | 3 |
| [US-161](EP-21-clases-y-check-in/US-161-borrar-asistencia.md) | Como coach quiero borrar una asistencia registrada por error para corregir la lista de la clase y devolver la clase al socio | EP-21 | Classes | v0.4 | CheckIn | 2 |
| [US-162](EP-21-clases-y-check-in/US-162-reportes-de-asistencia.md) | Como administrador quiero consultar la asistencia por socio y por semana para ver la ocupación real de cada horario y la constancia de cada socio | EP-21 | Classes | v0.4 | Sesiones (pestaña asistencia) y Socio_Ficha (Asistencia) | 3 |
| [US-163](EP-21-clases-y-check-in/US-163-filtro-de-ultima-asistencia.md) | Como administrador quiero filtrar la lista de socios por su última asistencia para encontrar a quienes dejaron de venir y llamarlos antes de que no renueven | EP-21 | Members (+ Classes) | v0.4 | Socios_Lista | 2 |
| [US-164](EP-21-clases-y-check-in/US-164-kpis-de-asistencia-en-inicio.md) | Como administrador quiero ver en Inicio la asistencia de la semana y las sesiones de hoy para saber de un vistazo cómo va la ocupación del box | EP-21 | Dashboard | v0.4 | Inicio | 2 |
| [US-165](EP-22-entrenamiento-wods-y-resultados/US-165-catalogo-de-movimientos.md) | Como coach quiero mantener el catálogo de movimientos para armar los WODs con ejercicios estandarizados | EP-22 | Training | v0.5 | Movimientos (/movimientos) | 5 |
| [US-166](EP-22-entrenamiento-wods-y-resultados/US-166-crear-y-editar-wod.md) | Como coach quiero crear y editar el WOD con sus movimientos, reps y cargas RX para publicar el entrenamiento del día | EP-22 | Training | v0.5 | WOD_Form (/wods/nuevo, /wods/:id/editar) | 8 |
| [US-167](EP-22-entrenamiento-wods-y-resultados/US-167-calendario-de-wods.md) | Como coach quiero ver el calendario de WODs por semana y buscar benchmarks para planear la programación | EP-22 | Training | v0.5 | WOD_Lista (/wods) | 3 |
| [US-168](EP-22-entrenamiento-wods-y-resultados/US-168-wod-del-dia-y-asignacion-a-sesiones.md) | Como coach quiero que las sesiones del día hereden el WOD del día y poder asignar otro a una sesión para registrar los resultados contra el entrenamiento correcto | EP-22 | Training | v0.5 | WOD_Detalle / Sesiones | 3 |
| [US-169](EP-22-entrenamiento-wods-y-resultados/US-169-registrar-resultados-en-tablet.md) | Como coach quiero registrar en la tablet las marcas de los socios que asistieron a la clase para sacar los resultados de la pizarra | EP-22 | Training (+ Classes) | v0.5 | Resultados_Registro (/clases/:id/resultados) | 8 |
| [US-170](EP-22-entrenamiento-wods-y-resultados/US-170-corregir-resultado.md) | Como coach quiero corregir un resultado mal registrado sin borrarlo para que la marca correcta quede vigente y el error quede en el historial | EP-22 | Training | v0.5 | Resultados_Registro | 3 |
| [US-171](EP-22-entrenamiento-wods-y-resultados/US-171-leaderboard-del-dia.md) | Como coach quiero un leaderboard del WOD por nivel y sexo para que los atletas comparen sus marcas | EP-22 | Training | v0.5 | WOD_Detalle | 5 |
| [US-172](EP-22-entrenamiento-wods-y-resultados/US-172-detalle-de-wod.md) | Como coach quiero ver el detalle de un WOD con sus movimientos y todos sus resultados para revisar cómo le fue al box | EP-22 | Training | v0.5 | WOD_Detalle (/wods/:id) | 3 |
| [US-173](EP-22-entrenamiento-wods-y-resultados/US-173-pestana-resultados-de-la-ficha.md) | Como coach quiero ver los resultados de un socio en su ficha para conversar con él sobre su progreso | EP-22 | Training | v0.5 | Socio_Ficha (pestaña Resultados) | 2 |
| [US-174](EP-22-entrenamiento-wods-y-resultados/US-174-tarjeta-wod-de-hoy-en-inicio.md) | Como coach quiero ver el WOD de hoy en el tablero de inicio para saber qué se entrena sin abrir otra pantalla | EP-22 | Dashboard | v0.5 | Inicio | 1 |
| [US-175](EP-23-pantalla-de-tv/US-175-token-de-dispositivo-de-tv.md) | Como administrador quiero generar y rotar el token de la TV desde Configuración para controlar qué pantalla puede mostrar el WOD y el leaderboard | EP-23 | Settings | v0.5 | Config (TV) | 2 |
| [US-176](EP-23-pantalla-de-tv/US-176-endpoint-publico-de-tv.md) | Como dispositivo TV quiero leer el WOD del día y su leaderboard con mi token para mostrarlos en la pared del box sin datos personales | EP-23 | TV | v0.5 | ninguna | 3 |
| [US-177](EP-23-pantalla-de-tv/US-177-pantalla-de-tv.md) | Como dispositivo TV quiero mostrar el WOD del día y el leaderboard actualizados cada 30 segundos para reemplazar la pizarra de la pared | EP-23 | TV | v0.5 | TV (/tv?token=...) | 3 |
| [US-178](EP-24-perfil-del-atleta/US-178-registrar-medidas-corporales-cifradas.md) | Como coach quiero registrar el peso y las medidas corporales de un socio cifradas para seguir su evolución sin exponer datos de salud | EP-24 | Athletes | v0.6 | Atleta_Perfil (Medidas) | 5 |
| [US-179](EP-24-perfil-del-atleta/US-179-mostrar-medida-en-claro-auditada.md) | Como coach quiero mostrar en claro una medida corporal con registro de auditoría para ver el dato real sin perder la trazabilidad | EP-24 | Athletes | v0.6 | Atleta_Perfil (MaskedValue) | 2 |
| [US-180](EP-24-perfil-del-atleta/US-180-registrar-records-manuales.md) | Como coach quiero registrar récords personales manuales de un socio para conservar las marcas logradas fuera del registro de resultados | EP-24 | Athletes | v0.6 | Atleta_Perfil (RMs, Récords) | 3 |
| [US-181](EP-24-perfil-del-atleta/US-181-record-derivado-por-carga.md) | Como coach quiero que un resultado validado con más carga que el RM vigente cree el récord automáticamente para no tener que registrarlo a mano | EP-24 | Athletes | v0.6 | ninguna (efecto en Atleta_Perfil) | 5 |
| [US-182](EP-24-perfil-del-atleta/US-182-record-derivado-de-benchmark.md) | Como coach quiero que una mejor marca validada en un benchmark cree el récord del socio para seguir su progreso en los WODs de referencia | EP-24 | Athletes | v0.6 | ninguna | 3 |
| [US-183](EP-24-perfil-del-atleta/US-183-comparar-benchmarks.md) | Como coach quiero ver todos los intentos de un socio en un mismo benchmark en orden cronológico para mostrarle cuánto ha mejorado | EP-24 | Athletes | v0.6 | Atleta_Perfil (Benchmarks) | 3 |
| [US-184](EP-24-perfil-del-atleta/US-184-perfil-del-atleta-en-la-ficha.md) | Como coach quiero ver el perfil del atleta en la ficha del socio con resumen, medidas, RMs, récords y benchmarks para tener toda su historia en un solo lugar | EP-24 | Athletes | v0.6 | Atleta_Perfil (/socios/:id/atleta) | 5 |
| [US-185](EP-25-portal-del-socio/US-185-crear-cuenta-de-portal.md) | Como administrador quiero crear la cuenta de portal de un socio desde su ficha para que reciba por correo el enlace de activación | EP-25 | Auth (+ Members) | v1.0 | Socio_Ficha (acción) y Login (activación) | 5 |
| [US-186](EP-25-portal-del-socio/US-186-autorizacion-propia-en-rutas-me.md) | Como socio quiero que el portal solo me muestre mis datos para tener la certeza de que nadie más ve mi información ni yo la de otros | EP-25 | Portal | v1.0 | ninguna (todas /mi) | 3 |
| [US-187](EP-25-portal-del-socio/US-187-inicio-del-portal.md) | Como socio quiero ver en el inicio del portal mi plan, su estado y cuándo vence para saber si estoy al día sin preguntar en recepción | EP-25 | Portal | v1.0 | Portal_Inicio (/mi) | 3 |
| [US-188](EP-25-portal-del-socio/US-188-mis-pagos-y-recibos.md) | Como socio quiero ver mis pagos y descargar sus recibos para tener constancia de que mi plata quedó registrada | EP-25 | Portal | v1.0 | Portal_Pagos (/mi/pagos) | 3 |
| [US-189](EP-25-portal-del-socio/US-189-mis-wods-y-enviar-resultado.md) | Como socio quiero ver mis resultados y enviar mi marca del WOD de hoy desde el celular para tener mi historial sin depender del coach | EP-25 | Portal | v1.0 | Portal_WODs (/mi/wods) | 5 |
| [US-190](EP-25-portal-del-socio/US-190-validar-resultados-enviados.md) | Como coach quiero validar los resultados que envían los socios desde una bandeja para que entren al leaderboard y a sus récords | EP-25 | Training | v1.0 | Resultados_Registro y WOD_Detalle (bandeja por validar) | 5 |
| [US-191](EP-25-portal-del-socio/US-191-mi-progreso.md) | Como socio quiero ver mis récords, RMs, benchmarks y peso y registrar mi peso para seguir mi progreso desde el celular | EP-25 | Portal | v1.0 | Portal_Progreso (/mi/progreso) | 5 |
| [US-192](EP-25-portal-del-socio/US-192-mis-datos-y-contrasena.md) | Como socio quiero ver y corregir mi teléfono, correo y contacto de emergencia y cambiar mi contraseña para mantener mis datos al día sin ir a recepción | EP-25 | Portal | v1.0 | Portal_Datos (/mi/datos) | 5 |
| [US-193](EP-25-portal-del-socio/US-193-mis-avisos-y-canales.md) | Como socio quiero ver los avisos que me ha enviado el gimnasio y elegir por qué canales recibirlos para enterarme de mis vencimientos por donde prefiero | EP-25 | Portal | v1.0 | Portal_Avisos (/mi/avisos) | 3 |
| [US-194](EP-25-portal-del-socio/US-194-suscripcion-web-push.md) | Como socio quiero activar las notificaciones push del portal en mi celular para recibir los avisos sin depender del correo o de WhatsApp | EP-25 | Notifications, Members | v1.0 | Portal_Avisos | 5 |
| [US-195](EP-25-portal-del-socio/US-195-aviso-de-record-nuevo.md) | Como socio quiero recibir un push cuando logro un récord personal para celebrar mi progreso en el momento | EP-25 | Notifications | v1.0 | ninguna | 3 |
| [US-196](EP-26-cierre-criptografico-post-cuantico/US-196-firma-de-backups.md) | Como administrador quiero que cada backup quede firmado con ML-DSA y se verifique antes de restaurarlo para saber que nadie lo alteró | EP-26 | Crypto, backup | v1.0 | ninguna | 5 |
| [US-197](EP-26-cierre-criptografico-post-cuantico/US-197-cbom-cyclonedx.md) | Como administrador quiero exportar el inventario criptográfico en formato CycloneDX para entregarlo a quien audite la protección de datos | EP-26 | Crypto (+ backup) | v1.0 | Llaves | 3 |
| [US-198](EP-26-cierre-criptografico-post-cuantico/US-198-envoltura-de-llaves-con-ml-kem.md) | Como administrador quiero que las DEK se envuelvan con ML-KEM detrás del mismo KeyProvider para que la protección de las llaves resista computación cuántica | EP-26 | Crypto (+ backup) | v1.0 | ninguna | 8 |
| [US-199](EP-26-cierre-criptografico-post-cuantico/US-199-re-envoltura-reanudable-de-deks.md) | Como administrador quiero re-envolver las DEK existentes con ML-KEM en un trabajo reanudable para proteger los datos ya guardados sin recifrarlos | EP-26 | Crypto (+ backup) | v1.0 | ninguna | 5 |


## Orden sugerido en v0.1 (ruta crítica)

Cada historia trae sus dependencias en su archivo. Este es el orden que las respeta.

1. **Terreno:** US-001, US-002, US-005, US-009. Después US-003, US-004, US-006, US-007, US-008 y US-010.
2. **Núcleo:** US-011, US-012, US-013, US-017, US-018. Después US-014, US-015, US-016, US-019 y US-020. Al final US-021 y US-022.
3. **En paralelo:**
   - Bus de criptografía: US-023 a US-031.
   - Seguridad: US-032 a US-040.
   - Kit del front: US-059 a US-068.
4. **Acceso:** identidad (US-041 a US-053) y configuración (US-054 a US-058). US-058 tiene que estar lista antes de congelar.
5. **Socios y planes, en paralelo:** socios de US-069 a US-077 y planes de US-078 a US-081.
6. **Membresías y pagos, en la misma iteración:** US-083, US-084, US-095, US-085, US-086, US-096, US-097, US-087, y luego el resto de EP-09 y EP-10. US-071 y US-082 cierran cuando existe US-092.
7. **Worker:** US-113 tiene que estar antes de cerrar US-094.
8. **Auditoría y tablero:** auditoría de US-102 a US-107 y tablero de US-108 a US-110.
9. **Puesta en marcha:** US-111, US-112 y de US-114 a US-119.

Ruta crítica de historias: US-001 → US-002 → US-011 → US-012 → US-015 → US-016 → US-023/US-024 → US-025 → US-028 → US-069 → US-084 ↔ US-095 → US-086 → US-092 → US-108.

## Ajustes de dependencias hechos al consolidar

Los forks encontraron dependencias que el catálogo inicial no tenía. Ya quedaron escritas en la sección "Dependencias" de cada historia, marcadas como "agregado en consolidación":

- **Dependencias suaves:**
  - US-016 depende de US-034, porque el actor de una petición HTTP sale del usuario autenticado.
  - US-034 depende de US-041; mientras tanto se prueba con un doble.
- **Nuevas dependencias:**
  - US-030 depende de US-016.
  - US-048 depende de US-036.
  - US-053 depende de US-045.
  - US-073 depende de US-040.
  - US-116 depende de US-074.
  - US-124 depende de US-122 y US-123.
  - US-147 depende de US-034 y US-069.
  - US-189 depende de US-168.
  - US-191 depende de US-179.
  - US-194 depende de US-121.
  - US-196 depende de US-027.
  - US-199 depende de US-196.
- **Contratos entre services que otras historias necesitan:**
  - `memberships.service.member_ids_by_status`, en US-092, lo usa US-071.
  - `members.service.search_ids` y `names_for`, en US-069 o US-070, los usan US-091 y US-110.
  - `payments.service.sum_not_voided`, en US-095, lo usa US-086.
  - `paid_cop` en `GET /memberships/{id}`, en US-091, lo usa US-095.
  - `names_for` en plans y auth, lo usa US-110.
- **Ciclo resuelto entre US-074 y US-107:** la fila de auditoría `reveal` la escribe US-074, que llama a `audit.record` en la misma transacción. US-107 se queda con login, `UserLocked` y `SessionsRevoked`.
- **Requisitos que se cruzan entre épicas:**
  - El mixin de US-012 debe asignar el UUID en Python antes del flush, porque el AAD del cifrado es el id (US-028).
  - US-115 y US-136 agregan los campos `backup` y `crypto` al `/health` de US-020.
  - US-140 necesita que `cli init-keys` de US-023 acepte `--data-class`.
- **Unificación:** la contraseña mínima quedó en 12 caracteres en US-032, US-041, US-045 y US-048. Antes, US-032 decía 10.

## Historias más riesgosas

1. **US-069 · Registrar socio (8).** Fija con datos reales cuatro cosas que después solo se cambian recifrando o reindexando todo el padrón:
   - el formato del blob;
   - la normalización del índice ciego;
   - el índice único parcial sobre `document_idx`;
   - la decisión de las columnas `*_hint` (pregunta N-01).
2. **US-084 · Vender membresía (5).** Fija el esquema de `memberships` y la invariante de Q1 con `EXCLUDE USING gist`, que necesita `btree_gist`. Además, la atomicidad de S5 depende del bus transaccional y de pagos. Un error se propaga a renovar, congelar, al resumen, al tablero y al job de vencimientos.
3. **US-096 · Inmutabilidad de pagos en la base (3).** El trigger debe dejar pasar exactamente una transición, la anulación, y una sola vez. Si se escribe mal, bloquea anulaciones legítimas o deja editar la caja. Corregirlo con pagos reales es migrar una regla que protege plata.
4. **US-030 · Rotación de llave por CLI (8).** Junta un cambio de estado de llaves que no se deshace con un recifrado por lotes que debe poder reanudarse. Si la llave anterior pasa a `retired` mientras queda un dato cifrado con ella, ese dato personal se pierde para siempre.
5. **US-015 · Tabla de auditoría y cadena de hashes (3).** La serialización canónica no se puede cambiar cuando ya hay datos. Además hay que resolver dos cosas: la concurrencia al leer el `prev_hash` y el choque de `hashlib` con la regla `banned-api` (pregunta N-06).

También tienen riesgo:
- US-159 (check-in): cupo y ventana pueden contradecir RN-09.
- US-116 (respaldo de la KEK): un backup sin KEK no sirve.
- US-043 (refresh con varias pestañas).
- US-124 (generación diaria de avisos).
- US-169 (resultados, con trigger e índice parcial).
- US-198 (ML-KEM, depende de OpenBao).

## Preguntas abiertas

> **Nota (21 de octubre de 2026):** las preguntas heredadas (sección A) fueron aprobadas en el gate tal como se propusieron.
> Las nuevas (N-01 a N-50) quedaron decididas en `docs/ddd/DECISIONES.md`, sección D; la lista siguiente se conserva como registro histórico.

### Heredadas, aprobadas en el gate (`DECISIONES.md`, sección A)

- **D1 / S1:** front en `web/`. Hay que reescribir el "Alcance" de `CLAUDE.md`. Afecta todas las historias con front.
- **D2 / S2:** paginación `limit`/`offset`. Hay que corregir `DESIGN.md` y `ROUTES.md`.
- **D5 / S5:** vender y renovar con `sell` en un solo endpoint (US-084, US-085, US-088).
- **P1:** quién atiende recepción.
- **P3:** destino del backup (US-114).
- **P4:** recibo PDF en v0.2 (US-137).
- **P5:** correo de login en claro en `auth.users.email` (US-041, US-042, US-185).
- **P7:** solo LAN en v0.1 y TLS en v0.3 (US-152, US-153). En v0.1 los tokens viajan sin TLS (US-043).
- **Estructura:** tres épicas de núcleo (EP-01, EP-02, EP-03).

### Nuevas (supuestos de las historias que necesitan decisión)

Cada una está escrita como "Supuesto:" en la historia citada. Las que bloquean una migración de v0.1 van marcadas como **bloqueante**.

Criptografía y datos personales:
- **N-01 (bloqueante, US-069, US-073):** para mostrar el valor enmascarado sin descifrar se proponen columnas `document_hint`, `phone_hint` y `email_hint`, con los últimos 4 dígitos o el dominio enmascarado. Así quedan fragmentos en claro en la base. La alternativa es mostrar solo "Registrado" y exigir `reveal`. Hay que decidirlo antes de la migración de US-069.
- **N-02 (bloqueante, US-026):** la normalización del índice ciego quita minúsculas, espacios y puntos, como dice `CLAUDE.md`, pero no guiones ni tildes. Por eso "1020-304" y "1020304" no se encuentran entre sí. Es irreversible con datos.
- **N-03 (US-023):** la DEK se envuelve con AES-256-GCM bajo la KEK local. Ningún documento fija el algoritmo de envoltura.
- **N-04 (US-025, US-027):** el registro de `data_class` es una constante en código y no una tabla. La firma del bus usa el formato `apx1.<key_id>.<alg>.<sig>`.
- **N-05 (US-024, US-116, US-199):** se proponen tres ampliaciones del modelo:
  - columna `count` en `crypto_ops` para los lotes;
  - verbo `export` y los comandos `cli export-kek` y `cli verify-kek-backup`;
  - valor `rewrap` en `CryptoJob.kind`.
- **N-06 (US-015):** el SHA-256 de la cadena de auditoría se delega a `core/crypto` para no ampliar la excepción de `banned-api` (`hashlib` en `core/audit.py`). Choca con la estructura de módulos de `CLAUDE.md`.
- **N-07 (US-030, US-145):** la llave de índice ciego solo se rota con `--index` explícito, porque obliga a recalcular todos los `_idx`. La pantalla de Llaves solo rota llaves `encrypt`.
- **N-08 (US-137, US-147):** no existe la acción `download` en `AuditEntry.action`; las descargas de recibos y adjuntos se auditan como `export`. ¿Se agrega `download`?
- **N-09 (US-194):** las llaves `p256dh` y `auth` de la suscripción push se guardan en claro.

Identidad, sesiones y plataforma:
- **N-10 (US-032, US-041, US-045, US-048):** la política de contraseña mínima es de 12 caracteres. Ningún documento la define.
- **N-11 (US-047, US-048, US-052):** el token de activación vence a las 72 h y el de recuperación a 1 h. Un token inválido devuelve 400 `invalid_token`. La URL base del enlace sale de `FRONT_BASE_URL`.
- **N-12 (US-052):** `GET /users/{id}/activation-link` no puede mostrar un enlace ya emitido, porque se guarda solo el hash del token. En la práctica duplica `resend-link`. Se propone dejar una sola ruta.
- **N-13 (US-042, US-043, US-045):**
  - El refresh token va en cookie HttpOnly y el access token solo en memoria.
  - Reusar un refresh ya rotado devuelve 401 y no revoca las demás sesiones.
  - Cambiar la contraseña revoca las otras sesiones del usuario, pero no la actual.
- **N-14 (US-033, US-035, US-036, US-038):**
  - Tolerancia de reloj de 30 s.
  - `/docs` y `/openapi.json` apagados en producción.
  - Variable `TRUSTED_PROXIES` para `X-Forwarded-For`.
  - Nonce de la CSP con `$request_id` y `sub_filter` de Nginx.
- **N-15 (US-016, US-094, US-111, US-112, US-135, US-156):** cada historia resolvió distinto el actor técnico de los procesos sin usuario:
  - un identificador de actor de sistema configurable por variable y un usuario `system` para el worker;
  - un usuario propio para los datos de demostración;
  - `--as <email>` en `import-members` y `migrate-provider`.
  
  Resuelto por N-15 de `DECISIONES.md` (sección D): un único usuario técnico `system@apex.local` (`SYSTEM_USER_ID`) y `--as <email>` en los comandos de CLI.
- **N-16 (US-005, US-020, US-115, US-136):**
  - `/health` se expone en la raíz y también en `/api/v1/health`.
  - El estado del backup es informativo y deja el código en 200.
  - Con OpenBao sellado, `/health` responde 503 y las rutas que usan el bus responden 503 `crypto_unavailable`.
- **N-17 (US-054):** la `version` de cada sección de configuración sirve como control de concurrencia (409 `version_conflict`). Una sección de una versión futura responde 404 `section_not_available`.
- **N-18 (US-055, US-057, US-058, US-154):** ningún documento define los campos de las secciones `gym`, `privacy` y `hours`, ni los rangos de validación de `memberships` y `classes`.

Socios:
- **N-19 (US-069):**
  - El documento es obligatorio; teléfono y correo son opcionales.
  - En v0.1, `data_consent_version` queda vacío.
  - La respuesta incluye una lista `warnings`, que no está en el contrato.
- **N-20 (US-073, US-075, US-076):**
  - El coach recibe 404 al abrir un socio dado de baja.
  - El coach puede cambiar el documento.
  - La baja no anula las membresías vigentes y no hay forma de reactivar al socio en v0.1.
- **N-21 (US-077):** los propósitos válidos de `contact_for_notification` son `notify` y `auth_link`. El propósito se guarda en `after` de la auditoría, porque `AuditEntry` no tiene columna para eso.

Planes y membresías:
- **N-22 (US-082):**
  - El contrato no tiene endpoint de baja de planes; se propone `DELETE /plans/{id}` como borrado lógico.
  - Para RN-08, "membresía activa" significa `pending_payment`, `active`, `expiring` o `frozen`.
  - El nombre del plan no tiene que ser único (US-078).
- **N-23 (US-083, US-121):**
  - El fin es inclusivo: el día de `end_date` el socio sigue al día.
  - El desfase 0 de un aviso cuenta como "por vencer".
- **N-24 (US-084, US-088):**
  - Se acepta un `start_date` en el pasado sin límite.
  - Con `renew: true` se ignora el `start_date` que llegue.
  - Hay un endpoint nuevo, `GET /members/{id}/memberships/renewal-preview`.
- **N-25 (US-087, US-089):**
  - ¿Una membresía `frozen` vuelve a `pending_payment` si se anula el pago que la cubría?
  - Si correr el fin de una congelación choca con una membresía futura, la congelación responde 409; no corre también la futura.
  - Solo se guarda la última ventana de congelación.
- **N-26 (US-092, US-108):** el resumen y el tablero cuentan socios por su estado resuelto, no membresías. Un socio cuya única membresía es una futura ya pagada cuenta como "al día".

Pagos y exportaciones:
- **N-27 (US-095, US-100):**
  - `paid_at` es opcional, no puede ser futuro (tolerancia de 5 minutos) y no tiene límite hacia atrás.
  - El mes del resumen se decide por `paid_at` en hora de Bogotá.
  - Sin cierre de caja, un pago registrado tarde cambia un mes ya revisado.
- **N-28 (US-095):** se aceptan pagos en membresías `expired` y `frozen`; solo `cancelled` se rechaza. `reference` es opcional en los tres medios.
- **N-29 (US-138, US-139):** las columnas de los CSV de socios y de pagos no están definidas. Se proponen separador `;` y BOM UTF-8.

Auditoría:
- **N-30 (US-103, US-104):**
  - Hay rutas nuevas: `GET /audit/{seq}` y `GET /audit/verify/last`.
  - Una verificación en segundo plano se pierde si el API se reinicia.
  - Un salto en `seq` cuenta como ruptura de la cadena.
- **N-31 (US-106, US-107):**
  - El historial de la ficha muestra solo la tabla `members`.
  - Los login fallidos de correos que no existen no se auditan.
- **N-32 (US-141, US-142):**
  - La firma de la cadena corre a las 07:00 con el resto del worker, no de noche.
  - Si OpenBao está sellado, la firma se reintenta 3 veces.
  - "Avisar" significa log y estado en pantalla.
  - La firma se marca atrasada a las 48 h.

Avisos:
- **N-33 (US-123):** un socio sin preferencias guardadas acepta todos los canales. Hay que validarlo frente a la Ley 1581.
- **N-34 (US-126):** el modelo no tiene chat de Telegram por socio, así que los avisos de Telegram van al chat del gimnasio.
- **N-35 (US-124, US-125):**
  - Máximo 3 intentos de envío (`NOTIFY_MAX_ATTEMPTS`).
  - El job recupera hasta 15 días sin correr.
  - No se manda el aviso de vencido a quien ya renovó.
- **N-36 (US-131):** los correos de activación y recuperación salen directo, no por la cola de avisos, y su texto está fijo en el código.
- **N-37 (US-195):** el push de récord se crea después del commit, contra la regla de que los handlers corren en la misma transacción. Además, `Notification.membership_id` pasa a ser opcional.

Clases y entrenamiento:
- **N-38 (US-159):** con `allow_over_capacity = false` el check-in responde 409, que se puede forzar. Esto choca con "el cupo es advertencia, no bloqueo".
- **N-39 (US-159):** un check-in fuera de `checkin_window_min` responde 422, lo que choca con RN-09. ¿Debe ser solo advertencia?
- **N-40 (US-155, US-161, US-160):**
  - `start_time` de la franja se guarda como hora local de Bogotá, una excepción a la regla de UTC.
  - Borrar una asistencia es un borrado físico, con el `before` guardado en la auditoría.
  - Devolver una clase reactiva una tiquetera `expired` si su fecha no ha pasado.
- **N-41 (US-166, US-168):**
  - Un WOD principal por fecha significa unicidad de `date`.
  - `score_type` no se puede cambiar si el WOD ya tiene resultados.
  - La asignación a una sesión es `PATCH /class-sessions/{id}`, que no está en el contrato.
- **N-42 (US-169, US-181):** un resultado registrado por coach nace `validated` y emite también `WodResultValidated`, para que RN-12 aplique desde la tablet.
- **N-43 (US-171):**
  - Un socio que no termina dentro del time cap queda con `seconds = time_cap_s`, después de los que terminaron.
  - `rx_plus` y `rx` comparten grupo en el leaderboard.
- **N-44 (US-175, US-176):**
  - Se guarda el hash del token de la TV.
  - El token va por query string, así que Nginx no debe registrarla.
  - Rate limit de 12 peticiones por minuto.
  - En la TV se muestra el nombre y la inicial del apellido.

Atleta, portal y cierre:
- **N-45 (US-178, US-180, US-181):**
  - Rangos de medidas: peso de 20 a 400 kg, estatura de 50 a 250 cm y grasa de 1 a 75 %.
  - Los RM van en kg.
  - Un RM manual menor o igual al vigente queda como histórico; si hay empate, queda vigente el más antiguo.
  - Un resultado `scaled` no deriva RM.
- **N-46 (US-182, US-183):** cada repetición de un benchmark es un WOD nuevo, así que se agrupa por título normalizado. La alternativa es un catálogo de benchmarks.
- **N-47 (US-185, US-186, US-189):**
  - La cuenta de portal la crea solo el admin.
  - El correo de login no sigue al del padrón.
  - Un recurso ajeno en `/me` responde 404.
  - El socio envía resultados de hasta 7 días atrás sin asistencia registrada.
- **N-48 (US-196, US-198):**
  - Los backups anteriores a v1.0 no se firman.
  - Si OpenBao no ofrece ML-KEM, la alternativa con liboqs deja la llave privada envuelta con un algoritmo clásico y debilita la protección.
  - Re-envolver llaves (US-199) es irreversible en la práctica y exige aprobación explícita del dueño.

Infraestructura:
- **N-49 (US-004, US-009):** se acepta la licencia `0BSD` en el front, y las fuentes se suponen bajo OFL 1.1.
- **N-50 (US-113, US-114, US-115, US-133):**
  - Tabla nueva `worker.job_runs`.
  - Backup a las 02:00, con 14 días de retención, incluyendo uploads desde v0.1.
  - La identidad `age` se monta para la verificación.
  - Desellado de OpenBao con Shamir de 5 llaves y umbral 3.
