// S2-D33, parte de S2-F2: almacén de la sesión en memoria y su restauración al recargar.
// - El access token y el usuario viven solo en este módulo: nada en localStorage ni en
//   sessionStorage (N-13, blueprint 7.6). El refresh viaja en la cookie HttpOnly.
// - restoreSession(): una sola promesa compartida por carga (StrictMode o varias guardas a la
//   vez hacen un único POST /auth/refresh y un único GET /auth/me). Las respuestas se validan
//   con Zod antes de usarlas; cualquier fallo deja la sesión anónima.
// - El rol sale de la respuesta de me (o de login en F3), nunca del JWT.
// S2-F3 agrega aquí refreshAccessToken (single-flight, Web Locks y BroadcastChannel), logout e
// installSessionBridge; este archivo es, con permissions.ts, el único donde se permite
// comparar un rol con un literal (tests/lint/restricted-config.ts).
import { useSyncExternalStore } from "react";
import { z } from "zod";
import { api, setAccessTokenGetter } from "../api/client";
import { ROLES, type Role } from "./permissions";

export interface SessionUser {
  id: string;
  email: string;
  role: Role;
  memberId: string | null;
  gymName: string;
  mustChangePassword: boolean;
}

export type SessionStatus = "loading" | "anonymous" | "authenticated";
export type ClearReason = "restore_failed" | "logout" | "expired" | "unauthorized";

export interface SessionState {
  status: SessionStatus;
  user: SessionUser | null;
  reason?: ClearReason | undefined;
}

export interface SessionPayload {
  accessToken: string;
  user: SessionUser;
}

/** RefreshOut del contrato (blueprint B2). */
const refreshOutSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  expires_in: z.number().int().positive(),
});

/** MeOut del contrato (blueprint B3, S2-D14). */
const meOutSchema = z.object({
  id: z.string().min(1),
  email: z.string().min(3),
  role: z.enum(ROLES),
  member_id: z.string().nullable(),
  gym_name: z.string(),
  must_change_password: z.boolean(),
});

const INITIAL: SessionState = Object.freeze({ status: "loading", user: null });

let state: SessionState = INITIAL;
let accessToken: string | null = null;
let restoring: Promise<boolean> | null = null;
/**
 * Sube con cada cambio explícito de sesión (login, cierre, reinicio). Una restauración que
 * termina después de uno de esos cambios ya no escribe nada: un cierre de sesión durante el
 * refresh no se deshace con su respuesta tardía.
 */
let generation = 0;
const listeners = new Set<() => void>();

function emit(next: SessionState): void {
  state = next;
  for (const listener of listeners) listener();
}

export function getSession(): SessionState {
  return state;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** El cliente del api lee de aquí el token vigente (idempotente). */
function connectClient(): void {
  setAccessTokenGetter(getAccessToken);
}

function applySession(token: string, user: SessionUser): void {
  connectClient();
  accessToken = token;
  emit({ status: "authenticated", user });
}

function applyAnonymous(reason: ClearReason): void {
  accessToken = null;
  emit({ status: "anonymous", user: null, reason });
}

export function setSession({ accessToken: token, user }: SessionPayload): void {
  generation += 1;
  applySession(token, user);
}

export function clearSession(reason: ClearReason): void {
  generation += 1;
  applyAnonymous(reason);
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSession(): SessionState {
  return useSyncExternalStore(subscribe, getSession, getSession);
}

function toSessionUser(me: z.infer<typeof meOutSchema>): SessionUser {
  return {
    id: me.id,
    email: me.email,
    role: me.role,
    memberId: me.member_id,
    gymName: me.gym_name,
    mustChangePassword: me.must_change_password,
  };
}

async function restore(): Promise<boolean> {
  connectClient();
  const startedAt = generation;
  const current = (): boolean => startedAt === generation;
  try {
    const refresh = refreshOutSchema.parse(await api.post<unknown>("/auth/refresh", { skipAuthRetry: true }));
    if (!current()) return false;
    accessToken = refresh.access_token;
    const me = meOutSchema.parse(await api.get<unknown>("/auth/me", { skipAuthRetry: true }));
    if (!current()) return false;
    applySession(refresh.access_token, toSessionUser(me));
    return true;
  } catch {
    if (current()) applyAnonymous("restore_failed");
    return false;
  }
}

export function restoreSession(): Promise<boolean> {
  if (restoring) return restoring;
  const pending: Promise<boolean> = restore().finally(() => {
    if (restoring === pending) restoring = null;
  });
  restoring = pending;
  return pending;
}

/** Solo pruebas: vuelve al estado inicial ("loading", sin token). */
export function resetSessionForTests(): void {
  generation += 1;
  accessToken = null;
  restoring = null;
  emit(INITIAL);
}
