// S2-F3 · US-042: POST /auth/login (LoginOut de B2).
// - skipAuthRetry: un 401 de credenciales malas nunca dispara un refresh.
// - La respuesta se valida con Zod; con ella se arma la sesión en memoria (setSession). El
//   gimnasio y el socio no vienen en LoginOut: llegan después con GET /auth/me
//   (refreshCurrentUser), sin bloquear la entrada; mientras tanto el gimnasio es "APEX".
// - loginErrorMessage traduce el error a un mensaje "qué pasó y qué hacer". Un 401 nunca dice
//   si la cuenta existe, está bloqueada o pendiente.
import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import type { components } from "../../core/api/types";
import { ROLES } from "../../core/auth/permissions";
import { refreshCurrentUser, setSession, type SessionPayload, type SessionUser } from "../../core/auth/session";
import type { LoginForm } from "./schemas";

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
  // Sin respuesta (status 0): red o timeout. Con respuesta manda el código HTTP, aunque el cuerpo
  // no sea el envelope (un 429 o un 502 de Nginx llegan como network_error).
  if (error.status === 0) return error.code === "timeout" ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error;
  if (error.status === HTTP_UNAUTHORIZED) return LOGIN_MESSAGES.invalidCredentials;
  if (error.status === HTTP_TOO_MANY) {
    return error.retryAfterS !== undefined && error.retryAfterS > 0 ? LOGIN_MESSAGES.tooManyWait(error.retryAfterS) : LOGIN_MESSAGES.tooMany;
  }
  if (error.status === HTTP_UNPROCESSABLE) return LOGIN_MESSAGES.invalidData;
  if (error.status >= HTTP_SERVER_ERROR) return LOGIN_MESSAGES.server;
  return LOGIN_MESSAGES.generic;
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
