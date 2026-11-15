// S8-F6 · US-177: el tablero de la TV con TanStack Query. GET /tv/today por fetchTvToday (core/api/tvClient: solo X-Device-Token).
// - La clave es ["tv", "today"] y NO lleva el token (la caché no lo ve). La respuesta se valida con Zod antes de pintarla.
// - Refresca cada `refresh_seconds` del api (15 a 300; 30 por defecto) aunque la pestaña esté oculta (una TV no tiene foco).
// - Con 401 («Token inválido») reintenta cada 5 minutos: un enlace nuevo sin reiniciar la TV no hace falta si se abre el enlace, y un
//   token revocado que vuelve a crearse se recupera solo. Con red caída o 5xx conserva lo último (react-query no borra `data`).
// - Sin reintentos automáticos de TanStack: el ritmo lo fija el intervalo, para no sumar peticiones al límite del api (S8-D33).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { fetchTvToday, TvRequestError } from "../../core/api/tvClient";
import { parseResponse } from "../../core/api/response";
import { tvBoardSchema, type TvBoardView } from "./schemas";

export const TV_QUERY_KEY = ["tv", "today"] as const;
export const TV_DEFAULT_REFRESH_S = 30;
export const TV_INVALID_RETRY_MS = 5 * 60_000;
const MS_PER_S = 1000;

export function useTvBoard(token: string | null): UseQueryResult<TvBoardView> {
  return useQuery({
    queryKey: TV_QUERY_KEY,
    enabled: token !== null,
    queryFn: async ({ signal }) => {
      try {
        return parseResponse(tvBoardSchema, await fetchTvToday(token ?? "", signal));
      } catch (error) {
        // Una respuesta con otra forma no se pinta: se trata como «sin conexión» y se conserva lo último.
        throw error instanceof TvRequestError ? error : new TvRequestError("unavailable");
      }
    },
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: true,
    refetchInterval: (query) => {
      if (query.state.error instanceof TvRequestError && query.state.error.failure === "invalid_token") return TV_INVALID_RETRY_MS;
      return (query.state.data?.refresh_seconds ?? TV_DEFAULT_REFRESH_S) * MS_PER_S;
    },
  });
}
