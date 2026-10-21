// US-063 T2: páginas ↔ limit/offset (D2: offset = (página - 1) * limit) y textos.
// DEFAULT_LIMIT y clampLimit vienen de src/core/api/query.ts para no duplicar la regla.
import { DEFAULT_LIMIT, clampLimit } from "../../core/api/query";
import { formatCount } from "../../core/i18n/format";

export { DEFAULT_LIMIT, clampLimit };

/** Tamaños de página que ofrece Pagination. */
export const PAGE_SIZES = [25, 50, 100] as const;

export function pageToOffset(page: number, limit: number): number {
  return (Math.max(1, Math.trunc(page)) - 1) * limit;
}

export function offsetToPage(offset: number, limit: number): number {
  return Math.floor(Math.max(0, offset) / limit) + 1;
}

/** Al menos una página, aunque esté vacía. */
export function totalPages(total: number, limit: number): number {
  return Math.max(1, Math.ceil(total / limit));
}

/** "Mostrando 101–150 de 312"; sin resultados, "Sin resultados". */
export function rangeLabel(offset: number, limit: number, total: number): string {
  if (total <= 0) return "Sin resultados";
  const first = Math.min(offset + 1, total);
  const last = Math.min(offset + limit, total);
  return `Mostrando ${formatCount(first)}–${formatCount(last)} de ${formatCount(total)}`;
}
