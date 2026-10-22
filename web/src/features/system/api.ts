// S2-F5 (US-055, US-057, US-058; blueprint F5): lectura y guardado de las secciones de
// configuración que habilita el Sprint 2 (gym, privacy y memberships, S2-D15).
// - GET /settings/{key} con la clave de caché ["settings", key]; la respuesta se valida con
//   Zod antes de usarla (una forma inesperada es un error, no datos).
// - PATCH /settings/{key} reemplaza la sección completa con { value, version }, donde version
//   es la que se leyó (0 si nunca se guardó). Al salir bien se actualiza solo la caché de esa
//   clave: las otras pestañas no se recargan (US-055, criterio 4).
// - 409 version_conflict: isConflict y sin reintento (las mutaciones no se reintentan);
//   reload() limpia el conflicto y vuelve a leer, sin sobrescribir lo de la otra persona.
// - Nada se guarda en localStorage: la única copia local es la caché de TanStack Query.
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { ApiError, isApiError } from "../../core/api/errors";

export type SettingsKey = "gym" | "privacy" | "memberships";

export const CONFLICT_MESSAGE = "Otra persona cambió esta sección. Recarga para ver los cambios.";
const INVALID_RESPONSE_MESSAGE = "La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.";
const NOT_LOADED_MESSAGE = "La sección todavía no se ha cargado. Espera un momento e intenta de nuevo.";
const CONFLICT_STATUS = 409;

// Los campos opcionales del api llegan como null; `default(null)` cubre una clave ausente.
const text = z.string().nullable().default(null);
const integer = z.number().int();

const gymValueSchema = z.object({
  name: z.string(),
  nit: text,
  address: text,
  city: text,
  phone: text,
  whatsapp: text,
  email: text,
});

const privacyValueSchema = z.object({
  policy_version: text,
  policy_text: text,
  retention_years: integer,
  consent_required_from: text,
});

const membershipsValueSchema = z.object({
  expiring_days: integer,
  max_freeze_days_per_membership: integer,
  max_freezes_per_membership: integer,
  max_retroactive_days: integer,
});

function sectionSchema<K extends SettingsKey, V extends z.ZodTypeAny>(key: K, value: V) {
  return z.object({
    key: z.literal(key),
    value,
    version: z.number().int().nonnegative(),
    updated_at: z.string().nullable(),
    updated_by: z.string().nullable(),
  });
}

const SECTION_SCHEMAS = {
  gym: sectionSchema("gym", gymValueSchema),
  privacy: sectionSchema("privacy", privacyValueSchema),
  memberships: sectionSchema("memberships", membershipsValueSchema),
} as const;

export type GymSettings = z.infer<typeof gymValueSchema>;
/** Lo que se lee de `privacy`: sin publicar, versión y texto son null. */
export type PrivacyView = z.infer<typeof privacyValueSchema>;
export type MembershipsSettings = z.infer<typeof membershipsValueSchema>;

/** Lo que se escribe en `privacy`: publicar exige versión y texto. */
export interface PrivacyInput {
  policy_version: string;
  policy_text: string;
  retention_years: number;
  consent_required_from: string | null;
}

interface SectionInputs {
  gym: GymSettings;
  privacy: PrivacyInput;
  memberships: MembershipsSettings;
}

export type SettingsSection<K extends SettingsKey> = z.infer<(typeof SECTION_SCHEMAS)[K]>;
export type SectionValue<K extends SettingsKey> = SettingsSection<K>["value"];
export type SectionInput<K extends SettingsKey> = SectionInputs[K];

export interface SettingsSectionApi<K extends SettingsKey> {
  query: UseQueryResult<SettingsSection<K>>;
  /**
   * PATCH con la versión leída (o con `version`, la que tenía el formulario al armarse);
   * rechaza con el ApiError del servidor.
   */
  save: (value: SectionInput<K>, version?: number) => Promise<SettingsSection<K>>;
  isSaving: boolean;
  isConflict: boolean;
  /** Limpia el conflicto y vuelve a leer la sección; devuelve lo leído. */
  reload: () => Promise<SettingsSection<K> | undefined>;
}

export function settingsQueryKey(key: SettingsKey): readonly ["settings", SettingsKey] {
  return ["settings", key];
}

export function isVersionConflict(error: unknown): boolean {
  return isApiError(error) && error.status === CONFLICT_STATUS && error.code === "version_conflict";
}

function parseSection<K extends SettingsKey>(key: K, raw: unknown): SettingsSection<K> {
  const parsed = SECTION_SCHEMAS[key].safeParse(raw);
  if (!parsed.success) throw new ApiError({ status: 0, code: "invalid_response", message: INVALID_RESPONSE_MESSAGE });
  return parsed.data;
}

const pathOf = (key: SettingsKey): string => `/settings/${key}`;

export function useSettingsSection<K extends SettingsKey>(key: K): SettingsSectionApi<K> {
  const queryClient = useQueryClient();
  const queryKey = settingsQueryKey(key);

  const query = useQuery({
    queryKey,
    queryFn: async ({ signal }) => parseSection(key, await api.get<unknown>(pathOf(key), { signal })),
    // Volver a la ventana no debe pisar lo que el admin está escribiendo.
    refetchOnWindowFocus: false,
  });

  const mutation = useMutation({
    mutationFn: async ({ value, version }: { value: SectionInput<K>; version: number }) =>
      parseSection(key, await api.patch<unknown>(pathOf(key), { body: { value, version } })),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKey, saved);
    },
  });

  const save = (value: SectionInput<K>, version?: number): Promise<SettingsSection<K>> => {
    const current = query.data;
    if (!current) return Promise.reject(new ApiError({ status: 0, code: "not_loaded", message: NOT_LOADED_MESSAGE }));
    return mutation.mutateAsync({ value, version: version ?? current.version });
  };

  const reload = async (): Promise<SettingsSection<K> | undefined> => {
    // refetch no lanza: si falla, result.data es la copia vieja. El conflicto sigue a la vista
    // y no se entrega nada que reemplace lo escrito.
    const result = await query.refetch();
    if (result.isError) return undefined;
    mutation.reset();
    return result.data;
  };

  return { query, save, isSaving: mutation.isPending, isConflict: isVersionConflict(mutation.error), reload };
}
