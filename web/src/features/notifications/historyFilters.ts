// S5-F2 · US-130 (front): los filtros de /avisos/historial, de la URL al api.
// - En la URL quedan `status`, `channel`, `rule_id`, `from`, `to`, `limit` y `offset`; la búsqueda por
//   socio vive en memoria y viaja como `q` (S2-D41): un `q` de la URL se ignora.
// - Solo pasa lo que el api acepta: estado y canal de las listas del contrato, regla con forma de UUID y
//   fechas reales (AAAA-MM-DD). Un rango invertido no viaja; cualquier otro valor se descarta.
import { isUuid } from "../../shared/lib/ids";
import { NOTIFICATION_CHANNELS, NOTIFICATION_STATUSES } from "./schemas";
import type { HistoryFilter } from "./adminSchemas";

export interface HistoryUrlFilters {
  status: string;
  channel: string;
  rule_id: string;
  from: string;
  to: string;
}

export interface HistoryParams {
  limit: number;
  offset: number;
  q?: string;
  status?: string;
  channel?: string;
  rule_id?: string;
  from?: string;
  to?: string;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function isCalendarDate(value: string): boolean {
  const match = ISO_DATE.exec(value);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

const oneOf = (values: readonly string[], candidate: string | undefined): string => (candidate !== undefined && values.includes(candidate) ? candidate : "");

/** Lo que dice la URL, ya limpio: lo inválido queda como "". */
export function readHistoryFilters(raw: Readonly<Record<HistoryFilter, readonly string[]>>): HistoryUrlFilters {
  const first = (name: HistoryFilter): string | undefined => raw[name][0];
  const from = first("from") ?? "";
  const to = first("to") ?? "";
  const rule = first("rule_id") ?? "";
  const validFrom = isCalendarDate(from) ? from : "";
  const validTo = isCalendarDate(to) ? to : "";
  const inverted = validFrom !== "" && validTo !== "" && validFrom > validTo;
  return {
    status: oneOf(NOTIFICATION_STATUSES, first("status")),
    channel: oneOf(NOTIFICATION_CHANNELS, first("channel")),
    rule_id: isUuid(rule) ? rule : "",
    from: inverted ? "" : validFrom,
    to: inverted ? "" : validTo,
  };
}

export function toHistoryParams(page: { limit: number; offset: number }, q: string, filters: HistoryUrlFilters): HistoryParams {
  return {
    limit: page.limit,
    offset: page.offset,
    ...(q ? { q } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.channel ? { channel: filters.channel } : {}),
    ...(filters.rule_id ? { rule_id: filters.rule_id } : {}),
    ...(filters.from ? { from: filters.from } : {}),
    ...(filters.to ? { to: filters.to } : {}),
  };
}

export const hasHistoryFilters = (filters: HistoryUrlFilters, q: string): boolean => q !== "" || Object.values(filters).some((value) => value !== "");
