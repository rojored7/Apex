// S7-F4 · S7-D24 (H-2): comprueba la contraseña de la cuenta que está en sesión sin cambiar la sesión.
// POST /auth/login con el correo de la sesión; la respuesta se descarta (el token y el usuario siguen siendo los actuales).
// Devuelve el mensaje de error en palabras de la pantalla, o null si la contraseña es la correcta.
import { api } from "../api/client";
import { isApiError } from "../api/errors";
import { HTTP_TOO_MANY, HTTP_UNAUTHORIZED } from "../api/status";
import { connectionMessage, waitText } from "../../shared/lib/apiMessages";

export const CONFIRM_PASSWORD_MESSAGES = {
  wrong: "Contraseña incorrecta. Escríbela de nuevo.",
  tooMany: (wait: string): string => `Hiciste muchos intentos. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos verificar la contraseña. Intenta de nuevo en un momento.",
} as const;

export async function confirmPassword(email: string, password: string): Promise<string | null> {
  try {
    await api.post<unknown>("/auth/login", { body: { email, password }, skipAuthRetry: true });
    return null;
  } catch (error) {
    if (!isApiError(error)) return CONFIRM_PASSWORD_MESSAGES.generic;
    if (error.status === HTTP_UNAUTHORIZED) return CONFIRM_PASSWORD_MESSAGES.wrong;
    if (error.status === HTTP_TOO_MANY) return CONFIRM_PASSWORD_MESSAGES.tooMany(waitText(error.retryAfterS));
    return connectionMessage(error) ?? CONFIRM_PASSWORD_MESSAGES.generic;
  }
}
