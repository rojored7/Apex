// S2-F3 · US-042: POST /auth/login (LoginOut de B2).
// - skipAuthRetry: un 401 de credenciales malas nunca dispara un refresh.
// - La respuesta se valida con Zod; con ella se arma la sesión en memoria (setSession). El
//   gimnasio y el socio no vienen en LoginOut: llegan después con GET /auth/me
//   (refreshCurrentUser), sin bloquear la entrada; mientras tanto el gimnasio es "APEX".
// - loginErrorMessage traduce el error a un mensaje "qué pasó y qué hacer". Un 401 nunca dice
//   si la cuenta existe, está bloqueada o pendiente.
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import type { components } from "../../core/api/types";
import { ROLES } from "../../core/auth/permissions";
import { adoptAccessToken, getSession, refreshCurrentUser, setSession, type SessionPayload, type SessionUser } from "../../core/auth/session";
import type { ForgotForm, LoginForm } from "./schemas";

export type LoginOut = components["schemas"]["LoginOut"];

/** Nombre que muestra la TopBar hasta que GET /auth/me trae gym_name (S2-D50). */
export const DEFAULT_GYM_NAME = "APEX";

const loginOutSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  expires_in: z.number().int().positive(),
  must_change_password: z.boolean(),
  user: z.object({
    id: z.string().min(1),
    email: z.string().min(3),
    role: z.enum(ROLES),
  }),
});

export const LOGIN_MESSAGES = {
  invalidCredentials: "Correo o contraseña incorrectos. Revísalos e intenta de nuevo.",
  tooManyWait: (seconds: number) => `Demasiados intentos. Espera ${String(seconds)} s y vuelve a intentarlo.`,
  tooMany: "Demasiados intentos. Espera un momento y vuelve a intentarlo.",
  canRetry: "Ya puedes intentarlo de nuevo.",
  invalidData: "Revisa el correo y la contraseña e intenta de nuevo.",
  server: "El servidor tuvo un problema. Intenta de nuevo en un momento.",
  generic: "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo.",
} as const;

const HTTP_UNAUTHORIZED = 401;
const HTTP_TOO_MANY = 429;
const HTTP_UNPROCESSABLE = 422;
const HTTP_SERVER_ERROR = 500;

/** LoginOut validado → sesión. Lanza si la respuesta no tiene la forma del contrato. */
export function sessionFromLogin(out: unknown): SessionPayload {
  const login = loginOutSchema.parse(out);
  return {
    accessToken: login.access_token,
    user: {
      id: login.user.id,
      email: login.user.email,
      role: login.user.role,
      memberId: null,
      gymName: DEFAULT_GYM_NAME,
      mustChangePassword: login.must_change_password,
    },
  };
}

export function loginErrorMessage(error: unknown): string {
  if (!isApiError(error)) return LOGIN_MESSAGES.generic;
  // Con respuesta manda el código HTTP, aunque el cuerpo no sea el envelope (un 429 o un 502 de
  // Nginx llegan como network_error); sin respuesta (status 0), red o timeout.
  if (error.status === HTTP_UNAUTHORIZED) return LOGIN_MESSAGES.invalidCredentials;
  if (error.status === HTTP_UNPROCESSABLE) return LOGIN_MESSAGES.invalidData;
  return commonErrorMessage(error) ?? LOGIN_MESSAGES.generic;
}

async function login(values: LoginForm): Promise<SessionUser> {
  const out = await api.post<unknown>("/auth/login", { body: { email: values.email, password: values.password }, skipAuthRetry: true });
  const payload = sessionFromLogin(out);
  setSession(payload);
  void refreshCurrentUser();
  return payload.user;
}

/** Mutación del login: al terminar, la sesión ya está en memoria. */
export function useLogin(): UseMutationResult<SessionUser, Error, LoginForm> {
  return useMutation<SessionUser, Error, LoginForm>({ mutationFn: login, gcTime: 0 });
}

// ---------------------------------------------------------------------------------------
// S2-F4a · US-045, US-048: mi cuenta, cambio de contraseña, restablecimiento y recuperación.
// - useMe: GET /auth/me con la clave ["me"], validado con Zod.
// - useChangePassword: POST /auth/me/password → 200 AccessTokenOut (S2-D37). El access
//   nuevo entra a la sesión con setSession (must_change_password queda en falso) y se reparte
//   a las demás pestañas por apex-auth (adoptAccessToken): el api ya cortó los anteriores.
// - useResetPassword: POST /auth/reset (204, no inicia sesión, S2-D18).
// - useForgotPassword: POST /auth/forgot (siempre 204, H-2).
// Las tres mutaciones llevan contraseñas (y el token del enlace) en sus variables: gcTime 0,
// así no quedan en la caché de TanStack Query al terminar.
export type MeOut = components["schemas"]["MeOut"];

export const ME_QUERY_KEY = ["me"] as const;

const meSchema = z.object({
  id: z.string().min(1),
  email: z.string().min(3),
  role: z.enum(ROLES),
  member_id: z.string().nullable(),
  gym_name: z.string(),
  must_change_password: z.boolean(),
});

export type MeView = z.infer<typeof meSchema>;

const accessTokenOutSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  expires_in: z.number().int().positive(),
});

export const INVALID_RESPONSE_MESSAGE = "La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.";

export const PASSWORD_ERRORS = {
  currentWrong: "La contraseña actual no es correcta. Revísala e intenta de nuevo.",
  invalidLink: "El enlace ya no es válido. Pide uno nuevo al administrador.",
  rejected: "El servidor no aceptó esta contraseña. Elige otra.",
  generic: "No pudimos guardar la contraseña. Recarga la página e intenta de nuevo.",
} as const;

const HTTP_BAD_REQUEST = 400;

function invalidResponse(): ApiError {
  return new ApiError({ status: 0, code: "invalid_response", message: INVALID_RESPONSE_MESSAGE });
}

function parseOrThrow<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.infer<T> {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw invalidResponse();
  return parsed.data as z.infer<T>;
}

/**
 * Mensaje de los errores que no dependen de la pantalla: sin respuesta (red o timeout), 429
 * con la espera, 5xx y una respuesta con forma inesperada. `null` si el error es de otro tipo.
 */
export function commonErrorMessage(error: unknown): string | null {
  if (!isApiError(error)) return null;
  if (error.code === "invalid_response") return error.message;
  if (error.status === 0) return error.code === "timeout" ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error;
  if (error.status === HTTP_TOO_MANY) {
    return error.retryAfterS !== undefined && error.retryAfterS > 0 ? LOGIN_MESSAGES.tooManyWait(error.retryAfterS) : LOGIN_MESSAGES.tooMany;
  }
  if (error.status >= HTTP_SERVER_ERROR) return LOGIN_MESSAGES.server;
  return null;
}

export function isInvalidLink(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_BAD_REQUEST && error.code === "invalid_token";
}

export type PasswordFieldName = "currentPassword" | "newPassword";

/** Un 422 con `field` del api llevado al campo del formulario, con un mensaje propio. */
export function passwordFieldError(error: unknown): { field: PasswordFieldName; message: string } | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE) return null;
  if (error.field === "current_password") return { field: "currentPassword", message: PASSWORD_ERRORS.currentWrong };
  if (error.field === "new_password") {
    const reason = error.message.trim();
    return { field: "newPassword", message: reason.endsWith(".") ? `${reason} Elige otra.` : PASSWORD_ERRORS.rejected };
  }
  return null;
}

/** Error general de un formulario de contraseña: "qué pasó y qué hacer". */
export function passwordErrorMessage(error: unknown): string {
  if (isInvalidLink(error)) return PASSWORD_ERRORS.invalidLink;
  if (isApiError(error) && error.code === "session_changed") return error.message;
  return commonErrorMessage(error) ?? PASSWORD_ERRORS.generic;
}

export function useMe({ enabled = true }: { enabled?: boolean } = {}): UseQueryResult<MeView> {
  return useQuery<MeView>({
    queryKey: ME_QUERY_KEY,
    queryFn: async ({ signal }) => parseOrThrow(meSchema, await api.get<unknown>("/auth/me", { signal })),
    enabled,
  });
}

export interface ChangePasswordInput {
  currentPassword: string;
  newPassword: string;
}

export const SESSION_CHANGED_MESSAGE = "La contraseña se cambió, pero tu sesión se cerró mientras tanto. Inicia sesión con la contraseña nueva.";

async function changePassword({ currentPassword, newPassword }: ChangePasswordInput): Promise<undefined> {
  // La sesión que pidió el cambio: si al volver es otra (o ninguna), el token no es de ella.
  const requestedBy = getSession().user?.id;
  const raw = await api.post<unknown>("/auth/me/password", { body: { current_password: currentPassword, new_password: newPassword } });
  const out = parseOrThrow(accessTokenOutSchema, raw);
  const { user } = getSession();
  if (!user || user.id !== requestedBy) throw new ApiError({ status: 0, code: "session_changed", message: SESSION_CHANGED_MESSAGE });
  setSession({ accessToken: out.access_token, user: { ...user, mustChangePassword: false } });
  adoptAccessToken(out.access_token, out.expires_in);
  return undefined;
}

export function useChangePassword(): UseMutationResult<undefined, Error, ChangePasswordInput> {
  const queryClient = useQueryClient();
  return useMutation<undefined, Error, ChangePasswordInput>({
    mutationFn: changePassword,
    gcTime: 0,
    // Sin esperar: la relectura de me no debe alargar el "Guardando…".
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    },
  });
}

export interface ResetInput {
  token: string;
  newPassword: string;
}

async function resetPassword({ token, newPassword }: ResetInput): Promise<undefined> {
  await api.post<unknown>("/auth/reset", { body: { token, new_password: newPassword }, skipAuthRetry: true });
  return undefined;
}

export function useResetPassword(): UseMutationResult<undefined, Error, ResetInput> {
  return useMutation<undefined, Error, ResetInput>({ mutationFn: resetPassword, gcTime: 0 });
}

async function forgotPassword({ email }: ForgotForm): Promise<undefined> {
  await api.post<unknown>("/auth/forgot", { body: { email }, skipAuthRetry: true });
  return undefined;
}

export function useForgotPassword(): UseMutationResult<undefined, Error, ForgotForm> {
  return useMutation<undefined, Error, ForgotForm>({ mutationFn: forgotPassword, gcTime: 0 });
}
