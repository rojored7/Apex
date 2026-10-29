// S4A-F2 · US-106 (front), S4A-D32: una entrada de GET /members/{id}/audit (MemberHistoryItem) como
// AuditEntryView de HistoryAside (shared/lib/audit-labels.ts): `id` es el `seq`, la entidad es la tabla
// completa (`members.members`, ENTITY_LABELS), `fields` se copia (sin valores; no hay `before` ni
// `after`), `purpose` marca un reveal automático y `phrase` es la frase de historyPhrase.
import type { AuditEntryView } from "../../../shared/lib/audit-labels";
import type { MemberHistoryItemView } from "../schemas";
import { historyPhrase } from "./historyPhrase";

export function toAuditEntryView(item: MemberHistoryItemView): AuditEntryView {
  return {
    id: String(item.seq),
    at: item.at,
    actor_id: item.user_id,
    actor_name: item.user_name,
    entity: item.table_name,
    action: item.action,
    fields: [...item.fields],
    purpose: item.purpose,
    phrase: historyPhrase(item),
  };
}

/** Las entradas de varias páginas sin repetir un `seq` (una entrada nueva corre el offset). */
export function uniqueHistoryEntries(items: readonly MemberHistoryItemView[]): AuditEntryView[] {
  const bySeq = new Map<number, MemberHistoryItemView>();
  for (const item of items) if (!bySeq.has(item.seq)) bySeq.set(item.seq, item);
  return Array.from(bySeq.values(), toAuditEntryView);
}
