// S2-F3 · US-042: formulario de login. Topes del api (S2-D30): correo hasta 254 caracteres,
// contraseña de 1 a 128. El correo se recorta (el api lo normaliza); la contraseña no, porque
// un espacio puede ser parte de ella. Mensajes en español: qué pasó y qué hacer.
// S2-F4a: cambio de contraseña, restablecimiento y recuperación (al final).
import { z } from "zod";

export const EMAIL_MAX_LENGTH = 254;
export const PASSWORD_MAX_LENGTH = 128;

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Escribe tu correo.")
    .max(EMAIL_MAX_LENGTH, `El correo admite hasta ${String(EMAIL_MAX_LENGTH)} caracteres.`)
    .email("Escribe un correo válido, por ejemplo ana@correo.com."),
  password: z
    .string()
    .min(1, "Escribe tu contraseña.")
    .max(PASSWORD_MAX_LENGTH, `La contraseña admite hasta ${String(PASSWORD_MAX_LENGTH)} caracteres.`),
});

export type LoginForm = z.infer<typeof loginSchema>;

// S2-F4a · US-045, US-048: cambio de contraseña, restablecimiento y recuperación.
// Política del api (N-10, S2-D30): de 12 a 128 caracteres; el api además rechaza las comunes
// y, al cambiarla, la igual a la actual. Las contraseñas nunca se recortan.
export const PASSWORD_MIN_LENGTH = 12;

export const PASSWORD_MESSAGES = {
  currentRequired: "Escribe tu contraseña actual.",
  currentTooLong: `La contraseña actual admite hasta ${String(PASSWORD_MAX_LENGTH)} caracteres.`,
  newRequired: "Escribe la contraseña nueva.",
  newTooShort: `La contraseña nueva debe tener al menos ${String(PASSWORD_MIN_LENGTH)} caracteres.`,
  newTooLong: `La contraseña nueva admite hasta ${String(PASSWORD_MAX_LENGTH)} caracteres.`,
  confirmRequired: "Repite la contraseña nueva.",
  mismatch: "Las contraseñas no coinciden. Escribe la misma en los dos campos.",
  sameAsCurrent: "La contraseña nueva debe ser distinta de la actual.",
  policy: `Entre ${String(PASSWORD_MIN_LENGTH)} y ${String(PASSWORD_MAX_LENGTH)} caracteres. Evita las contraseñas comunes.`,
} as const;

const newPassword = z
  .string()
  .min(1, PASSWORD_MESSAGES.newRequired)
  .min(PASSWORD_MIN_LENGTH, PASSWORD_MESSAGES.newTooShort)
  .max(PASSWORD_MAX_LENGTH, PASSWORD_MESSAGES.newTooLong);

const confirmPassword = z.string().min(1, PASSWORD_MESSAGES.confirmRequired);

const sameConfirmation = (values: { newPassword: string; confirmPassword: string }): boolean =>
  values.confirmPassword === "" || values.newPassword === values.confirmPassword;

export const resetSchema = z
  .object({ newPassword, confirmPassword })
  .refine(sameConfirmation, { path: ["confirmPassword"], message: PASSWORD_MESSAGES.mismatch });

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, PASSWORD_MESSAGES.currentRequired).max(PASSWORD_MAX_LENGTH, PASSWORD_MESSAGES.currentTooLong),
    newPassword,
    confirmPassword,
  })
  .refine(sameConfirmation, { path: ["confirmPassword"], message: PASSWORD_MESSAGES.mismatch })
  .refine((values) => values.currentPassword === "" || values.newPassword !== values.currentPassword, {
    path: ["newPassword"],
    message: PASSWORD_MESSAGES.sameAsCurrent,
  });

export const forgotSchema = z.object({ email: loginSchema.shape.email });

export type ChangePasswordForm = z.infer<typeof changePasswordSchema>;
export type ResetForm = z.infer<typeof resetSchema>;
export type ForgotForm = z.infer<typeof forgotSchema>;
