// S9-F1: vistas del atleta que comparten `athletes` y `results` (una feature nunca importa de otra).
// Guardar o anular un resultado puede crear, mover o invalidar un RM o un récord derivado (S9-D20): `results` relee
// estas vistas con invalidateAthleteViews, y `athletes` la usa al guardar o anular una medida.
import type { QueryClient } from "@tanstack/react-query";

/** Todo lo que muestra datos del atleta: resumen, medidas, RMs, récords y benchmarks (la clave lleva el id del socio después). */
export const ATHLETE_VIEW_KEYS = [["athlete-summary"], ["athlete-metrics"], ["athlete-rms"], ["athlete-records"], ["athlete-benchmarks"]] as const;

/** Relee todo lo que muestra datos del atleta. */
export function invalidateAthleteViews(queryClient: QueryClient): void {
  for (const queryKey of ATHLETE_VIEW_KEYS) void queryClient.invalidateQueries({ queryKey });
}

/** Lo que un récord (guardar o invalidar) mueve: resumen, RMs, récords y benchmarks de ESE socio; sus medidas no cambian. */
const RECORD_VIEW_KEYS = ["athlete-summary", "athlete-rms", "athlete-records", "athlete-benchmarks"] as const;

export function invalidateRecordViews(queryClient: QueryClient, memberId: string): void {
  for (const name of RECORD_VIEW_KEYS) void queryClient.invalidateQueries({ queryKey: [name, memberId] });
}

/** Lo que una medida (guardar o anular) mueve: el resumen (conteo y última fecha) y las medidas de ESE socio; sus RMs y récords no cambian. */
const METRIC_VIEW_KEYS = ["athlete-summary", "athlete-metrics"] as const;

export function invalidateMetricViews(queryClient: QueryClient, memberId: string): void {
  for (const name of METRIC_VIEW_KEYS) void queryClient.invalidateQueries({ queryKey: [name, memberId] });
}
