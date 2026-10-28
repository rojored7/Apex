// S3-F6 · US-098 (front): los filtros de /pagos, leídos de la URL y listos para el api.
// - En la URL quedan `from` y `to` como días civiles de Bogotá ("AAAA-MM-DD", lo que se ve en el
//   campo), `method`, `registered_by`, `voided` (Estado: sin él es Todos, D37; "false" Válidos,
//   "true" Anulados), `backdated`, `limit` y `offset`. La búsqueda vive en memoria (S2-D41, con
//   useListParams) y viaja como `q`. Recargar conserva la vista y "atrás" restaura la anterior.
// - Hacia el api el rango va en UTC (D26, `[from, to)`): "Desde" es ese día a las 00:00 de Bogotá y
//   `to` es exclusivo, el día siguiente al "Hasta" a las 00:00 de Bogotá; así "Hasta 20 oct" incluye
//   los pagos de todo el 20 de octubre.
// - Nada desconocido viaja: un medio que no existe, un `registered_by` que no es un UUID, un estado o
//   un retroactivo que no es "true" ni "false" y una fecha que no es real se descartan. Un rango
//   invertido tampoco viaja (el api daría 422); la pantalla lo explica (`rangeInverted`).
import { useMemo } from "react";
import { addDaysCivil, bogotaInputToUtc } from "../../../core/i18n/format";
import { PAYMENT_METHOD_CODES, type PaymentMethodCode } from "../../../shared/data/schemas/payment";
import { useListParams, type ListParamsApi } from "../../../shared/hooks/useListParams";
import { isUuid } from "../../../shared/lib/ids";
import type { DateRange } from "../../../shared/ui/FilterBar";
import type { PaymentsParams } from "../api";

export const PAYMENT_FILTERS = ["from", "to", "method", "registered_by", "voided", "backdated"] as const;
export type PaymentFilter = (typeof PAYMENT_FILTERS)[number];

/** Un filtro de sí o no tal como viaja en la URL; "" es "sin filtro". */
export type BooleanFilter = "" | "true" | "false";


const isMethod = (value: string): value is PaymentMethodCode => (PAYMENT_METHOD_CODES as readonly string[]).includes(value);

/** Una fecha civil real "AAAA-MM-DD", o "" si no lo es. */
const civilOrEmpty = (value: string | undefined): string => (value !== undefined && addDaysCivil(value, 0) === value ? value : "");

const booleanOf = (value: string | undefined): BooleanFilter => (value === "true" || value === "false" ? value : "");

/** El inicio (UTC) de un día civil de Bogotá; null si el día no es real. */
export function bogotaDayStartUtc(day: string): string | null {
  return civilOrEmpty(day) === "" ? null : bogotaInputToUtc(`${day}T00:00`);
}

/** El fin exclusivo (UTC) de un día civil de Bogotá: el inicio del día siguiente. */
export function bogotaDayEndUtc(day: string): string | null {
  const next = civilOrEmpty(day) === "" ? null : addDaysCivil(day, 1);
  return next === null ? null : bogotaInputToUtc(`${next}T00:00`);
}

export interface PaymentFiltersApi {
  list: ListParamsApi<PaymentFilter>;
  /** Los días de la URL válidos ("" si falta o no es real). */
  range: DateRange;
  rangeInverted: boolean;
  /** El medio de la URL si existe, o "". */
  method: PaymentMethodCode | "";
  /** El `registered_by` de la URL si es un UUID, o "". */
  registeredBy: string;
  voided: BooleanFilter;
  backdated: BooleanFilter;
  /** Hay búsqueda o algún filtro aplicado. */
  isFiltered: boolean;
  params: PaymentsParams;
  setRange: (range: DateRange) => void;
  setFilter: (name: Exclude<PaymentFilter, "from" | "to">, value: string) => void;
}

export function usePaymentFilters(): PaymentFiltersApi {
  const list = useListParams<PaymentFilter>({ filters: PAYMENT_FILTERS, localQuery: true });
  const { filters, q } = list;
  const { limit, offset } = list.params;
  const from = civilOrEmpty(filters.from[0]);
  const to = civilOrEmpty(filters.to[0]);
  const rangeInverted = from !== "" && to !== "" && to < from;
  const methodRaw = filters.method[0] ?? "";
  const method = isMethod(methodRaw) ? methodRaw : "";
  const registeredRaw = filters.registered_by[0] ?? "";
  const registeredBy = isUuid(registeredRaw) ? registeredRaw : "";
  const voided = booleanOf(filters.voided[0]);
  const backdated = booleanOf(filters.backdated[0]);

  const params = useMemo<PaymentsParams>(() => {
    const fromUtc = from && !rangeInverted ? bogotaDayStartUtc(from) : null;
    const toUtc = to && !rangeInverted ? bogotaDayEndUtc(to) : null;
    return {
      limit,
      offset,
      ...(q ? { q } : {}),
      ...(fromUtc ? { from: fromUtc } : {}),
      ...(toUtc ? { to: toUtc } : {}),
      ...(method ? { method } : {}),
      ...(registeredBy ? { registered_by: registeredBy } : {}),
      ...(voided ? { voided: voided === "true" } : {}),
      ...(backdated ? { backdated: backdated === "true" } : {}),
    };
  }, [limit, offset, q, from, to, rangeInverted, method, registeredBy, voided, backdated]);

  const { setFilter } = list;
  return {
    list,
    range: { from, to },
    rangeInverted,
    method,
    registeredBy,
    voided,
    backdated,
    isFiltered: Boolean(q) || from !== "" || to !== "" || method !== "" || registeredBy !== "" || voided !== "" || backdated !== "",
    params,
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas
    // partirían de la misma URL y la segunda pisaría a la primera).
    setRange: (next) => {
      if (next.from !== from) setFilter("from", next.from || undefined);
      else if (next.to !== to) setFilter("to", next.to || undefined);
    },
    setFilter: (name, value) => {
      setFilter(name, value || undefined);
    },
  };
}
