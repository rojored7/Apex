// S6-F4 · US-149: la versión vigente de la política de privacidad (GET /settings/privacy), solo lectura.
// - Es el dato que el formulario del socio muestra junto a la autorización: la versión que el api
//   copia en data_consent_version al registrarla (S6-C3). El formulario nunca la envía.
// - GET /settings/privacy es solo del admin: para un coach el 403 (u otro fallo) no rompe la
//   pantalla; `unavailable` y quien pinta usa un texto neutro. Clave propia (la de Configuración
//   guarda otra forma de la misma sección).
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";

const privacyVersionSchema = z.object({ value: z.object({ policy_version: z.string().nullable() }) });

export type PrivacyVersionState = { status: "loading" } | { status: "unavailable" } | { status: "ready"; version: string | null };

export const PRIVACY_VERSION_KEY = ["settings", "privacy", "version"] as const;

/** `enabled`: solo se pide cuando la pantalla la muestra (un coach no recibe un 403 por visita). */
export function usePrivacyVersion(enabled: boolean): PrivacyVersionState {
  const query = useQuery({
    queryKey: PRIVACY_VERSION_KEY,
    queryFn: async ({ signal }) => privacyVersionSchema.parse(await api.get<unknown>("/settings/privacy", { signal })).value.policy_version,
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
  });
  if (query.isPending) return { status: "loading" };
  if (query.isError) return { status: "unavailable" };
  return { status: "ready", version: query.data };
}
