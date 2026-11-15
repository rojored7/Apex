// S8-F4 · US-169 y US-170 (front): datos de la tablet de resultados.
// - useSessionAttendance(id): GET /class-sessions/{id}/attendance (asistentes con su resultado vigente y el WOD de la clase).
// - useSaveResult(): PUT /results. Un resultado nuevo o una corrección (`supersedes_id` y el MISMO `session_id`, S8-B1d M-3).
// - «Alguien que no hizo check-in» usa useCheckIn de shared/data/attendance (una sola copia con classes).
// Las escrituras pasan por useSensitiveMutation. Nada de esto toca /reveal ni /members/{id} (S8-D24).
import { useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { resultSchema, sessionAttendanceSchema, type ResultView, type ScoreValues, type SessionAttendanceView } from "./schemas";

export const SESSION_RESULTS_QUERY_KEY = ["session-results"] as const;
/** Una clase cabe en una página (el api topa en 200). */
export const ATTENDEES_LIMIT = 200;

export function sessionResultsKey(id: string): readonly ["session-results", string] {
  return ["session-results", id];
}

export function useSessionAttendance(id: string): UseQueryResult<SessionAttendanceView> {
  return useQuery({
    queryKey: sessionResultsKey(id),
    queryFn: async ({ signal }) =>
      parseResponse(sessionAttendanceSchema, await api.get<unknown>(`/class-sessions/${encodeURIComponent(id)}/attendance`, { query: listParams({ limit: ATTENDEES_LIMIT, offset: 0 }), signal })),
    enabled: id !== "",
    refetchOnWindowFocus: false,
  });
}

export interface SaveResultVariables {
  wodId: string;
  memberId: string;
  sessionId: string;
  score: ScoreValues;
  /** El resultado vigente que se corrige; sin él es un resultado nuevo. */
  supersedesId?: string | undefined;
}

/** PUT /results; al terminar (bien o mal) la lista de la clase se relee. */
export function useSaveResult(): UseMutationResult<ResultView, Error, SaveResultVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<ResultView, Error, SaveResultVariables>({
    mutationFn: async ({ wodId, memberId, sessionId, score, supersedesId }) => {
      try {
        return parseResponse(
          resultSchema,
          await api.put<unknown>("/results", {
            body: {
              wod_id: wodId,
              member_id: memberId,
              session_id: sessionId,
              level: score.level,
              capped: score.capped,
              scaled_movement_ids: score.scaled_movement_ids,
              ...(score.seconds === null ? {} : { seconds: score.seconds }),
              ...(score.rounds === null ? {} : { rounds: score.rounds }),
              ...(score.reps === null ? {} : { reps: score.reps }),
              ...(score.load_g === null ? {} : { load_g: score.load_g }),
              ...(supersedesId === undefined ? {} : { supersedes_id: supersedesId }),
            },
          }),
        );
      } finally {
        void queryClient.invalidateQueries({ queryKey: SESSION_RESULTS_QUERY_KEY });
      }
    },
    onSuccess: () => {
      for (const key of [["wod-leaderboard"], ["wod-results"], ["wods"], ["wod"]]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
