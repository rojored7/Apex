// S4A-F3 · US-108 a US-110 (front): lectura del tablero de Inicio.
// - useDashboard(): GET /dashboard con la clave ["dashboard"] y `staleTime` de 60 s (S4A-D33). Las
//   tres piezas de la pantalla (KPI, futuros y últimos movimientos) llaman al mismo hook: TanStack
//   Query hace una sola petición y "Reintentar" en cualquiera las vuelve a pedir todas.
// - La respuesta se valida con Zod (`dashboardSchema`); una forma inesperada es `invalid_response`.
// - Solo lectura: Inicio no tiene mutaciones.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { dashboardSchema, type DashboardView } from "./schemas";

export const DASHBOARD_QUERY_KEY = ["dashboard"] as const;
/** S4A-D33: el tablero se considera fresco un minuto (el api cachea el resumen 30 s). */
export const DASHBOARD_STALE_MS = 60_000;

export function useDashboard(): UseQueryResult<DashboardView> {
  return useQuery({
    queryKey: DASHBOARD_QUERY_KEY,
    queryFn: async ({ signal }) => parseResponse(dashboardSchema, await api.get<unknown>("/dashboard", { signal })),
    staleTime: DASHBOARD_STALE_MS,
  });
}
