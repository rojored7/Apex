// S8-F5 (limpieza de F4): la llegada de un socio a una clase (POST /attendance), una sola copia para classes (check-in) y results
// («+ Alguien que no hizo check-in»). Manda solo la sesión y el socio: las banderas y el descuento los decide el servidor (L-1, S8-D15).
import { useQueryClient, type QueryClient, type UseMutationResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";

export const checkinSchema = z.object({
  id: z.string().min(1),
  flags: z.array(z.string()),
  flagged: z.boolean(),
  membership_status_at_checkin: z.string(),
  attendance_count: z.number().int().nonnegative(),
  capacity: z.number().int(),
});
export type CheckinResult = z.infer<typeof checkinSchema>;

export interface CheckInVariables {
  sessionId: string;
  memberId: string;
}

// Todo lo que muestra una clase (S8-V7b, L-1): la clase, las listas de sesiones, las asistencias, la tablet de resultados, las
// clases del WOD y Inicio. Una llegada, quitar una asistencia, cancelar o cambiar el WOD las releen todas.
const STALE_KEYS = [["class-session"], ["class-sessions"], ["attendance"], ["session-results"], ["wod-sessions"], ["dashboard"]] as const;

export function invalidateSessionViews(queryClient: QueryClient): void {
  for (const queryKey of STALE_KEYS) void queryClient.invalidateQueries({ queryKey });
}

/** POST /attendance. Con éxito, el duplicado (409) o la sesión cambiada, las listas de la tablet se releen. */
export function useCheckIn(): UseMutationResult<CheckinResult, Error, CheckInVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<CheckinResult, Error, CheckInVariables>({
    mutationFn: async ({ sessionId, memberId }) => {
      try {
        return parseResponse(checkinSchema, await api.post<unknown>("/attendance", { body: { session_id: sessionId, member_id: memberId } }));
      } finally {
        invalidateSessionViews(queryClient);
      }
    },
  });
}
