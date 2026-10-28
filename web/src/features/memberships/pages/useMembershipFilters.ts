// S3-F5 · US-091 (front): los filtros de /membresias, leídos de la URL y listos para el api.
// - En la URL quedan `status` (varios estados separados por comas, como los recibe el api, D18),
//   `plan_id`, `ends_from`, `ends_to`, `limit` y `offset`; la búsqueda vive en memoria (S2-D41, con
//   useListParams). Recargar conserva la vista y "atrás" restaura la anterior.
// - Nada desconocido viaja: un estado que no existe se descarta; un `plan_id` que no es un UUID y
//   una fecha que no es real ("AAAA-MM-DD") no se envían. Un rango invertido tampoco: el api daría
//   422 en `ends_to`; la pantalla lo explica (`rangeInverted`).
// - Los estados van siempre en el orden de los chips, así la misma selección es la misma URL y la
//   misma clave de caché.
import { useMemo } from "react";
import { addDaysCivil } from "../../../core/i18n/format";
import type { MembershipStatus } from "../../../shared/data/memberships";
import { useListParams, type ListParamsApi } from "../../../shared/hooks/useListParams";
import { isUuid } from "../../../shared/lib/ids";
import type { DateRange } from "../../../shared/ui/FilterBar";
import type { MembershipsParams } from "../api";

export const MEMBERSHIP_FILTERS = ["status", "plan_id", "ends_from", "ends_to"] as const;
export type MembershipFilter = (typeof MEMBERSHIP_FILTERS)[number];

/** Los estados en el orden de los chips de Membresias.html. */
export const STATUS_CHIP_ORDER = ["active", "expiring", "expired", "frozen", "pending_payment", "cancelled"] as const satisfies readonly MembershipStatus[];


const isStatus = (value: string): value is MembershipStatus => (STATUS_CHIP_ORDER as readonly string[]).includes(value);

/** Los estados conocidos de un `status` de la URL ("frozen,active"), sin repetir y en el orden de los chips. */
export function parseStatuses(raw: readonly string[]): MembershipStatus[] {
  const wanted = new Set(raw.flatMap((value) => value.split(",")).map((value) => value.trim()).filter(isStatus));
  return STATUS_CHIP_ORDER.filter((status) => wanted.has(status));
}

/** Una fecha civil real "AAAA-MM-DD", o "" si no lo es. */
const civilOrEmpty = (value: string | undefined): string => (value !== undefined && addDaysCivil(value, 0) === value ? value : "");

export interface MembershipFiltersApi {
  list: ListParamsApi<MembershipFilter>;
  statuses: MembershipStatus[];
  /** El `plan_id` de la URL si es un UUID, o "". */
  planId: string;
  /** Las fechas de "Vence entre" válidas de la URL ("" si falta o no es real). */
  range: DateRange;
  /** Las dos fechas son reales y la segunda es anterior a la primera (no viajan). */
  rangeInverted: boolean;
  /** Hay búsqueda o algún filtro aplicado. */
  isFiltered: boolean;
  params: MembershipsParams;
  setStatuses: (statuses: readonly string[]) => void;
  setPlan: (planId: string) => void;
  setRange: (range: DateRange) => void;
}

export function useMembershipFilters(): MembershipFiltersApi {
  const list = useListParams<MembershipFilter>({ filters: MEMBERSHIP_FILTERS, localQuery: true });
  const { filters, q } = list;
  const { limit, offset } = list.params;
  const statusKey = parseStatuses(filters.status).join(",");
  const planRaw = filters.plan_id[0] ?? "";
  const planId = isUuid(planRaw) ? planRaw : "";
  const from = civilOrEmpty(filters.ends_from[0]);
  const to = civilOrEmpty(filters.ends_to[0]);
  const rangeInverted = from !== "" && to !== "" && to < from;

  const params = useMemo<MembershipsParams>(
    () => ({
      limit,
      offset,
      ...(q ? { q } : {}),
      ...(statusKey ? { status: statusKey } : {}),
      ...(planId ? { plan_id: planId } : {}),
      ...(from && !rangeInverted ? { ends_from: from } : {}),
      ...(to && !rangeInverted ? { ends_to: to } : {}),
    }),
    [limit, offset, q, statusKey, planId, from, to, rangeInverted],
  );

  const { setFilter } = list;
  return {
    list,
    statuses: parseStatuses([statusKey]),
    planId,
    range: { from, to },
    rangeInverted,
    isFiltered: Boolean(q) || statusKey !== "" || planId !== "" || from !== "" || to !== "",
    params,
    setStatuses: (next) => {
      const ordered = parseStatuses(next);
      setFilter("status", ordered.length > 0 ? ordered.join(",") : undefined);
    },
    setPlan: (next) => {
      setFilter("plan_id", next || undefined);
    },
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas
    // partirían de la misma URL y la segunda pisaría a la primera).
    setRange: (next) => {
      if (next.from !== from) setFilter("ends_from", next.from || undefined);
      else if (next.to !== to) setFilter("ends_to", next.to || undefined);
    },
  };
}
