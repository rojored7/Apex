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
