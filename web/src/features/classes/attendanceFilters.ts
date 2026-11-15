// S7-F5 · US-162 (front): los filtros de /clases/asistencia, leídos de la URL y listos para el api.
// - En la URL quedan `from` y `to` (días civiles de Bogotá, "AAAA-MM-DD"), `flagged` ("true" o "false"), `limit` y `offset`. La
//   búsqueda vive en memoria (S2-D41) y viaja como `q`. Sin fechas el rango son las últimas 4 semanas hasta hoy.
// - Hacia el api la lista va en UTC `[from, to)`: «Desde» es ese día a las 00:00 de Bogotá y `to` es el día siguiente al «Hasta»
//   a las 00:00; el resumen va en días civiles. Un rango invertido o de más de 26 semanas no viaja (el api daría 422): la
//   pantalla lo explica (`rangeError`).
// - Nada desconocido viaja: una fecha que no es real se ignora y un `flagged` que no es "true" ni "false" también.
import { useMemo } from "react";
import { addDaysCivil, bogotaInputToUtc, civilDaysBetween, todayBogota } from "../../core/i18n/format";
import { useListParams, type ListParamsApi } from "../../shared/hooks/useListParams";
import type { DateRange } from "../../shared/ui/FilterBar";
import type { AttendanceParams, SummaryRange } from "./attendanceApi";

export const ATTENDANCE_FILTERS = ["from", "to", "flagged"] as const;
export type AttendanceFilter = (typeof ATTENDANCE_FILTERS)[number];

/** Las últimas 4 semanas, contando hoy. */
export const DEFAULT_RANGE_DAYS = 28;
/** El tope del api: 26 semanas. */
export const MAX_RANGE_DAYS = 26 * 7;

export type FlaggedFilter = "" | "true" | "false";
export type RangeError = "inverted" | "too_long" | null;

const civilOrEmpty = (value: string | undefined): string => (value !== undefined && addDaysCivil(value, 0) === value ? value : "");
const flaggedOf = (value: string | undefined): FlaggedFilter => (value === "true" || value === "false" ? value : "");

/** El inicio (UTC) de un día civil de Bogotá. */
export function bogotaDayStartUtc(day: string): string | null {
  return bogotaInputToUtc(`${day}T00:00`);
}

/** El fin exclusivo (UTC) de un día civil de Bogotá: el inicio del día siguiente. */
export function bogotaDayEndUtc(day: string): string | null {
  const next = addDaysCivil(day, 1);
  return next === null ? null : bogotaInputToUtc(`${next}T00:00`);
}

export function rangeErrorOf(from: string, to: string): RangeError {
  if (to < from) return "inverted";
  const days = civilDaysBetween(from, to);
  return days !== null && days + 1 > MAX_RANGE_DAYS ? "too_long" : null;
}

export interface AttendanceFiltersApi {
  list: ListParamsApi<AttendanceFilter>;
  /** El rango que se ve en los campos (el de la URL o el de omisión). */
  range: DateRange;
  rangeError: RangeError;
  flagged: FlaggedFilter;
  /** Hay búsqueda o algún filtro distinto del de omisión. */
  isFiltered: boolean;
  /** Parámetros de la lista; null si el rango no es válido (no se pide nada). */
  listParams: AttendanceParams | null;
  /** Rango del resumen en días civiles; null si el rango no es válido. */
  summaryRange: SummaryRange | null;
  setRange: (range: DateRange) => void;
  setFlagged: (value: string) => void;
}

export function useAttendanceFilters(): AttendanceFiltersApi {
  const list = useListParams<AttendanceFilter>({ filters: ATTENDANCE_FILTERS, localQuery: true });
  const { filters, q } = list;
  const { limit, offset } = list.params;
  const today = todayBogota();
  const fromUrl = civilOrEmpty(filters.from[0]);
  const toUrl = civilOrEmpty(filters.to[0]);
  const from = fromUrl || (addDaysCivil(today, 1 - DEFAULT_RANGE_DAYS) ?? today);
  const to = toUrl || today;
  const rangeError = rangeErrorOf(from, to);
  const flagged = flaggedOf(filters.flagged[0]);

  const listParams = useMemo<AttendanceParams | null>(() => {
    const fromUtc = bogotaDayStartUtc(from);
    const toUtc = bogotaDayEndUtc(to);
    if (rangeError !== null || fromUtc === null || toUtc === null) return null;
    return { limit, offset, from: fromUtc, to: toUtc, ...(q ? { q } : {}), ...(flagged ? { flagged: flagged === "true" } : {}) };
  }, [limit, offset, from, to, rangeError, q, flagged]);
  const summaryRange = useMemo<SummaryRange | null>(() => (rangeError === null ? { from, to } : null), [rangeError, from, to]);

  const { setFilter } = list;
  return {
    list,
    range: { from, to },
    rangeError,
    flagged,
    isFiltered: Boolean(q) || fromUrl !== "" || toUrl !== "" || flagged !== "",
    listParams,
    summaryRange,
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas se pisarían).
    setRange: (next) => {
      if (next.from !== from) setFilter("from", next.from || undefined);
      else if (next.to !== to) setFilter("to", next.to || undefined);
    },
    setFlagged: (value) => {
      setFilter("flagged", value || undefined);
    },
  };
}
