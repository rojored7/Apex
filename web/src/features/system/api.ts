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
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { invalidResponseError, parseResponse } from "../../core/api/response";
import { HTTP_CONFLICT, HTTP_NOT_FOUND } from "../../core/api/status";
import { LINK_PURPOSES, userOutSchema, usersPageSchema, type CreateUserForm, type LinkPurpose, type UserRowView, type UserView } from "./schemas";

export type SettingsKey = "gym" | "privacy" | "memberships";

export const CONFLICT_MESSAGE = "Otra persona cambió esta sección. Recarga para ver los cambios.";
const NOT_LOADED_MESSAGE = "La sección todavía no se ha cargado. Espera un momento e intenta de nuevo.";

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
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.versionConflict;
}

function parseSection<K extends SettingsKey>(key: K, raw: unknown): SettingsSection<K> {
  // parseResponse no sirve aquí: el esquema depende de K y TypeScript no reduce la unión.
  const parsed = SECTION_SCHEMAS[key].safeParse(raw);
  if (!parsed.success) throw invalidResponseError();
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
    if (!current) return Promise.reject(new ApiError({ status: 0, code: CLIENT_ERROR_CODES.notLoaded, message: NOT_LOADED_MESSAGE }));
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

// ---------------------------------------------------------------------------------------
// S2-F4a · US-046, US-047: lista y alta de usuarios.
// - useUsers(params): GET /users con la clave ["users", params]; la página se valida con Zod.
//   Mientras llega la página siguiente se ve la anterior (placeholderData).
// - useCreateUser(): POST /users → 201 con el enlace de activación. L-7: gcTime 0; quien la
//   usa llama reset() al cerrar, así el enlace no queda en la caché. Invalida ["users"].
export interface UsersParams {
  limit: number;
  offset: number;
  q?: string;
  role?: string;
  status?: string;
}

export interface CreatedUser {
  id: string;
  email: string;
  activationUrl: string;
  expiresAt: string;
}

export const USERS_QUERY_KEY = ["users"] as const;

export function usersQueryKey(params: UsersParams): readonly ["users", UsersParams] {
  return ["users", params];
}

const createdUserSchema = z.object({
  user: z.object({ id: z.string().min(1), email: z.string().min(1) }),
  // Solo http(s): el enlace se muestra y se copia, nunca se interpreta.
  activation_url: z.string().regex(/^https?:\/\/\S+$/),
  expires_at: z.string().datetime({ offset: true }),
});

export function useUsers(params: UsersParams): UseQueryResult<Page<UserRowView>> {
  return useQuery({
    queryKey: usersQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(usersPageSchema, await api.get<unknown>("/users", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    // L2 (revisión del Sprint 2), como useMembers: una búsqueda por correo no se queda en la
    // caché al dejar de usarse ni se repite al volver a la ventana.
    ...(params.q ? { gcTime: 0, refetchOnWindowFocus: false } : {}),
  });
}

export function useCreateUser(): UseMutationResult<CreatedUser, Error, CreateUserForm> {
  const queryClient = useQueryClient();
  return useMutation<CreatedUser, Error, CreateUserForm>({
    mutationFn: async ({ email, role }) => {
      const { user, activation_url, expires_at } = parseResponse(createdUserSchema, await api.post<unknown>("/users", { body: { email, role } }));
      return { id: user.id, email: user.email, activationUrl: activation_url, expiresAt: expires_at };
    },
    gcTime: 0,
    // M3 (revisión del Sprint 2): sin esperar la relectura; el enlace se muestra enseguida.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
  });
}

// ---------------------------------------------------------------------------------------
// S2-F4b · US-049 a US-052: detalle, edición, baja, bloqueo, sesiones y reenvío del enlace.
// - useUser(id): GET /users/{id} (incluye cuentas dadas de baja) con la clave
//   ["users", "detail", id], dentro de ["users"]: toda mutación de cuentas la invalida.
// - Las mutaciones validan la respuesta con Zod (una forma inesperada es un error, no un
//   éxito) e invalidan ["users"] al salir bien.
// - useResendLink(): L-7, gcTime 0; quien la usa llama reset() al cerrar, así el enlace no
//   queda en la caché. Solo enlaces http(s).
export interface UpdateUserChanges {
  email?: string;
  role?: UserView["role"];
}

export interface IssuedLink {
  url: string;
  purpose: LinkPurpose;
  expiresAt: string;
}

export interface UserTarget {
  id: string;
}

export function userQueryKey(id: string): readonly ["users", "detail", string] {
  return ["users", "detail", id];
}

const userPath = (id: string, action?: string): string => `/users/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

const revokedSchema = z.object({ revoked: z.number().int().nonnegative() });

const issuedLinkSchema = z.object({
  url: z.string().regex(/^https?:\/\/\S+$/),
  purpose: z.enum(LINK_PURPOSES),
  expires_at: z.string().datetime({ offset: true }),
});

/** Mutación de una cuenta que, al salir bien, invalida toda la familia ["users"]. */
function useUserMutation<TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options: { gcTime?: number } = {},
): UseMutationResult<TData, Error, TVariables> {
  const queryClient = useQueryClient();
  return useMutation<TData, Error, TVariables>({
    mutationFn,
    ...options,
    // Sin esperar la relectura: cerrar las propias sesiones termina la sesión enseguida
    // (S2-D37) y la lista se relee en segundo plano.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
    // 404 y 409 dicen que la lista quedó vieja (otra persona la cambió): se relee.
    onError: (error) => {
      if (isApiError(error) && (error.status === HTTP_NOT_FOUND || error.status === HTTP_CONFLICT)) void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
  });
}

export function useUser(id: string | null): UseQueryResult<UserView> {
  return useQuery({
    queryKey: userQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(userOutSchema, await api.get<unknown>(userPath(id ?? ""), { signal })),
    enabled: Boolean(id),
    // Volver a la ventana no debe pisar lo que se está editando; y cada apertura lee la cuenta
    // del servidor (sin copia vieja en caché que luego cambie bajo el formulario).
    refetchOnWindowFocus: false,
    gcTime: 0,
  });
}

export function useUpdateUser(): UseMutationResult<UserView, Error, UserTarget & { changes: UpdateUserChanges }> {
  return useUserMutation(async ({ id, changes }: UserTarget & { changes: UpdateUserChanges }) =>
    parseResponse(userOutSchema, await api.patch<unknown>(userPath(id), { body: changes })),
  );
}

export function useDeleteUser(): UseMutationResult<undefined, Error, UserTarget> {
  return useUserMutation(async ({ id }: UserTarget) => {
    await api.delete<unknown>(userPath(id));
    return undefined;
  });
}

export function useLockUser(): UseMutationResult<UserView, Error, UserTarget> {
  return useUserMutation(async ({ id }: UserTarget) => parseResponse(userOutSchema, await api.post<unknown>(userPath(id, "lock"))));
}

export function useUnlockUser(): UseMutationResult<UserView, Error, UserTarget> {
  return useUserMutation(async ({ id }: UserTarget) => parseResponse(userOutSchema, await api.post<unknown>(userPath(id, "unlock"))));
}

/** Devuelve cuántas sesiones cerró el api ({revoked}). */
export function useRevokeSessions(): UseMutationResult<number, Error, UserTarget> {
  return useUserMutation(async ({ id }: UserTarget) => parseResponse(revokedSchema, await api.post<unknown>(userPath(id, "revoke-sessions"))).revoked);
}

export function useResendLink(): UseMutationResult<IssuedLink, Error, UserTarget> {
  return useUserMutation(
    async ({ id }: UserTarget) => {
      const { url, purpose, expires_at } = parseResponse(issuedLinkSchema, await api.post<unknown>(userPath(id, "resend-link")));
      return { url, purpose, expiresAt: expires_at };
    },
    { gcTime: 0 },
  );
}
