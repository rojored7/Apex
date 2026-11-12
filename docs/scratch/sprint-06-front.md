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
