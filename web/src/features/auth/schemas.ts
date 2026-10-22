// S2-F3 · US-042: formulario de login. Topes del api (S2-D30): correo hasta 254 caracteres,
// contraseña de 1 a 128. El correo se recorta (el api lo normaliza); la contraseña no, porque
// un espacio puede ser parte de ella. Mensajes en español: qué pasó y qué hacer.
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
