// S2-F5 (US-055, US-057, US-058): esquemas de los tres formularios de Configuración con los
// mismos rangos que el api (api/src/app/modules/settings/schemas.py, N-18) y mensajes en
// español que dicen qué pasó y qué hacer. Los formularios trabajan con texto (lo que da un
// <input>); los formularios convierten a null y a enteros al armar el PATCH.
// applyApiFieldError lleva un 422 con `field = "value.<campo>"` al campo del formulario.
import type { FieldValues, Path, UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { isApiError } from "../../core/api/errors";
import { pageSchema } from "../../core/api/page";
import { ROLES, STAFF_ROLES } from "../../core/auth/permissions";
import { PAYMENT_METHOD_CODES } from "../../shared/data/schemas/payment";
import type { AccountStatusView } from "../../shared/ui/statusLabel";

/** `^\d+(-\d)?$` del api: dígitos y, opcional, un guion con el dígito de verificación. */
export const NIT_PATTERN = /^\d+(-\d)?$/;
export const POLICY_TEXT_MAX = 20_000;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DIGITS = /^\d+$/;
const emailFormat = z.string().email();

const maxText = (max: number, message: string) => z.string().trim().max(max, message);

function isCalendarDate(value: string): boolean {
  const match = ISO_DATE.exec(value);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

/** Entero escrito en un campo de texto o número, dentro de [min, max]. */
function integerText(min: number, max: number) {
  return z
    .string()
    .trim()
    .min(1, "Escribe un número.")
    .regex(DIGITS, "Escribe un número entero, sin decimales ni signos.")
    .refine((value) => !DIGITS.test(value) || (Number(value) >= min && Number(value) <= max), `Escribe un número entre ${String(min)} y ${String(max)}.`);
}

export const gymSettingsSchema = z.object({
  name: z.string().trim().min(1, "Escribe el nombre del gimnasio.").max(80, "El nombre admite hasta 80 caracteres."),
  nit: z
    .string()
    .trim()
    .max(15, "El NIT admite hasta 15 caracteres.")
    .refine(
      (value) => value === "" || value.length > 15 || NIT_PATTERN.test(value),
      "El NIT no es válido. Usa solo dígitos y, si tiene, un guion con el dígito de verificación: 901234567-8.",
    ),
  address: maxText(120, "La dirección admite hasta 120 caracteres."),
  city: maxText(60, "La ciudad admite hasta 60 caracteres."),
  phone: maxText(20, "El teléfono admite hasta 20 caracteres."),
  whatsapp: maxText(20, "El WhatsApp admite hasta 20 caracteres."),
  email: z
    .string()
    .trim()
    .refine((value) => value === "" || emailFormat.safeParse(value).success, "El correo no es válido. Escríbelo completo, por ejemplo box@ejemplo.com."),
});

export const privacySettingsSchema = z.object({
  policy_version: z.string().trim().min(1, "Escribe la versión de la política, por ejemplo 2026-10.").max(20, "La versión admite hasta 20 caracteres."),
  policy_text: z
    .string()
    .trim()
    .min(1, "Escribe o pega el texto de la política.")
    .max(POLICY_TEXT_MAX, "El texto supera los 20.000 caracteres. Acórtalo antes de guardar."),
  retention_years: integerText(1, 20),
  consent_required_from: z
    .string()
    .trim()
    .refine((value) => value === "" || isCalendarDate(value), "Escribe una fecha válida o deja el campo vacío."),
});

export const membershipsSettingsSchema = z.object({
  expiring_days: integerText(1, 30),
  max_freeze_days_per_membership: integerText(0, 180),
  max_freezes_per_membership: integerText(0, 12),
  max_retroactive_days: integerText(0, 30),
});

export type GymSettingsForm = z.infer<typeof gymSettingsSchema>;
export type PrivacySettingsForm = z.infer<typeof privacySettingsSchema>;
export type MembershipsSettingsForm = z.infer<typeof membershipsSettingsSchema>;

// S3-F4 · US-056 (D24, S3-D55): las etiquetas de los tres medios fijos. `label` de 1 a 30 y `hint` hasta
// 120 (METHOD_LABEL_MAX_LENGTH y METHOD_HINT_MAX_LENGTH de settings/schemas.py), recortados; las tres
// etiquetas no se repiten sin distinguir mayúsculas: el error va en la segunda que repite, como el api.
export const METHOD_LABEL_MAX = 30;
export const METHOD_HINT_MAX = 120;

const methodLabelForm = z.object({
  label: z.string().trim().min(1, "Escribe el nombre del medio de pago.").max(METHOD_LABEL_MAX, `El nombre admite hasta ${String(METHOD_LABEL_MAX)} caracteres.`),
  hint: z.string().trim().max(METHOD_HINT_MAX, `La ayuda admite hasta ${String(METHOD_HINT_MAX)} caracteres.`),
});

export const DUPLICATE_LABEL_MESSAGE = "Ya hay otro medio con este nombre. Usa uno distinto.";

export const paymentMethodsSettingsSchema = z
  .object({ cash: methodLabelForm, nequi: methodLabelForm, breb: methodLabelForm })
  .superRefine((values, ctx) => {
    const seen = new Set<string>();
    for (const code of PAYMENT_METHOD_CODES) {
      const label = values[code].label.toLowerCase();
      if (seen.has(label)) ctx.addIssue({ code: z.ZodIssueCode.custom, path: [code, "label"], message: DUPLICATE_LABEL_MESSAGE });
      seen.add(label);
    }
  });
export type PaymentMethodsSettingsForm = z.infer<typeof paymentMethodsSettingsSchema>;

const VALUE_PREFIX = "value.";
const UNPROCESSABLE = 422;

/** S3-F4: ¿el formulario tiene el campo `a.b.c`? (los medios de pago tienen `nequi.label`). */
function hasPath(values: unknown, path: string): boolean {
  let current: unknown = values;
  for (const key of path.split(".")) {
    if (typeof current !== "object" || current === null || !Object.prototype.hasOwnProperty.call(current, key)) return false;
    current = (current as Record<string, unknown>)[key];
  }
  return true;
}

/**
 * Marca en el formulario el campo de un 422 del api (`field = "value.<campo>"`). Usa el
 * mensaje propio del campo si se da (el del api nombra el campo en inglés) y, si no, el del
 * api. Devuelve false si el error no es de un campo de este formulario.
 */
export function applyApiFieldError<T extends FieldValues>(
  form: Pick<UseFormReturn<T>, "setError" | "getValues">,
  error: unknown,
  messages: Partial<Record<string, string>> = {},
): boolean {
  if (!isApiError(error) || error.status !== UNPROCESSABLE || !error.field) return false;
  const name = error.field.startsWith(VALUE_PREFIX) ? error.field.slice(VALUE_PREFIX.length) : error.field;
  if (!hasPath(form.getValues(), name)) return false;
  form.setError(name as Path<T>, { type: "server", message: messages[name] ?? error.message }, { shouldFocus: true });
  return true;
}

// S2-F4a · US-046, US-047: fila de la lista de usuarios (UserRow del contrato de B3) y alta
// de un usuario del equipo (CreateUserIn: solo admin o coach hasta el portal, L-2).
/** Tope del correo en el api (EmailAddress, hasta 254). */
const EMAIL_MAX_LENGTH = 254;

export const ACCOUNT_STATUSES = ["active", "pending_activation", "locked", "inactive", "deleted"] as const satisfies readonly AccountStatusView[];


export const userRowSchema = z.object({
  id: z.string().min(1),
  email: z.string().min(1),
  role: z.enum(ROLES),
  status: z.enum(ACCOUNT_STATUSES),
  member_id: z.string().nullable(),
  last_login_at: z.string().nullable(),
  created_at: z.string(),
  active_sessions: z.number().int().nonnegative(),
});

export const usersPageSchema = pageSchema(userRowSchema);

export const USER_EMAIL_MESSAGES = {
  required: "Escribe el correo del usuario.",
  tooLong: `El correo admite hasta ${String(EMAIL_MAX_LENGTH)} caracteres.`,
  invalid: "Escribe un correo válido, por ejemplo ana@correo.com.",
} as const;

export const createUserSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, USER_EMAIL_MESSAGES.required)
    .max(EMAIL_MAX_LENGTH, USER_EMAIL_MESSAGES.tooLong)
    .email(USER_EMAIL_MESSAGES.invalid),
  role: z.enum(STAFF_ROLES, { errorMap: () => ({ message: "Elige un rol: Coach o Admin." }) }),
});

export type UserRowView = z.infer<typeof userRowSchema>;
export type CreateUserForm = z.infer<typeof createUserSchema>;

// S2-F4b · US-049 a US-052: detalle de una cuenta (UserOut de B5, incluye dadas de baja),
// edición (UpdateUserIn: correo y rol) y enlace reenviado (IssuedLinkOut).
export const userOutSchema = z.object({
  id: z.string().min(1),
  email: z.string().min(1),
  role: z.enum(ROLES),
  status: z.enum(ACCOUNT_STATUSES),
  member_id: z.string().nullable(),
  must_change_password: z.boolean(),
});

export const LINK_PURPOSES = ["activate", "reset"] as const;
export type LinkPurpose = (typeof LINK_PURPOSES)[number];

export const editUserSchema = z.object({
  email: createUserSchema.shape.email,
  role: z.enum(ROLES),
});

export type UserView = z.infer<typeof userOutSchema>;
export type EditUserForm = z.infer<typeof editUserSchema>;
