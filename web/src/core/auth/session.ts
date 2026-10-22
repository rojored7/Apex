// S2-D33: la sesión del front (blueprint 7.6).
// Parte de S2-F2: almacén en memoria y restauración al recargar.
// - El access token y el usuario viven solo en este módulo: nada en el almacenamiento del
//   navegador (N-13). El refresh viaja en la cookie HttpOnly `apex_refresh`.
// - restoreSession(): una sola promesa compartida por carga (StrictMode o varias guardas a la
//   vez hacen un único POST /auth/refresh y un único GET /auth/me). Las respuestas se validan
//   con Zod antes de usarlas; cualquier fallo deja la sesión anónima.
// - El rol sale de la respuesta de me o de login, nunca del JWT.
// Parte de S2-F3 (US-043, US-044):
// - refreshAccessToken(): tres defensas contra el reuso por concurrencia. Una promesa única por
//   pestaña; el candado `apex-refresh` entre pestañas, dentro del cual se mira si otra pestaña
//   ya publicó un token nuevo; y el canal `apex-auth` (tabSync.ts) para repartirlo.
//   Un 401 del refresh limpia la sesión ("expired"); un 429, un 5xx o la red no (L-12).
// - logout(): POST /auth/logout por la cookie; publica `logout`, limpia la sesión y la caché.
//   Si el api no lo confirmó (red, 5xx) la razón es `logout_unconfirmed` (H-1).
// - installSessionBridge(): conecta el token y el gancho del 401 con core/api/client.ts y abre
//   el canal. main.tsx la llama antes de montar.
// Este archivo es, con permissions.ts, el único donde se permite comparar un rol con un
// literal (tests/lint/restricted-config.ts).
import { useSyncExternalStore } from "react";
import { z } from "zod";
import { api, registerOnUnauthorized, setAccessTokenGetter, type UnauthorizedHandler } from "../api/client";
import { isApiError } from "../api/errors";
import { queryClient } from "../api/queryClient";
import { ROLES, type Role } from "./permissions";
import { hasRefreshLock, openTabSync, withRefreshLock, type AuthMessage, type OutgoingAuthMessage, type TabSync } from "./tabSync";

export { AUTH_CHANNEL, REFRESH_LOCK } from "./tabSync";

export interface SessionUser {
  id: string;
  email: string;
  role: Role;
  memberId: string | null;
  gymName: string;
  mustChangePassword: boolean;
}

export type SessionStatus = "loading" | "anonymous" | "authenticated";
/**
 * Por qué no hay sesión. `logout_unconfirmed` (H-1): se cerró en este navegador, pero el api
 * no confirmó el cierre (red caída o 5xx); la pantalla de login lo avisa.
 */
export type ClearReason = "restore_failed" | "logout" | "logout_unconfirmed" | "expired" | "unauthorized";

export interface SessionState {
  status: SessionStatus;
  user: SessionUser | null;
  reason?: ClearReason | undefined;
}

export interface SessionPayload {
  accessToken: string;
  user: SessionUser;
}

export interface LogoutResult {
  /** `false` si el api no confirmó el cierre (red, 5xx u otro error): H-1. */
  serverConfirmed: boolean;
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

/**
 * Tras publicar un token, quien tiene el candado lo retiene este tiempo: el mensaje del canal
 * llega a las demás pestañas antes de que alguna entre al candado y pida otro refresh.
 */
const CHANNEL_SETTLE_MS = 50;

const INITIAL: SessionState = Object.freeze({ status: "loading", user: null });

let state: SessionState = INITIAL;
let accessToken: string | null = null;
let restoring: Promise<boolean> | null = null;
let refreshing: Promise<boolean> | null = null;
let loggingOut: Promise<LogoutResult> | null = null;
let tabSync: TabSync | null = null;
let bridge: { uninstall: () => void } | null = null;
/**
 * Sube con cada cambio explícito de sesión (login, cierre, reinicio). Una restauración, un
 * refresh o una lectura de me que terminan después de uno de esos cambios ya no escriben nada:
 * un cierre de sesión durante el refresh no se deshace con su respuesta tardía.
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

/** Sin sesión no queda nada en memoria: ni token ni datos del api en la caché. */
function applyAnonymous(reason: ClearReason): void {
  accessToken = null;
  queryClient.clear();
  emit({ status: "anonymous", user: null, reason });
}

export function setSession({ accessToken: token, user }: SessionPayload): void {
  generation += 1;
  refreshing = null;
  applySession(token, user);
}

export function clearSession(reason: ClearReason): void {
  generation += 1;
  refreshing = null;
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

/** Publicar nunca impide cerrar ni renovar en esta pestaña (canal cerrado, navegador raro). */
function publish(message: OutgoingAuthMessage): void {
  try {
    tabSync?.publish(message);
  } catch {
    // Las demás pestañas se enteran en su próxima petición (401 o refresh).
  }
}

const settle = (): Promise<void> =>
  tabSync !== null && hasRefreshLock()
    ? new Promise((resolve) => {
        setTimeout(resolve, CHANNEL_SETTLE_MS);
      })
    : Promise.resolve();

/**
 * Dentro del candado: si otra pestaña ya dejó un token distinto de `stale`, se usa ese; si no,
 * POST /auth/refresh, se publica el nuevo y se retiene el candado un instante. Devuelve el
 * token, o null si la sesión cambió mientras tanto (login, cierre o reinicio).
 */
async function obtainFreshToken(stale: string | null, startedAt: number): Promise<string | null> {
  return withRefreshLock(async () => {
    if (startedAt !== generation) return null;
    if (accessToken !== null && accessToken !== stale) return accessToken;
    const out = refreshOutSchema.parse(await api.post<unknown>("/auth/refresh", { skipAuthRetry: true }));
    if (startedAt !== generation) return null;
    accessToken = out.access_token;
    publish({ type: "token", accessToken: out.access_token, expiresIn: out.expires_in });
    await settle();
    return out.access_token;
  });
}

async function restore(): Promise<boolean> {
  connectClient();
  const startedAt = generation;
  const current = (): boolean => startedAt === generation;
  try {
    const token = await obtainFreshToken(accessToken, startedAt);
    if (token === null || !current()) return false;
    const me = meOutSchema.parse(await api.get<unknown>("/auth/me", { skipAuthRetry: true }));
    if (!current()) return false;
    // Un token más nuevo pudo llegar por el canal mientras se leía me: se conserva ese.
    applySession(accessToken ?? token, toSessionUser(me));
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

async function runRefresh(): Promise<boolean> {
  const startedAt = generation;
  try {
    return (await obtainFreshToken(accessToken, startedAt)) !== null;
  } catch (error) {
    // Solo un 401 dice que la cookie ya no sirve; 429, 5xx, red o una forma inesperada no
    // cierran la sesión (L-12): la petición original falla y se puede reintentar.
    if (startedAt === generation && isApiError(error) && error.status === 401) clearSession("expired");
    return false;
  }
}

/** Renueva el access con la cookie. Una sola promesa en curso por pestaña. */
export function refreshAccessToken(): Promise<boolean> {
  if (refreshing) return refreshing;
  if (state.status !== "authenticated") return Promise.resolve(false);
  const pending: Promise<boolean> = runRefresh().finally(() => {
    if (refreshing === pending) refreshing = null;
  });
  refreshing = pending;
  return pending;
}

/**
 * Toma un access nuevo que entregó el api fuera del refresh (S2-D37: cambiar la contraseña)
 * y lo reparte a las demás pestañas. Sin sesión no hace nada.
 */
export function adoptAccessToken(token: string, expiresIn: number): void {
  if (state.status !== "authenticated") return;
  accessToken = token;
  publish({ type: "token", accessToken: token, expiresIn });
}

/**
 * Relee el usuario con GET /auth/me (gimnasio, socio, rol y must_change_password vigentes).
 * Si falla (429, red, forma inesperada) se conserva el usuario actual (L-12); si me es de otra
 * cuenta, la sesión de esta pestaña se cierra.
 */
export async function refreshCurrentUser(): Promise<void> {
  const user = state.user;
  if (state.status !== "authenticated" || user === null) return;
  const startedAt = generation;
  try {
    const me = meOutSchema.parse(await api.get<unknown>("/auth/me"));
    // La misma generación implica la misma sesión abierta (login y cierre la suben).
    if (startedAt !== generation) return;
    // Otro usuario: la cookie ya es de otra cuenta (otra pestaña entró con ella).
    if (me.id !== user.id) {
      clearSession("unauthorized");
      return;
    }
    emit({ status: "authenticated", user: toSessionUser(me) });
  } catch {
    // L-12: el usuario se queda como estaba.
  }
}

async function runLogout(): Promise<LogoutResult> {
  let serverConfirmed: boolean;
  try {
    await api.post<unknown>("/auth/logout", { skipAuthRetry: true });
    serverConfirmed = true;
  } catch {
    serverConfirmed = false;
  }
  // publish nunca lanza: la limpieza local ocurre siempre.
  publish({ type: "logout" });
  clearSession(serverConfirmed ? "logout" : "logout_unconfirmed");
  return { serverConfirmed };
}

/** Cierra la sesión en el api (cookie) y en todas las pestañas; dos clics hacen un solo POST. */
export function logout(): Promise<LogoutResult> {
  if (loggingOut) return loggingOut;
  const pending: Promise<LogoutResult> = runLogout().finally(() => {
    if (loggingOut === pending) loggingOut = null;
  });
  loggingOut = pending;
  return pending;
}

function onTabMessage(message: AuthMessage): void {
  if (message.type === "logout") {
    if (state.status !== "anonymous") clearSession("logout");
    return;
  }
  // L-6: tras un logout (o sin sesión) un token ajeno se ignora; mientras restaura, se guarda
  // para que el refresh de esta pestaña lo use en lugar de pedir otro.
  if (state.status === "anonymous") return;
  accessToken = message.accessToken;
  // La cookie es del navegador: si otra pestaña entró con otra cuenta, el token es de ella.
  // Se relee me y, si el usuario cambió, esta pestaña cierra su sesión.
  if (state.status === "authenticated") void refreshCurrentUser();
}

const onUnauthorized: UnauthorizedHandler = async (error, { accessToken: used }) => {
  if (state.status !== "authenticated") return "fail";
  // Otra petición (o un login) ya cambió el token mientras esta volvía con el 401: la respuesta
  // habla del token viejo, así que se reintenta sin refresh y sin cerrar la sesión nueva.
  if (accessToken !== null && accessToken !== used) return "retry";
  if (error.code !== "token_expired") {
    clearSession("unauthorized");
    return "fail";
  }
  return (await refreshAccessToken()) ? "retry" : "fail";
};

/** Conecta la sesión con el cliente del api y con las demás pestañas. Idempotente. */
export function installSessionBridge(): () => void {
  if (bridge) return bridge.uninstall;
  connectClient();
  registerOnUnauthorized(onUnauthorized);
  tabSync = openTabSync(onTabMessage);
  const installed = {
    uninstall: (): void => {
      if (bridge !== installed) return;
      registerOnUnauthorized(null);
      tabSync?.close();
      tabSync = null;
      bridge = null;
    },
  };
  bridge = installed;
  return installed.uninstall;
}

/** Solo pruebas: vuelve al estado inicial ("loading", sin token ni operaciones en curso). */
export function resetSessionForTests(): void {
  generation += 1;
  accessToken = null;
  restoring = null;
  refreshing = null;
  loggingOut = null;
  emit(INITIAL);
}
