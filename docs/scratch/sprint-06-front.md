# Cuaderno del front del Sprint 6 (worktree `.claude/worktrees/sprint-06-front`, rama `feat/sprint-06-front`)

## F1 · Estado de la firma (US-142)

- Base: `2fca6c4` (checkpoint de C5, rama `feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`). `npm ci` hecho en `web/`; `gen:api` sin diff.
- Rojo: `features/system/api.test.tsx` (`useLatestSignature`, `useVerifyChain` con firmas), `components/SignatureStatus.test.tsx`, `VerifyChainButton.test.tsx`, `pages/AuditPage.test.tsx`; módulo `SignatureStatus` inexistente al inicio.
- Verde: `features/system/{api,schemas}.ts` (`SIGNATURE_LATEST_KEY`, `signaturesLatestSchema`, campos planos de firmas en `verifyResultSchema`, todos `nullish`), `components/SignatureStatus.{tsx,module.css}`, `VerifyChainButton.tsx`, `pages/AuditPage.tsx`; `shared/ui/{StatusTag.tsx,statusLabel.ts}` suman la variante `signature` (como `payment` en S3-F6).
- Decisiones:
  - El estado sale del contrato: `latest` nulo = Sin firmas; `state=invalid` = Alterada (manda sobre el atraso); `is_late` = Firma atrasada; `state=ok` = Íntegra. `state=none` con firma registrada no pinta etiqueta: dice «Última firma registrada… Pulsa «Verificar ahora»» (no afirma integridad sin verificar).
  - El algoritmo se muestra como `Ed25519` (variantes de mayúsculas se normalizan; otro valor sale tal cual).
  - Nunca «no verificable»: con el custodio sellado la verificación es completa (S6-D81, D104); solo el `CustodyNotice` global informa del sellado.
  - Una verificación terminada (200, o 202 resuelto por sondeo) invalida `["audit","signatures","latest"]`.
  - Una verificación con `ok=false` por firma y sin `broken_at_seq` no dice «Cadena íntegra»: dice «Firma alterada en el registro seq X» con enlace a `?seq=X`.
- Pruebas que cambian: `AuditPage.test.tsx` quita «ML-DSA» de los DESIGN-GAP exigidos y exige que no aparezca; el test de llamadas a `/audit/*` excluye `signatures/latest`; `test/audit.tsx` suma `signatureInfo`, `signaturesLatest`, `signedVerifyResult` y el handler por defecto.
- E2E: `tests/e2e/audit.spec.ts` (preview, 20 casos verdes: 5 estados × claro/oscuro con axe) y `tests/e2e/stack/audit-signature.spec.ts` (escrito, no corrido; V7, tras `--run-once sign_audit`).
- DESIGN-GAP: cerrado el de «ML-DSA» (BRECHAS 14.6). Ninguno nuevo; el aviso de custodio sellado es el de S5-F5.
- Pendiente: revisión `security-reviewer` y sello `slice-gate.sh` (orquestador); fila de «Exportar rango» sigue en 13.10.

- Revisión de seguridad 0C/0H/2M/3L: M1 y M2 corregidas, L1 corregida, L2 y L3 aceptadas.
  - M1: `web/.vitest/` (salida JSON de vitest con rutas locales) borrado y añadido a `web/.gitignore`.
  - M2: el error de la firma sale de `auditErrors.signatureError` (403, 429 con espera y genérico); con 429 y 403 no hay «Reintentar».
  - L1: `through_seq` de la firma reutiliza `seqSchema` (positivo).
  - L2 (aceptada): los `px` literales del CSS siguen el precedente de `VerifyChainButton.module.css`.
  - L3 (aceptada): el `test.skip` del spec `stack/` es correcto; el proyecto `preview` lo ignora con `testIgnore`.

## F3 · Foto y pestaña Adjuntos (US-148, US-150)

- Base: `e85bd22` (checkpoint de F1, rama `feat/sprint-06-front`). `gen:api` sin diff (`AttachmentOut`, `photo_attachment_id` ya estaban).
- Rojo: `features/attachments/pages/AttachmentsTab.test.tsx` (24 casos), `features/attachments/lib/attachmentText.test.ts`, `shared/data/memberPhoto.test.ts` (6), `features/members/components/MemberPhoto.test.tsx` (8), `core/api/client.test.ts` (tipos de `api.blob`); módulos inexistentes al inicio. Helper `test/attachments.tsx`.
- Verde: `features/attachments/{api,schemas,attachmentErrors}.ts`, `lib/attachmentText.ts`, `components/AttachmentDownloadButton.tsx`, `pages/AttachmentsTab.tsx`; `shared/data/memberPhoto.ts`; `features/members/components/MemberPhoto.tsx`; `MemberDetailPage` (foto en el encabezado, Adjuntos sin `disabledUntil`), `MembersListPage` y `MemberCardList` (miniatura); `PageHeader` suma `leading`; `core/api/client.ts`; `config/{routeTable,routes.reference,features}.ts`; `permissions.ts`.
- Decisiones:
  - La pestaña es hija de `members` (`/socios/:id/adjuntos`, `members.view`), sin feature `attachments` aparte (anotado en `features.ts`).
  - `attachments.download.restricted` (solo admin) en la matriz de permisos: el coach no ve «Descargar» en `consent`/`other` (M-6) y lee «Solo administradores»; el 403 del api se muestra igual.
  - `useMemberPhoto`: `useQuery` con `gcTime: 0`, sin reintentos; el `blob:` se crea en un efecto y se revoca al desmontar y al cambiar de id; un error deja el marcador (no rompe la pantalla).
  - Descarga con `useBlobDownload` (`api.blob` + `a[download]`), una instancia por fila; 403 y 404 con texto propio, el resto con los mensajes de descargas.
  - Tamaño en base 1024 con coma decimal («220 KB», «1,5 MB»); «quién subió»: `uploaded_by_name` si llega, si no «Usuario <8 hex>» (el contrato no trae el nombre: BRECHAS 14.10).
  - `BLOB_CONTENT_TYPES` suma `image/jpeg`, `image/png` y `application/json`; `BLOB_ACCEPT` se deriva de la lista.
  - `memberRowSchema` (estricto) y `memberDetailViewSchema` aceptan `photo_attachment_id` (nulo por defecto).
- Pruebas que cambian: `client.test.ts` (JSON ya no se rechaza; `image/gif`, `image/svg+xml` sí), `permissions.test.ts`, `routes.test.ts` (Adjuntos, última hija), `schemas.test.ts` (diez claves), `MemberDetailPage.test.tsx` (Adjuntos habilitada), `PageHeader.test.tsx`, `MembersListPage.test.tsx`.
- E2E: `tests/e2e/member-tabs.spec.ts` (preview, 16 casos verdes; Adjuntos con axe en claro y oscuro a 390 y 1440; a 390 la tabla es de tarjetas) y `tests/e2e/stack/members-attachments.spec.ts` (escrito, no corrido; V7).
- DESIGN-GAP: tabla de Adjuntos (14.4, cerrada con el gap en `AttachmentsTab.tsx`); el gap de la foto de `MemberCardList` se cierra (14.9). Campo de foto y autorización en el formulario siguen en F4 (14.2, 14.3).
- Pendiente: revisión `security-reviewer` y sello `slice-gate.sh web/attachments` (orquestador); nombre de quien subió (14.10).

- Revisión de seguridad 0C/0H/2M/4L: todas corregidas.
  - M1: `application/json` sale de `BLOB_CONTENT_TYPES` (solo va en el `Accept`: `[...BLOB_CONTENT_TYPES, "application/json"]`, S6-D120); vuelve la prueba «rechaza application/json».
  - M2: `useMemberPhoto` con `gcTime` de 60 s: el Blob se reutiliza entre lista y ficha; el `blob:` se sigue revocando por componente.
  - L1: `useMemberPhoto` lanza `unexpected_content_type` si la respuesta no es `image/*`.
  - L2: `id`, `owner_id`, `uploaded_by` (adjuntos) y `photo_attachment_id` (socios) con `z.string().uuid()`.
  - L3: `mime` de `AttachmentOut` pasa a `z.string()`.
  - L4: `AttachmentDownloadButton` usa `instanceof ApiError`.

## F4 · Foto y autorización en el formulario (US-148, US-149)

- Base: `8fef9ff` (checkpoint de F3, rama `feat/sprint-06-front`). `gen:api` sin diff.
- Rojo: `core/api/client.test.ts` (`api.upload`, 12 casos), `features/members/components/PhotoField.test.tsx` (17), `ConsentSection.test.tsx` (14), `features/members/schemas.test.ts` (15 nuevos: `fileError`, `photoFieldSchema`, `consentFileFieldSchema`), `memberErrors.test.ts` (errores de subida y 422 de `data_consent_at`), `api.test.ts` (`subirAdjunto`, `useSubirAdjunto`), `lib/uploadPending.test.ts` (4), `shared/data/privacyVersion.test.tsx` (5), `pages/MemberFormPage.photo.test.tsx` (alta y edición, claro y oscuro, 38). Solo `schemas.test.ts` y `memberErrors.test.ts` se vieron en rojo antes del Verde; en los demás Rojo y Verde se escribieron seguidos (el Verde pasó a la primera).
- Verde: `core/api/client.ts` (`api.upload`, `UPLOAD_TIMEOUT_MS`, `UPLOAD_TOO_LARGE_MESSAGE`), `core/api/{status,errorCodes}.ts`, `features/members/{api,schemas,memberErrors}.ts`, `lib/uploadPending.ts`, `components/{PhotoField,ConsentSection}.tsx` (+ CSS con tokens), `MemberFormFields`, `MemberEditFields`, `MemberFormPage`, `MemberEditView`; `shared/data/privacyVersion.ts`; `test/server.ts` suma `rawBody` a `RecordedCall`.
- Decisiones:
  - `api.upload(path, file, {kind})`: `fetch` con `body: file`, `?kind=`, `Content-Type` = `file.type` o `application/octet-stream`, 30 s, mismo manejo del 401 (un reintento con el mismo archivo), 503 `crypto_unavailable` con el aviso global; nunca reintenta un 503 `busy`. Un 413 sin envelope (Nginx) o con él llega como `file_too_large` con el mismo mensaje.
  - `fileError(kind, file)` es la única regla (tipo, 5 MiB exactos, vacío) y la usan el campo y Zod. Un archivo inválido avisa en el campo y NO se entrega al formulario (`onChange(null)`): nada se pierde.
  - `photo` y `consent_file` viven en los valores de React Hook Form (`File | null`) pero nunca viajan en el JSON (`toMemberCreate` y `toMemberPatch` no los leen).
  - Orden al crear: `POST /members` → foto → documento (`kind=consent`). Un fallo de subida no deshace el alta: pantalla «El socio quedó creado sin foto» con enlaces a la ficha y a la edición (el formulario se cierra para no repetir el `POST`). Al editar: PATCH solo si hay cambios, luego las subidas; con fallo se queda en la edición («Los cambios se guardaron, pero la foto no se subió») y lo que sí subió se limpia del formulario.
  - Sin cambios y sin archivos la edición sigue diciendo «No hay cambios para guardar»; con solo un archivo no hay PATCH.
  - La versión vigente sale de `GET /settings/privacy` (solo admin) con clave propia `["settings","privacy","version"]` en `shared/data` (una feature no importa otra). Publicada: la versión; sin política: «versión no registrada»; ilegible (coach, 403): «Se registra la versión vigente al guardar».
  - La fecha de aceptación es «ahora» en Bogotá, fija mientras la casilla siga marcada; fecha y versión son de solo lectura y no viajan (las fija el api, S6-C3).
  - El 422 de `data_consent_at` se mapea a la casilla (alta y edición) y le lleva el foco desde `ConsentSection`.
  - Con la autorización ya registrada (edición) se muestra su texto, sin casilla, y aún se puede subir el documento firmado.
  - 422 `unsupported_type` y 413 tienen mensajes distintos en pantalla (tipo vs. 5 MB); el brief los pedía «con el mismo mensaje» solo para el cliente HTTP, donde ambos conservan su código.
- Pruebas que cambian: `schemas.test.ts` (`editDefaults` suma `photo` y `consent_file` en `null`).
- E2E: `tests/e2e/members.spec.ts` (preview: 15 casos verdes; 5 nuevos: foto y documento en claro 1440 y oscuro 390 con axe y sin desborde, subida cruda en orden, fallo de foto, 5.242.881 vs 5.242.880) y `tests/e2e/stack/members-photo.spec.ts` (escrito, NO corrido; V7: 5.242.880 pasa por Nginx y 5.242.881 muestra el mensaje).
- DESIGN-GAP: campo de foto (`MemberFormFields.tsx`, BRECHAS 14.2, cerrada) y fecha/versión/documento de la autorización (14.3, cerrada). Nuevas: 14.11 (cerrada) y 14.12 (el coach no puede leer la versión).
- Pendiente: revisión `security-reviewer` y sello `slice-gate.sh web/members` (orquestador); decisión de contrato de 14.12.

- Revisión de seguridad 0C/0H/2M/5L: M1, M2, L1 a L4 corregidas, L5 aceptada.
  - M1: tras un PATCH correcto, `MemberEditView` resetea el formulario (sin `dirty`, sin modos «Cambiar»/«Quitar», archivos conservados); un reintento por una subida fallida solo repite la subida (prueba en `MemberFormPage.photo.test.tsx`).
  - M2: `usePrivacyVersion(enabled)` solo pide `GET /settings/privacy` con la casilla marcada y sin autorización registrada; un coach no recibe un 403 por visita (pruebas en `ConsentSection.test.tsx` y `privacyVersion.test.tsx`).
  - L1: `UPLOAD_TIMEOUT_MS` a 35 000 (5 s sobre los 30 s del api, S6-D84) para que llegue el 408 `upload_timeout` antes del aborto del cliente.
  - L2: `ATTACHMENT_KINDS` y `attachmentRefSchema` en `shared/data/attachments.ts`, usados por `features/attachments/schemas.ts` y `features/members/schemas.ts`.
  - L3: quitada la prueba tautológica del mensaje de `data_consent_at` en `memberErrors.test.ts` (lo cubre `MemberFormPage.photo.test.tsx`).
  - L4: `MemberFormPage.photo.test.tsx` usa `vi.stubGlobal("URL", ...)` con una subclase de `URL` (el literal plano rompe `new URL` del mock del api y del router).
  - L5 (aceptada): la rama del 413 de Nginx sin envelope es defensiva: `client_max_body_size 6m` y el cliente bloquea a 5 MiB antes de enviar.
- Proceso (honesto): el Rojo previo solo se hizo en `schemas.test.ts` y `memberErrors.test.ts`; en lo demás prueba y código se escribieron seguidos.

## F5 · Inicio y Config (US-151, US-153 en textos)

- Base: `0355f7b` (checkpoint de F4, rama `feat/sprint-06-front`). `gen:api` sin diff.
- Rojo (visto en rojo antes del Verde, 11 fallos en las tres pruebas): `features/dashboard/components/NotificationKpis.test.tsx` (tarjeta «Sin autorización» con enlace a `/socios?consent=missing`, «Todos con autorización» en 0, null sin enlace), `features/members/pages/MembersListPage.test.tsx` (bloque nuevo de 9 casos: lectura de la URL, consulta con `consent=missing`, chip, quitar el chip, limpiar, valor ajeno ignorado, celular, exportación, axe claro y oscuro), `features/system/components/PrivacySettingsForm.test.tsx` (ayuda de la fecha; axe en claro y oscuro). `FutureKpis.test.tsx` solo cambia el nombre negado.
- Verde: `NotificationKpis.tsx`, `MembersListPage.tsx`, `members/api.ts` (`MembersParams.consent`, `ConsentFilter`), `components/ExportButton.tsx` (`consent` en los filtros de la exportación), `PrivacySettingsForm.tsx` (texto de ayuda).
- Decisiones:
  - El chip «Sin autorización» es un `Chips` de modo único (grupo «Autorización») que solo existe con el filtro activo; quitarlo llama `setFilter("consent", undefined)` (vuelve a la primera página, conserva `limit`). `consent` entra en `FILTERS`, en la consulta (después de `plan_id`), en la exportación y en `isFiltered` (el vacío ofrece «Limpiar filtros»). Cualquier valor distinto de `missing` se ignora.
  - La tarjeta es enlace solo con un número (con 0 también: la lista filtrada queda vacía y lo confirma); con null o error sigue siendo un grupo. `attention` con conteo > 0.
  - `useMembersTotal` (chip «Todos») no lleva el filtro.
- Pruebas que cambian: `NotificationKpis.test.tsx` (nombres «Sin autorización»), `FutureKpis.test.tsx` (nombre negado).
- E2E: `tests/e2e/home.spec.ts` (enlace) y `members.spec.ts` (chip, axe, quitar) en preview: 28 verdes; `stack/home.spec.ts` suma el conteo contra `/members?consent=missing` (escrito, NO corrido; V7).
- DESIGN-GAP: chip «Sin autorización» (BRECHAS 14.13) y texto de ayuda de la fecha (14.14), ambas aceptadas; 14.5 y 13.24 cerradas.
- Revisión de seguridad 0C/0H/1M/5L: M1 y L1 a L4 corregidas, L5 aceptada.
  - M1: `ConsentFilter` sale del contrato (`operations["list_members_api_v1_members_get"]`), no de un literal.
  - L1: `ExportButton` tipa `consent?: ConsentFilter` (importado de `../api`), no `string`.
  - L2: `exportFilters` se deriva de `params` sin `limit` ni `sort`: una sola construcción de filtros.
  - L3: `CONSENT_MISSING_PATH` usa `MEMBERS_PATH` de `shared/lib/routes.ts`.
  - L4: `// DESIGN-GAP:` junto a la ayuda nueva de «Autorización obligatoria desde» (BRECHAS 14.14).
  - L5 (aceptada): el chip «Todos» muestra el total sin `consent` (constancia en BRECHAS 14.13).
- Pendiente: sello `slice-gate.sh web/members` (orquestador).
