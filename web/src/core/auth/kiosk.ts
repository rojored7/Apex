// S7-F4b · S7-D41: el modo quiosco lo impone el servidor. Entrar (POST /auth/kiosk) marca la sesión de refresco; salir
// (POST /auth/kiosk/exit) verifica la contraseña sin abrir otra sesión ni sumar al bloqueo de la cuenta. Las dos respuestas
// traen un access nuevo que reemplaza al de la sesión. Los mensajes dicen qué pasó y qué hacer.
import { z } from "zod";
import { api } from "../api/client";
import { API_ERROR_CODES } from "../api/errorCodes";
import { isApiError } from "../api/errors";
import { HTTP_FORBIDDEN, HTTP_TOO_MANY, HTTP_UNAUTHORIZED } from "../api/status";
import { connectionMessage, waitText } from "../../shared/lib/apiMessages";
import { applyKioskAccess, getSession, logout, refreshAccessToken, type LogoutResult } from "./session";

export const KIOSK_MESSAGES = {
  wrong: "Contraseña incorrecta. Escríbela de nuevo.",
  tooMany: (wait: string): string => `Hiciste muchos intentos. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos verificar la contraseña. Intenta de nuevo en un momento.",
  enterFailed: "No pudimos activar el modo tablet. Intenta de nuevo en un momento.",
  notToday: "Esa clase no es de hoy. Elige otra clase.",
  sessionEnded: "La sesión de esta tablet terminó. Vuelve a entrar con tu correo y contraseña.",
} as const;

/** KioskSessionOut del contrato. */
const kioskOutSchema = z.object({
  access_token: z.string().min(1),
  expires_in: z.number().int().positive(),
  kiosk_path: z.string().nullable(),
});

/** Activa el quiosco en `path`. Devuelve el mensaje de error, o null si quedó activo. */
export async function enterKiosk(path: string): Promise<string | null> {
  try {
    const out = kioskOutSchema.parse(await api.post<unknown>("/auth/kiosk", { body: { path } }));
    applyKioskAccess(out.access_token, out.expires_in, out.kiosk_path);
    return null;
  } catch (error) {
    // S7-F5b (M): cada fallo dice qué hacer; el selector no tiene «Reintentar», así que ningún texto lo pide.
    if (!isApiError(error)) return KIOSK_MESSAGES.enterFailed;
    if (error.status === HTTP_FORBIDDEN && error.code === API_ERROR_CODES.kioskMode) return KIOSK_MESSAGES.notToday;
    if (error.status === HTTP_TOO_MANY) return KIOSK_MESSAGES.tooMany(waitText(error.retryAfterS));
    return connectionMessage(error) ?? KIOSK_MESSAGES.enterFailed;
  }
}

/** Sale del quiosco con la contraseña de la cuenta. Devuelve el mensaje de error, o null si salió. */
export async function exitKiosk(password: string, renewed = false): Promise<string | null> {
  try {
    // skipAuthRetry: un 401 `invalid_password` no es una sesión vencida y no debe cerrarla.
    const out = kioskOutSchema.parse(await api.post<unknown>("/auth/kiosk/exit", { body: { password }, skipAuthRetry: true }));
    applyKioskAccess(out.access_token, out.expires_in, out.kiosk_path);
    return null;
  } catch (error) {
    if (!isApiError(error)) return KIOSK_MESSAGES.generic;
    // El access de 15 min venció con la tablet quieta: se renueva una vez y se repite.
    if (error.status === HTTP_UNAUTHORIZED && error.code === API_ERROR_CODES.tokenExpired && !renewed && (await refreshAccessToken())) return exitKiosk(password, true);
    if (error.status === HTTP_UNAUTHORIZED) {
      if (error.code === API_ERROR_CODES.invalidPassword) return KIOSK_MESSAGES.wrong;
      // S7-V7f (M-4): cualquier otro 401 es una sesión revocada o vencida: la tablet no se queda atrapada en «Contraseña incorrecta».
      void logoutDevice();
      return KIOSK_MESSAGES.sessionEnded;
    }
    if (error.status === HTTP_TOO_MANY) return KIOSK_MESSAGES.tooMany(waitText(error.retryAfterS));
    return connectionMessage(error) ?? KIOSK_MESSAGES.generic;
  }
}

/** La ruta tal como la acepta el api (S7-D41): minúsculas y sin barra final. */
export function normalizeKioskPath(path: string): string {
  return path.toLowerCase().replace(/\/+$/, "");
}

const LOGOUT_ATTEMPTS = 3;
const LOGOUT_RETRY_MS = 5000;

/** Cierra la sesión del dispositivo; si el api no confirma, reintenta (la marca solo muere con la revocación). */
export async function logoutDevice(): Promise<LogoutResult> {
  let result = await logout();
  for (let attempt = 1; !result.serverConfirmed && attempt < LOGOUT_ATTEMPTS; attempt += 1) {
    await new Promise<void>((resolve) => {
      setTimeout(resolve, LOGOUT_RETRY_MS);
    });
    // LOW-1: si en la espera entró otra persona, el reintento no revoca su sesión nueva.
    if (getSession().status !== "anonymous") break;
    result = await logout();
  }
  return result;
}
