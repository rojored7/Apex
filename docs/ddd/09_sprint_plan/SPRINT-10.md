# Sprint 10 · v1.0: portal del socio y cierre criptográfico post-cuántico

- Versión: v1.0.
- Épicas: EP-25 (portal del socio) y EP-26 (cierre criptográfico post-cuántico).
- Tamaño: 15 historias, 66 puntos y 284 h relativas (EP-25: 184 h; EP-26: 100 h).
- Nivel de detalle: bloques en orden de ejecución, sin slices. Se refina al llegar.
- Historias del sprint: US-185, US-186, US-187, US-188, US-189, US-190, US-191, US-192, US-193, US-194, US-195, US-196, US-197, US-198, US-199.

## Objetivo

Que cada socio entre a su propio portal de cinco pestañas (Inicio, Pagos, WODs, Progreso y Yo). Desde ahí:
- ve su membresía, sus pagos y sus recibos;
- envía resultados para que el coach los valide;
- ve su progreso;
- corrige sus datos de contacto;
- elige sus canales, incluido web push, y recibe el aviso de récord nuevo.

Además se cierra la parte criptográfica:
- los backups salen firmados;
- el CBOM se puede exportar también en CycloneDX;
- las DEK se re-envuelven con ML-KEM por un trabajo que se puede reanudar.

## Demo al final del sprint

1. **Cuenta del portal.** El admin crea la cuenta desde la ficha del socio. El correo de activación sale con el propósito `auth_link` (N-21, N-36).
2. **Acceso propio.**
   - El socio entra y ve sus 5 pestañas.
   - Un `/me/payments/{id}` de otro socio responde 404 (N-47).
3. **Resultados.**
   - El socio envía su resultado del WOD de hasta 7 días atrás; queda `pending`.
   - El coach lo valida desde la bandeja y se emite `WodResultValidated`.
   - Si mejora su RM, el socio recibe un push de récord. La fila `pending` se inserta en la misma transacción y la envía el job `notify` (N-37).
4. **Mis datos.**
   - El socio cambia su teléfono: se recifra y se reindexa.
   - No puede cambiar documento, nombres, sexo ni fecha de nacimiento (Q24).
   - Cambiar la contraseña revoca sus otras sesiones.
5. **Backups firmados.**
   - El backup nocturno sale firmado con `backup.signature`: ML-DSA, o Ed25519 si no está disponible (Q27).
   - `backup_check` y la restauración verifican la firma.
   - Los backups anteriores a v1.0 no tienen firma (N-48).
6. **Re-envoltura con ML-KEM.**
   - `cli` de `rewrap` con `confirm: "REENVOLVER"` y rol admin re-envuelve las DEK. Al reiniciar el proceso, todo sigue legible.
   - `GET /crypto/cbom` y `cli cbom` ofrecen el CBOM también en CycloneDX, como formato adicional, sin cambiar el JSON de US-146 (refinamiento de US-197).

## Dependencias de sprints anteriores

- **Sprint 9:**
  - US-179 (patrón de `reveal`);
  - US-180 a US-184 (consultas de athletes);
  - US-181 (emite `PersonalRecordSet`).
- **Sprint 8:**
  - US-168 (`GET /wods/today`);
  - US-169 y US-170 (modelo, trigger y corrección);
  - US-171 (el leaderboard solo muestra resultados validados).
- **Sprint 6:**
  - US-152 y US-153 (TLS: la Push API no funciona sin HTTPS fuera de `localhost`);
  - US-140 y US-141 (patrón de firma);
  - US-143 a US-146 (inventario, jobs y CBOM).
- **Sprint 5:**
  - US-121, US-123, US-124, US-125, US-129 y US-131 (reglas, preferencias, `notify`, historial y correo directo);
  - US-133 a US-136 (OpenBao).
  - US-137 (recibo PDF).
- **Sprints 4A y 4B:**
  - US-114, US-115 y US-116 (backup, `backup_check` y respaldo de la KEK);
  - US-113 (`job_runs`).
- **Sprints 2 y 3:**
  - US-041, US-045, US-047, US-048 y US-052 (auth, contraseña, activación y `resend-link`);
  - US-073, US-074, US-075 y US-077 (ficha, `reveal`, edición y `contact_for_notification`);
  - US-092 y US-095 (consultas de membresías y de pagos).
- **Sprint 1:** US-024 (`crypto_jobs` con `rewrap`) y US-027 (firma).

## Historias en orden de ejecución (por bloques)

1. **Bloque A · Cuenta y autorización propia (EP-25).**
   - US-185 · Crear la cuenta de portal: la ruta va en `auth/router.py` para evitar el ciclo members↔auth.
   - US-186 · Autorización propia en las rutas `/me`: `current_member_id`, `extra = "forbid"`, prueba de arquitectura y anti IDOR.
2. **Bloque B · Lecturas del portal (EP-25).**
   - US-187 · Inicio.
   - US-188 · Mis pagos y recibos, con la descarga auditada como `download`.
   - US-191 · Mi progreso, con las medidas en claro auditadas.
3. **Bloque C · Resultados del socio (EP-25).**
   - US-189 · Mis WODs y enviar resultado.
   - US-190 · Validar los resultados enviados, con la bandeja en el panel.
4. **Bloque D · Datos y avisos (EP-25).**
   - US-192 · Mis datos y contraseña.
   - US-193 · Mis avisos y canales: `email`, `whatsapp_link` y `push`, sin Telegram (N-34).
   - US-194 · Suscripción web push:
     - `push_subscriptions` con las llaves en claro (N-09);
     - `WebPushChannel` con pywebpush (MPL-2.0 sin modificar).
   - US-195 · Aviso de récord nuevo.
5. **Bloque E · Cierre criptográfico (EP-26).**
   - US-196 · Firma de backups: con `digest_file` (G-07), desde un job del worker y no desde el contenedor de backup.
   - US-197 · CBOM en CycloneDX.
   - US-198 · Envoltura de llaves con ML-KEM: por Transit, o con un adaptador `liboqs` con su debilidad documentada. `wrap_algorithm` se introduce en tres pasos.
   - US-199 · Re-envoltura reanudable de DEKs: una transacción por llave, y exige un backup firmado previo.

Waves:
- **Wave 0:**
  - llaves VAPID por `.env`;
  - service worker servido por Nginx;
  - `liboqs` compilada en CI y fijada en la imagen, con `OQS_INSTALL_PATH` fijo y prueba de arranque sin red.
- **Waves 3a y 3b:** los bloques A a E. El bloque E puede ir en paralelo lógico, pero se ejecuta después del D para no mezclar riesgos en la misma wave.
- **Waves 5a y 5b:**
  - Portal_Inicio, Portal_Pagos, Portal_WODs, Portal_Progreso, Portal_Datos y Portal_Avisos, en `PortalLayout`;
  - la bandeja de validación;
  - el menú de exportación del CBOM.

Opción de partición: si OpenBao no ofrece ML-KEM cuando llegue el sprint, el bloque E se ejecuta como un Sprint 10b, y el portal se libera sin esperar por él. Este riesgo ya está señalado en el desglose de EP-26.

## Migraciones que aplica

En orden ascendente:
- `0090_members_push_subscriptions` (US-194).
- `0091_members_channel_preferences_push` (US-193 y US-194).
- `0092_notification_rules_push_record` (US-195): agrega `push` al CHECK de canales.
- `0093_notifications_optional_membership_record` (US-195): `membership_id` pasa a ser nulo (N-37).
- `0094_auth_users_member_unique` (US-185).
- `0095_crypto_keys_wrap_algorithm_nullable`, `0096_crypto_keys_wrap_algorithm_not_null` y `0097_crypto_keys_purpose_kem` (US-198): cambio en tres pasos. También extienden la guarda de `0003`.
- `0098_crypto_jobs_one_running_per_kind` (US-199).

## Endpoints que expone

- **Cuenta de portal:** `POST` y `GET /api/v1/members/{id}/portal-account`.
- **Rutas `/me` (rol `member`, con `current_member_id`):**
  - `GET` y `PATCH /api/v1/me`;
  - `POST /api/v1/me/password`;
  - `GET /api/v1/me/summary`;
  - `GET /api/v1/me/payments` y `GET /api/v1/me/payments/{id}/receipt.pdf`;
  - `GET` y `POST /api/v1/me/results`;
  - `GET` y `POST /api/v1/me/metrics`;
  - `GET /api/v1/me/records`, `GET /api/v1/me/rms` y `GET /api/v1/me/benchmarks`;
  - `GET` y `PATCH /api/v1/me/channels`;
  - `GET /api/v1/me/notifications`;
  - `GET /api/v1/me/push-public-key`;
  - `POST` y `DELETE /api/v1/me/push-subscription`.
- **Validación (coach y admin):** `POST /api/v1/results/{id}/validate`.
- **Cambios en endpoints existentes:**
  - `GET /api/v1/crypto/cbom`, con el formato CycloneDX como extensión;
  - `GET /api/v1/crypto/jobs`, con los jobs `rewrap`;
  - `POST` y `PATCH /api/v1/notification-rules`, con el canal `push`.

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- Prueba de arquitectura anti IDOR (US-186): toda ruta `/me/*` declara `current_member_id`. Hay una prueba parametrizada por ruta.
- `test_banned_imports.py`: `oqs` y `pywebpush` solo donde corresponde. `oqs` solo en `core/crypto`.
- `test_audited_tables.py`: `push_subscriptions.endpoint` y sus llaves quedan excluidos del diff.
- `test_every_route_has_role.py` sobre las rutas `/me`.

## Riesgos y mitigación

1. [HIGH] La re-envoltura es irreversible: un fallo a mitad puede dejar una DEK inutilizable.
   - Mitigación:
     - verificar la nueva envoltura antes del `UPDATE`;
     - una transacción por llave;
     - poder reanudar;
     - exigir un backup firmado previo;
     - confirmación humana (`CLAUDE.md`).
2. [HIGH] IDOR en `/me/*`.
   - Mitigación: la prueba de arquitectura falla en CI, más la prueba anti IDOR por ruta, con 404 para recursos ajenos.
3. [MEDIUM] OpenBao sin ML-KEM ni ML-DSA.
   - Mitigación: la alternativa de N-48 y Q27, con el algoritmo guardado en el dato. Si hace falta, se parte el sprint en 10 y 10b.
4. [MEDIUM] `liboqs` no recomienda su uso en producción e intenta descargarse en tiempo de ejecución.
   - Mitigación: versión fijada en la imagen, prueba sin red y la decisión escrita en el ADR.
5. [MEDIUM] El push de récord llega con retraso si `notify` solo corre a las 07:00.
   - Mitigación: confirmar la frecuencia del job `notify` al refinar el sprint. No cambia el contrato.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E:
  - activación de la cuenta del portal;
  - las 5 pestañas;
  - envío y validación de un resultado;
  - push de récord en un navegador con HTTPS.
- Ensayo de re-envoltura con un reinicio del proceso a mitad del job y su reanudación.
- Backup firmado, verificado en una restauración limpia.
- Seguridad, revisada por `security-reviewer`:
  - anti IDOR;
  - lista blanca de campos editables;
  - `push_subscriptions` fuera de los logs y de la auditoría;
  - `liboqs` sin red;
  - `rewrap` solo con la confirmación literal y rol admin.
- `verify-delivery` sobre el stack con TLS. Se etiqueta `v1.0.0`.
