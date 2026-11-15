// S8-F3 · E5 (front): historial del WOD = GET /audit?table=wods.wods&record_id=<id> (solo admin, `audit.view`).
// El api manda quién, qué y cuándo (nunca valores): HistoryAside lo pinta con las etiquetas de la auditoría.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import type { AuditEntryView } from "../../shared/lib/audit-labels";

const auditRowSchema = z.object({
  seq: z.number().int().positive(),
  at: z.string(),
  user_id: z.string(),
  user_email: z.string().nullable(),
  user_name: z.string().nullable(),
  action: z.string(),
  table_name: z.string(),
});
export type WodHistoryRow = z.infer<typeof auditRowSchema>;

export const WOD_AUDIT_TABLE = "wods.wods";
export const HISTORY_PAGE_SIZE = 25;
export const WOD_HISTORY_QUERY_KEY = ["wod-history"] as const;

export function toEntry(row: WodHistoryRow): AuditEntryView {
  return { id: String(row.seq), at: row.at, actor_id: row.user_id, actor_name: row.user_name ?? row.user_email, entity: row.table_name, action: row.action };
}

export function useWodHistory(wodId: string, pages: number): UseQueryResult<Page<WodHistoryRow>> {
  const limit = HISTORY_PAGE_SIZE * pages;
  return useQuery({
    queryKey: [...WOD_HISTORY_QUERY_KEY, wodId, limit],
    queryFn: async ({ signal }) =>
      parseResponse(pageSchema(auditRowSchema), await api.get<unknown>("/audit", { query: listParams({ limit, offset: 0, table: WOD_AUDIT_TABLE, record_id: wodId }), signal })),
    enabled: wodId !== "",
  });
}
