# Sprint 2 · cierre de la deuda de las revisiones de Fase 4 (backend)

Rama `feat/sprint-02-identidad-config-socios-planes`, desde `11cf7e9`. Fuentes: revisión de
seguridad V10 (N-1…N-9), revisión Python (H1–H3, M1–M11, LOW) y la parte backend de la revisión
general (M5 contraseñas, M7 errores en OpenAPI). Este archivo es la entrada para que el agente de
documentación lo integre en `docs/ddd/DECISIONES.md`, `docs/RUNBOOK.md` y `SPRINT-02.md` (en este
árbol no se editaron DECISIONES, RUNBOOK, README, CLAUDE.md, `.github/`, `scripts/` ni `web/`,
salvo regenerar `web/src/core/api/types.ts`).

Línea base antes de tocar nada: suite `-m 'not perf'` 1856 ok, 4 omitidas, 3 deseleccionadas;
cobertura de `app` 94 %; ruff y mypy limpios. Cada corrección de comportamiento se hizo en TDD:
prueba en rojo (registrada abajo) y luego el cambio.

## Estado por hallazgo

### Seguridad (V10)

- **N-1 · commit después de la respuesta (MEDIUM): corregido.** `core/db.py` define
  `SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]`; lo usan
  `core/security.current_user` y los cuatro routers (`auth`, `members`, `plans`, `settings`, con
  `Session = SessionDep`). Docstrings de `db.py`, `security.py` y `context.py` corregidos (N-9).
  Pruebas: `tests/core/test_session_dependency.py::test_session_dep_confirma_antes_de_enviar_el_cuerpo`
  (`send` ASGI espía; rojo: `['response-body', 'commit']`) y
  `::test_un_error_de_commit_llega_al_cliente_como_envelope` (rojo: 200 con la escritura
  revertida; verde: 500 `internal_error` y 0 filas); `tests/architecture/test_session_scope.py`
  (todo nodo `get_session` del árbol efectivo de `create_app()` con `scope == "function"`, 29
  rutas). Re-ejecutadas `tests/architecture`, `tests/auth`, `tests/members`.
- **N-2 · NUL, formato y `offset` fuera de rango (MEDIUM) + Python H2: corregido.**
  `core/validators.py`: `SafeText` (NFC, recorte, sin `Cc` ni `Cf`, algo visible),
  `SafeMultilineText` (admite tabulador y saltos; rechaza los demás `Cc` y los controles
  bidireccionales U+202A–U+202E y U+2066–U+2069) y `EmailAddress` rechaza `Cc`/`Cf`.
  Aplicado a `MemberCreate.first_name/last_name`, `EmergencyContactIn.name/relationship`,
  `PlanCreate.name` (reemplaza su validador propio), `GymSettings.name/address/city/phone/
  whatsapp`, `PrivacySettings`/`PrivacyView.policy_version` (`SafeText`) y `policy_text`
  (`SafeMultilineText`). `members.service._build` normaliza los nombres a NFC.
  `PageParams.offset` con `le=MAX_OFFSET` (1.000.000). Pruebas (todas en rojo antes: 500 de
  asyncpg o 201/200 con el carácter guardado): `tests/core/test_validators.py` (unitarias),
  `tests/core/test_pagination_router.py::test_offset_por_encima_del_tope_da_422_con_field_offset`,
  `tests/auth/test_safe_text_router.py` (login con `a\u0000@x.co` → 422, `POST /users`,
  `PATCH /users/{id}`, `/users?offset=…`), `tests/members/test_safe_text_router.py` (`"a\x00b"`,
  `"\u200b"`, `"Pe\u202ena"`, `"\x07"`, contacto con NUL, `"Jose\u0301"` → `José` en la fila, y
  `/members?offset=…`), `tests/plans/test_router_list.py::test_offset_fuera_de_int64_da_422_field_offset`,
  `tests/settings/test_safe_text_router.py` (gym con NUL/U+200B/U+202E, privacy con NUL/bidi y
  saltos de línea aceptados).
- **N-3 · límite por cuenta por /24 (MEDIUM): corregido por decisión del orquestador.** Clave
  `"{correo}|{ip_bucket_key(ip, ipv4_prefix=32)}"` (`ACCOUNT_IPV4_PREFIX = 32`, `/64` en IPv6),
  igual que `rate_limit`; el tope global por correo (100/h) y el bloqueo a 20 siguen.
  `auth/sessions.py`. Pruebas: `tests/auth/test_login_service.py::test_dos_ips_del_mismo_24_no_comparten_el_cupo_por_cuenta`
  (nueva, rojo antes) y `::test_diez_fallos_desde_una_ip_no_impiden_entrar_desde_otra`
  (**prueba de B2 actualizada**: fijaba el 429 desde `IP_A2`, del mismo /24; ahora fija el 429
  desde la misma IP; quedó objetivamente desactualizada por la decisión). `unlock` sigue
  olvidando las subclaves `correo|...` de cualquier IP.
- **N-4 · `unlock-user` sin `--as` (LOW): corregido.** `--as` obligatorio y admin activo (como
  `issue-reset-link`). `cli.py`. Pruebas: `tests/cli/test_unlock_cli.py`
  (`test_sin_as_sale_con_2_y_no_toca_nada`, `--as` coach → 2, auditoría nunca del técnico) y
  `tests/cli/test_seed_cli.py::test_unlock_user_carga_los_services_de_los_modulos` (ahora con
  `--as`).
- **N-5 · CI sin `E2E_ADMIN_*` ni auditoría de dependencias (LOW): fuera de este árbol** (CI lo
  lleva el agente de CI/docs; `961e0d6` ya exportó `E2E_ADMIN_*`).
- **N-6 · IP real en el borde con Docker Desktop (LOW): fuera de este árbol** (RUNBOOK; sin
  cambio de código).
- **N-7 · piso de login a la mediana (LOW): corregido.** `LOGIN_MIN_DURATION_MS` por defecto 150
  (p99) en `Settings` y `.env.example`. Prueba: `tests/core/test_config.py::test_el_piso_de_login_por_defecto_es_150_ms`.
- **N-8 · cambio de correo de otro admin (LOW, riesgo US-131): corregido.** `update_user` da 409
  `user_not_eligible` si cambia el correo de otro admin activo con contraseña. `auth/users.py`,
  docstring de `UserNotEligible`. Prueba: `tests/auth/test_update_user_admin_email.py`.
- **N-9 · docstring de `db.py` (doc): corregido** con N-1.

### Python

- **H1 · `auth/service.py` de 1257 líneas: corregido.** Partido en `auth/events.py` (88),
  `auth/sessions.py` (login, refresh, logout, cargador del principal, sleeper y piso; 518),
  `auth/users.py` (seed, lecturas para otros módulos, me, change_password, list/create/get/
  update/delete/lock/unlock/revoke_sessions; 595) y `auth/links.py` (reset, forgot, issue_link,
  resend_link; 225); `service.py` es la fachada (117 líneas) con `__all__` y el registro del
  `PrincipalLoader`. Las definiciones se copiaron con `ast` (sin reescribirlas); solo se
  renombraron `_verify` → `verify_password_or_dummy` y `_wait_floor` → `wait_floor` (los usan
  dos archivos). `normalize_login_email` y `truncate` pasaron a `rules.py`. Arquitectura:
  `PRIVATE_HELPERS` de `tests/architecture/_imports.py` suma `events`, `sessions`, `users` y
  `links` (prueba parametrizada en `test_find_forbidden_imports.py`); `test_service_import_graph.py`
  revisa todos los archivos del módulo (la arista `auth → settings` vive ahora en `users.py`) con
  el control `test_las_aristas_del_mapa_se_ven_tras_partir_auth`. Nueva
  `tests/architecture/test_file_and_function_size.py`: ningún archivo de `api/src` pasa de 800
  líneas ni ninguna función de 50.
- **H2: corregido** con N-2.
- **H3 · duplicación de búsqueda e IntegrityError: corregido.** `core/search.py` (`LIKE_ESCAPE`,
  `escape_like`, `contains_pattern`, `strip_accents` con NFKD y `casefold`, `sql_fold` con
  `translate` y la tabla completa áéíóúüñàèìòùâêîôûäëïöç en minúsculas y mayúsculas, por si el
  `LC_CTYPE` no pliega `lower('Á')`, y `clean_query`) y `core/db.violated_constraint(error)`
  (lee `error.orig.__cause__.constraint_name` de asyncpg). Reemplazan las copias de
  `auth/rules.py`, `members/service.py`, `plans/service.py` y el "nombre in str(error.orig)" de
  auth, members, plans y settings. Pruebas: `tests/core/test_search.py` (unitarias, `sql_fold`
  contra PostgreSQL igual que `strip_accents`, `violated_constraint` con una violación real) y
  las de carrera existentes (alta concurrente de socio, plan, usuario y primer guardado de
  settings) en verde.
- **M1 · `change_password` con `FOR UPDATE` durante tres argon2: corregido.** Verifica y hashea
  sin candado; luego `FOR UPDATE` y exige que `password_hash` no haya cambiado. Si cambió, 422
  `invalid_current_password` sin sumar al tope (ver decisión). Pruebas:
  `tests/auth/test_change_password_concurrency.py` (sondeo `FOR UPDATE NOWAIT` desde otra
  conexión durante la verificación: rojo `[True]`, verde `[False]`; dos cambios concurrentes,
  exactamente uno falla con `InvalidCurrentPassword` y el hash final es el del ganador).
- **M2 · tope por cuenta no atómico: corregido.** `core/ratelimit.reserve` (comprueba y suma bajo
  el mismo candado) y `release` (quita la marca de esa reserva); `login` reserva antes de argon2
  y devuelve el cupo si el login sale bien (si el global no tiene cupo, devuelve el de la
  cuenta). Pruebas: `tests/auth/test_login_service.py::test_una_rafaga_paralela_no_supera_el_tope_por_cuenta`
  (30 logins en paralelo con 30 conexiones; rojo: 11 verificaciones con tope 10; verde: como
  máximo 10), `::test_un_login_correcto_devuelve_el_cupo_reservado` y
  `tests/core/test_ratelimit.py::test_reserve_es_atomica_y_release_devuelve_el_cupo`.
- **M3 · `gym_name` estricto: corregido.** `try/except ValidationError` con aviso sin el valor y
  respaldo `"APEX"`. Prueba: `tests/settings/test_gym_name_fallback.py` (`{"name": 5}`, vacío,
  campo extra, sin `name`; `/auth/me` 200 con `APEX`).
- **M4 · `updated_at` expirado: corregido.** `CommonColumnsMixin.__mapper_args__ =
  {"eager_defaults": True}`; quitados los tres `session.refresh(...)` (members, plans,
  settings). Prueba: `tests/auth/test_eager_defaults.py` (tras `update_user` y `lock`, leer
  `updated_at` sin `await`; rojo: `MissingGreenlet`). Suite completa en verde sin los refresh.
- **M5 (búsqueda por nombre sin índice / LC_CTYPE): mitigado.** La parte de locale la cubre
  `sql_fold` con mayúsculas en la tabla; el índice por nombre queda para cuando haya volumen
  (no se pidió en este cierre).
- **M6 · `no-store` solo en auth: corregido.** `core/http.no_store` (sale de `auth/cookies.py`)
  en el `APIRouter` de members, plans y settings y en cada ruta de auth. Prueba:
  `tests/architecture/test_no_store_routes.py` (toda ruta con rol lleva `no_store`; por HTTP
  `GET /members` y `GET /plans` responden `no-store`).
- **M7 · funciones de más de 50 líneas: corregido.** `main.create_app` → `_startup` y
  `_install_middleware`; `change_password` → `_verified_current_hash`, `_locked_if_unchanged` y
  `_store_new_password`; `update_user` → `_apply_user_changes`. Lo vigila
  `test_file_and_function_size.py`.
- **M8 · preámbulo repetido del CLI: corregido.** `cli_runtime(settings)` (listeners, services,
  engine y `dispose`) y `_admin_actor_and_target`. `_run` ahora copia el contexto al hilo
  (el reloj y el actor de quien llama llegan al comando). Pruebas: `tests/cli/*` en verde.
- **M9 · `User.role` como `str`: corregido.** `Mapped[Role]` (el `Literal` de `core.security`);
  quitados los 4 `type: ignore[arg-type]`. mypy `--strict` limpio.
- **M10 · cierre de enlaces vencidos: corregido.** `close_open_one_time_tokens` filtra
  `expires_at > now`. Prueba: `tests/auth/test_one_time_token_closure.py::test_el_cierre_ignora_los_enlaces_ya_vencidos`.
- **M11 · `refresh_current` por petición: medido, aceptado sin caché.** Ver decisión.

### Revisión general (parte backend)

- **M5 · contraseña mínima: corregido.** `core/config.PASSWORD_MIN_LENGTH_FLOOR = 12`, expuesto
  como `core.security.PASSWORD_MIN_LENGTH`; validador de `Settings`: en `ENV=production`,
  `PASSWORD_MIN_LENGTH >= 12`; `ChangePasswordIn.new_password` y `ResetIn.new_password` con
  `min_length=12` (el contrato publica `minLength: 12`). Pruebas:
  `tests/core/test_config.py::test_en_produccion_la_contrasena_minima_no_baja_de_12` y
  `::test_en_dev_la_contrasena_minima_puede_bajar_y_en_produccion_subir`;
  `tests/auth/test_me_router.py` y `tests/auth/test_reset_forgot_router.py` actualizadas (ver
  decisión sobre el código de error).
- **M7 · errores genéricos en el OpenAPI: corregido.** `core/errors.responses_for(*codes)`;
  `create_app` ya no pone `responses=ERROR_RESPONSES`; cada router o ruta declara sus códigos y
  el gancho solo agrega `500` y convierte en `ErrorResponse` los códigos del catálogo (el `503`
  de `/health` queda con `HealthOut`, antes se pisaba con `ErrorResponse`). Prueba:
  `tests/architecture/test_error_codes_per_route.py` (ninguna operación con los ocho; `/health`
  sin 400/401/403/404/409/422/429 y con 503 `HealthOut`; 401 en toda ruta con sesión; 429 solo
  en las que tienen límite; 422 solo con parámetros o cuerpo; todo genérico → `ErrorResponse`).

### LOW de Python

- L1 `_snapshot(fila: Plan | Row[*tuple[Any, ...]])` tipado y `detail` sin variable de salida.
- L3 `forgot(email, *, policy)` sin `session` ni `ip` (el router ya no abre sesión para forgot).
- L4 docstrings en las funciones públicas nuevas y en las que faltaban de los services de auth,
  members, plans y settings.
- L6 `birth_date` entre 1900-01-01 y hoy (`BIRTH_DATE_MIN`). Prueba:
  `tests/members/test_member_rules.py::test_fecha_de_nacimiento_anterior_a_1900_da_422`.
- L8 `tests/cli/test_issue_reset_link_cli.py` usa `reloj` (vence exacto en `T0 + 1 h`) en vez de
  `datetime.now` real.
- L9 `tests/conftest.py`: `test_database_url` falla si el nombre de la base no contiene `test`
  (protege `LIMPIEZA_DE_SESION` y `dos_sesiones`). Prueba: `tests/test_ci_database.py::test_la_limpieza_solo_corre_contra_una_base_de_prueba`.
- L2, L5, L7: sin cambio (contratos sin caller hasta Sprint 3; `list` es el nombre del contrato;
  las pruebas de 0006/0007 ya comparan nombres finales).

## Decisiones para DECISIONES.md

- **S2-R1 (N-3).** El límite por cuenta del login usa la IPv4 exacta (`/32`, `/64` en IPv6),
  igual que `rate_limit`. Motivo: en la LAN del gimnasio (P7) todos comparten un /24 y un
  dispositivo con diez fallos negaba el login de las cuentas no exentas. La rotación dentro del
  /24 la siguen frenando el tope global por correo (100/h) y el bloqueo a 20 fallos. La prueba de
  B2 que fijaba el 429 desde otra IP del mismo /24 se actualizó por esta decisión.
- **S2-R2 (M2).** El cupo por cuenta y el global se reservan de forma atómica antes de argon2 y se
  devuelven si el login sale bien; un 429 del global devuelve la reserva de la cuenta. El efecto
  visible es el mismo (solo cuentan los fallos), sin la carrera de `peek` + `record`.
- **S2-R3 (N-8).** `PATCH /users/{id}` no cambia el correo de OTRO admin activo con contraseña
  (409 `user_not_eligible`), la regla L-13 aplicada al correo. El propio admin sí puede cambiar el
  suyo (ya conoce su contraseña; no hay toma de cuenta). Un admin pendiente de activación o
  bloqueado sí se corrige (su enlace de activación se cierra al cambiar el correo, LOW-3 de B5).
- **S2-R4 (M1).** Si otro cambio de contraseña ganó la carrera entre la verificación (sin
  candado) y el `FOR UPDATE`, se responde 422 `invalid_current_password` (la "actual" tecleada
  ya no lo es) sin sumar al tope por usuario: no es un intento de adivinar. Se prefirió a un 409
  nuevo para no agregar un código al contrato por un caso que el front trata igual.
- **S2-R5 (M11).** `refresh_current` no se cachea. Medición (500 llamadas tras 20 de
  calentamiento): desde el host contra `db_test`, mediana 0,707 ms, p95 0,788, p99 0,936
  (`SELECT 1` del mismo camino: 0,541 ms de mediana, casi todo es ida y vuelta); dentro del
  contenedor del api contra `db`, la consulta de marca (`_marca`) da mediana 0,407 ms, p95 0,567,
  p99 0,655. Por debajo de 1 ms: un TTL de 5 s solo agregaría una ventana en que una rotación de
  otro proceso no se ve.
- **S2-R6 (M5 general).** El piso de `PASSWORD_MIN_LENGTH` en producción es 12
  (`PASSWORD_MIN_LENGTH_FLOOR` en `core/config.py`, expuesto como `core.security.PASSWORD_MIN_LENGTH`)
  y el contrato publica `minLength: 12` en `new_password`. Consecuencia: una contraseña nueva de
  menos de 12 caracteres la rechaza el schema con 422 `validation_error` (`field=new_password`),
  antes de la política; `weak_password` queda para la lista de comunes y "igual a la actual". El
  front ya valida 12 con Zod.
- **S2-R7 (N-2).** Texto libre en dos tipos: `SafeText` (una línea: sin `Cc` ni `Cf`) y
  `SafeMultilineText` (la política de privacidad: admite tabulador y saltos; de `Cf` solo rechaza
  los controles bidireccionales, para no romper el pegado desde un procesador con guion suave o
  ZWJ). `offset` tiene tope de 1.000.000.
- **S2-R8 (N-1).** Toda ruta y `current_user` piden la sesión con `SessionDep`
  (`scope="function"`); el commit corre antes de enviar la respuesta. Nunca `Depends(get_session)`
  suelto (mezclar alcances abre dos sesiones); lo exige `test_session_scope.py`.
- **S2-R9 (N-4).** `cli unlock-user` exige `--as` de un admin activo. **RUNBOOK §(ciclo de
  vida), línea con `unlock-user … --as <correo de una persona activa>`: cambiar a "de un admin
  activo"** (no se editó RUNBOOK en este árbol).
- **S2-R10 (H1).** Un `service.py` que crece se parte en archivos privados del módulo y queda
  como fachada con `__all__`; otros módulos siguen importando solo `service.py`. Topes: 800
  líneas por archivo y 50 por función (`test_file_and_function_size.py`).
- **S2-R11 (M7 general).** Los errores del OpenAPI se declaran por ruta con `responses_for`; el
  gancho agrega `500` a todas y no toca códigos fuera del catálogo (`503` de `/health`).

## Revisión de código del cierre (python-reviewer, solo lectura)

Sin CRITICAL, HIGH ni MEDIUM. Confirmó que la partición de auth conserva cada cuerpo (salvo los
cambios intencionales), el orden de candados admins → usuario → token, que ningún camino deja
mal tomada la reserva del límite y que el timing del login no cambió. LOW atendidos:
- Salidas de settings con texto seguro: un valor guardado antes de N-2 con `Cf` rompía
  `GET /settings/gym`/`privacy`. **Corregido:** `GymView` (nuevo) y `PrivacyView` sin `SafeText`;
  `SECTION_VIEWS` y `GymSectionOut` los usan; `service.get(gym)` devuelve `GymView`. Prueba:
  `tests/settings/test_safe_text_router.py::test_una_seccion_guardada_antes_del_texto_seguro_se_sigue_leyendo`
  (rojo antes) y `test_settings_service.py` ajustada al tipo de salida.
- Aceptados con motivo: (a) un login con rehash de argon2 entre la verificación y el candado de
  `change_password` da un `invalid_current_password` falso (carrera rara, el usuario reintenta;
  sin suma al tope); (b) con `ENV=dev` y `PASSWORD_MIN_LENGTH < 12` el schema exige 12 (el
  contrato es el de producción; en dev solo afecta pruebas manuales); (c) `no-store` no sale en
  el envelope de error (no lleva datos de personas; Nginx lo pone en todo `/api/`); (d) el
  router de socios no declara 404 porque todavía no hay rutas de detalle (Sprint 3 lo agrega con
  `responses_for(404)`).

## Pendientes para otros árboles (no se tocaron aquí)

- RUNBOOK: `unlock-user` exige `--as` de admin (S2-R9); el piso de login pasa a 150 ms (N-7) si
  el RUNBOOK cita 75; N-6 (IP real en el borde) y la nota de que el api y Nginx ponen
  `Cache-Control: no-store` (la respuesta lleva la cabecera dos veces con el mismo valor).
- CI: N-5 (`npm audit`, `pip-audit`).

## Evidencia

- Suite `PYTEST_ADDOPTS="-m 'not perf'"`: 1987 ok, 4 omitidas (NTFS y US-074), 3 deseleccionadas
  (perf), 0 fallos (línea base: 1856). Cobertura de `app`: 96 % (línea base 94 %).
- `uv run pytest -m perf -q`: 3 ok.
- `ruff format --check .`, `ruff check .` y `mypy src` (`--strict`, 72 archivos): limpios.
- Contrato P-API: `export-openapi` dos veces, salidas idénticas byte a byte; `npm run gen:api`,
  `npx vitest run src/core/api/types.contract.test.ts` (5 ok) y `npx tsc --noEmit` limpios; la
  suite completa del front (`npx vitest run`) 1676 ok. `new_password` publica `minLength: 12`.
- Docker: el api recargó por el bind de `src` (WatchFiles); `build api` (la imagen del servicio
  `tools`, por `cli.py`) y `up -d api`: healthy, migraciones al día, keyring con 8 llaves.
- Smoke por Nginx `:8180`: `/api/v1/health` 200; login del admin 200; `POST /auth/login` con
  `"a\u0000@x.co"` → 422 `validation_error` `field=email`; `GET /users?offset=99999999999999999999`
  → 422 `field=offset`; `GET /members` y `GET /plans` 200 con `Cache-Control: no-store`;
  `POST /members` con NUL en el nombre → 422 `field=first_name`; login + refresh inmediato + logout
  (200/200/204) con la fila rotada y la sucesora revocada en `auth.refresh_tokens` (la escritura
  del login ya estaba confirmada cuando llegó el refresh: N-1 en vivo).
- Gates y checkpoint: ver el reporte del cierre (se corren después de escribir este archivo,
  sin editar entre ellos).
