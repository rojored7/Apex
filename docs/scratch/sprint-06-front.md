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
