// S2-F4a: avisos que otra pantalla deja para /login en el estado de la navegación (nunca en la
// URL). Hoy solo uno: tras guardar la contraseña con el enlace (ResetPage), "ya puedes entrar".
// El estado se valida con Zod: cualquier otra cosa se ignora.
import { z } from "zod";

export const LOGIN_NOTICE_PASSWORD_SET = "password_set";

const NOTICE_TEXTS = {
  [LOGIN_NOTICE_PASSWORD_SET]: "Tu contraseña quedó guardada. Inicia sesión con ella.",
} as const;

const stateSchema = z.object({ notice: z.literal(LOGIN_NOTICE_PASSWORD_SET) });

/** El texto del aviso que trae `location.state`, o null. */
export function loginNoticeFrom(state: unknown): string | null {
  const parsed = stateSchema.safeParse(state);
  return parsed.success ? NOTICE_TEXTS[parsed.data.notice] : null;
}
