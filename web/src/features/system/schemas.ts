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
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";

/** `^\d+(-\d)?$` del api: dígitos y, opcional, un guion con el dígito de verificación. */
export const NIT_PATTERN = /^\d+(-\d)?$/;
export const POLICY_TEXT_MAX = 20_000;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DIGITS = /^\d+$/;
const emailFormat = z.email();

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
      if (seen.has(label)) ctx.addIssue({ code: CUSTOM_ISSUE, path: [code, "label"], message: DUPLICATE_LABEL_MESSAGE });
      seen.add(label);
    }
  });
export type PaymentMethodsSettingsForm = z.infer<typeof paymentMethodsSettingsSchema>;

// S5-F2 · US-122: formulario de la pestaña Canales (mismos topes que ChannelsSettings del api).
export const SENDER_NAME_MAX = 80;
export const REPLY_TO_MAX = 254;
export const CHANNELS_MESSAGES = {
  senderRequired: "Escribe el nombre del remitente.",
  senderTooLong: `El remitente admite hasta ${String(SENDER_NAME_MAX)} caracteres.`,
  replyToInvalid: "Escribe un correo válido, por ejemplo hola@mibox.co.",
  countryInvalid: "El indicativo tiene de 1 a 3 dígitos, sin el signo +.",
} as const;

export const channelsSettingsSchema = z.object({
  // Revisión V10 (LOW 5, S5-D260): los objetos anidados son estrictos, como el contrato.
  email: z
    .object({
      enabled: z.boolean(),
      sender_name: z.string().trim().min(1, CHANNELS_MESSAGES.senderRequired).max(SENDER_NAME_MAX, CHANNELS_MESSAGES.senderTooLong),
      reply_to: z
        .string()
        .trim()
        .max(REPLY_TO_MAX, CHANNELS_MESSAGES.replyToInvalid)
        .refine((value) => value === "" || emailFormat.safeParse(value).success, CHANNELS_MESSAGES.replyToInvalid),
    })
    .strict(),
  whatsapp: z
    .object({
      enabled: z.boolean(),
      country_code: z.string().trim().regex(/^\d{1,3}$/, CHANNELS_MESSAGES.countryInvalid),
    })
    .strict(),
  telegram: z.object({ enabled: z.boolean() }).strict(),
});
export type ChannelsSettingsForm = z.infer<typeof channelsSettingsSchema>;

// S7-F1 · US-154 (S7-D8): pestaña Horario. Por día: «Cerrado» o un rango y, opcional, un segundo.
// Las horas son `HH:MM` de Bogotá (lo que da un <input type="time">). Mismas reglas que HoursSettings del api:
// cada rango abre antes de cerrar y el segundo empieza donde o después de donde termina el primero.
export const WEEK_DAY_LABELS = {
  monday: "Lunes",
  tuesday: "Martes",
  wednesday: "Miércoles",
  thursday: "Jueves",
  friday: "Viernes",
  saturday: "Sábado",
  sunday: "Domingo",
} as const;

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export const HOURS_MESSAGES = {
  missing: "Escribe la hora de apertura y la de cierre.",
  invalid: "Escribe la hora con formato HH:MM, por ejemplo 05:30.",
  order: (day: string): string => `La hora de apertura debe ser anterior a la de cierre. Corrige los horarios del ${day}.`,
  overlap: (day: string): string => `Los dos rangos del ${day} se solapan. El segundo debe empezar cuando o después de que termina el primero.`,
} as const;

const timeText = z.string().trim();

const dayHoursSchema = (dayName: string) =>
  z
  .object({ closed: z.boolean(), open1: timeText, close1: timeText, second: z.boolean(), open2: timeText, close2: timeText })
  .superRefine((day, ctx) => {
    if (day.closed) return;
    const issue = (path: "open1" | "close1" | "open2" | "close2", message: string): void => {
      ctx.addIssue({ code: CUSTOM_ISSUE, path: [path], message });
    };
    const rangeOk = (openPath: "open1" | "open2", closePath: "close1" | "close2", open: string, close: string): boolean => {
      if (open === "" || close === "") {
        if (open === "") issue(openPath, HOURS_MESSAGES.missing);
        if (close === "") issue(closePath, HOURS_MESSAGES.missing);
        return false;
      }
      if (!HHMM.test(open)) issue(openPath, HOURS_MESSAGES.invalid);
      if (!HHMM.test(close)) issue(closePath, HOURS_MESSAGES.invalid);
      return HHMM.test(open) && HHMM.test(close);
    };
    const first = rangeOk("open1", "close1", day.open1, day.close1);
    if (first && day.open1 >= day.close1) issue("close1", HOURS_MESSAGES.order(dayName));
    if (!day.second) return;
    const second = rangeOk("open2", "close2", day.open2, day.close2);
    if (!second) return;
    if (day.open2 >= day.close2) issue("close2", HOURS_MESSAGES.order(dayName));
    else if (first && day.open2 < day.close1) issue("open2", HOURS_MESSAGES.overlap(dayName));
  });

export const hoursSettingsSchema = z.object({
  monday: dayHoursSchema("lunes"),
  tuesday: dayHoursSchema("martes"),
  wednesday: dayHoursSchema("miércoles"),
  thursday: dayHoursSchema("jueves"),
  friday: dayHoursSchema("viernes"),
  saturday: dayHoursSchema("sábado"),
  sunday: dayHoursSchema("domingo"),
});
export type DayHoursForm = HoursSettingsForm["monday"];
export type HoursSettingsForm = z.infer<typeof hoursSettingsSchema>;

// S7-F1 · US-154: pestaña Clases (ClassesSettings del api: cupo 1 a 100, ventana 0 a 240).
export const classesSettingsSchema = z.object({
  default_capacity: integerText(1, 100),
  checkin_window_min: integerText(0, 240),
});
export type ClassesSettingsForm = z.infer<typeof classesSettingsSchema>;

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
    .regex(z.regexes.email, USER_EMAIL_MESSAGES.invalid),
  role: z.enum(STAFF_ROLES, { error: "Elige un rol: Coach o Admin." }),
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

// S4A-F1 · US-102 a US-104: auditoría (AuditRow, AuditDetail, FieldChange, VerifyResultOut y
// VerifyStartedOut de audit/schemas.py). Estrictos (como el api, `extra="forbid"`): una fila de la
// lista con `before` o `after` es una respuesta inválida, nunca datos (S4A-D16).
export const AUDIT_ACTIONS = ["insert", "update", "delete", "reveal", "export", "download", "login", "verify"] as const;
export type AuditAction = (typeof AUDIT_ACTIONS)[number];

const instant = z.iso.datetime({ offset: true });
const seqSchema = z.number().int().positive();

export const auditRowSchema = z
  .object({
    seq: seqSchema,
    at: instant,
    user_id: z.string().min(1),
    user_email: z.string().nullable(),
    user_name: z.string().nullable(),
    action: z.enum(AUDIT_ACTIONS),
    table_name: z.string().min(1),
    record_id: z.string().nullable(),
    subject_member_id: z.string().nullable(),
  })
  .strict();

export const auditPageSchema = pageSchema(auditRowSchema);

export const fieldChangeSchema = z
  .object({
    field: z.string(),
    kind: z.enum(["added", "removed", "changed"]),
    before: z.unknown(),
    after: z.unknown(),
    encrypted: z.boolean(),
  })
  .strict();

const snapshotSchema = z.record(z.string(), z.unknown()).nullable();

export const auditDetailSchema = auditRowSchema
  .extend({
    before: snapshotSchema,
    after: snapshotSchema,
    prev_hash: z.string(),
    hash: z.string(),
    changes: z.array(fieldChangeSchema),
  })
  .strict()
  // Revisión de seguridad de F1 (LOW 3): la pantalla pinta solo `changes`; las fotos completas
  // `before` y `after` se validan y se descartan, así no quedan en la caché de la consulta.
  .transform(({ seq, at, user_id, user_email, user_name, action, table_name, record_id, subject_member_id, prev_hash, hash, changes }) => ({
    seq,
    at,
    user_id,
    user_email,
    user_name,
    action,
    table_name,
    record_id,
    subject_member_id,
    prev_hash,
    hash,
    changes,
  }));

export const verifyResultSchema = z
  .object({
    ok: z.boolean(),
    rows_checked: z.number().int().nonnegative(),
    through_seq: z.number().int().nonnegative(),
    broken_at_seq: seqSchema.nullable(),
    started_at: instant,
    finished_at: instant,
    triggered_by: z.string().min(1),
    source: z.enum(["api", "cli"]),
    // S6-A3: campos planos de las firmas; ausentes o nulos en verificaciones anteriores a v0.3.
    signatures_checked: z.number().int().nonnegative().nullish(),
    signatures_valid: z.number().int().nonnegative().nullish(),
    first_invalid_signature_seq: seqSchema.nullish(),
    last_valid_signature_seq: seqSchema.nullish(),
    last_valid_signature_at: instant.nullish(),
    last_valid_signature_algorithm: z.string().min(1).nullish(),
  })
  .strict();

export const verifyStartedSchema = z
  .object({
    status: z.literal("running"),
    last: verifyResultSchema.nullable(),
  })
  .strict();

/** GET /audit/verify/last: la última verificación terminada o null (nunca 404). */
export const lastVerificationSchema = verifyResultSchema.nullable();

// S6-F1 · US-142: GET /audit/signatures/latest (SignaturesLatestOut y SignatureInfoOut de audit/schemas.py).
export const signatureInfoSchema = z
  .object({ through_seq: seqSchema, signed_at: instant, algorithm: z.string().min(1) })
  .strict();

export const signaturesLatestSchema = z
  .object({
    latest: signatureInfoSchema.nullable(),
    last_valid: signatureInfoSchema.nullable(),
    is_late: z.boolean(),
    state: z.enum(["none", "ok", "invalid"]),
    verified_at: instant.nullish(),
  })
  .strict();

export type SignatureInfoView = z.infer<typeof signatureInfoSchema>;
export type SignaturesLatestView = z.infer<typeof signaturesLatestSchema>;
export type AuditRowView = z.infer<typeof auditRowSchema>;
export type FieldChangeView = z.infer<typeof fieldChangeSchema>;
export type AuditDetailView = z.infer<typeof auditDetailSchema>;
export type VerifyResultView = z.infer<typeof verifyResultSchema>;
export type VerifyStartedView = z.infer<typeof verifyStartedSchema>;

// S6-F2 · US-143 a US-146: llaves de cifrado (CryptoKeyOut, KeysSummary, KeysPage, CryptoOpOut, CryptoJobOut y
// RotationStartedOut de core/crypto/schemas.py). Todos estrictos (`extra="forbid"` en el api): un campo de más,
// como material de llave, `wrapped_material`, una referencia `vault:` o el texto `error` de un trabajo, hace
// la respuesta inválida y nunca llega al estado ni a la caché. El id de usuario tiene forma de UUID sin
// exigir versión: el técnico del sistema (00000000-…-0001) no es un UUID RFC.
export const KEY_PURPOSES = ["encrypt", "index", "sign"] as const;
export const KEY_STATES = ["active", "decrypt_only", "retired"] as const;
export const KEY_PROVIDERS = ["local", "openbao"] as const;
export const CRYPTO_VERBS = ["encrypt", "decrypt", "index", "sign", "verify", "wrap", "unwrap", "rotate", "export"] as const;
export const JOB_KINDS = ["rotate", "reencrypt", "migrate_provider", "rewrap"] as const;
export const JOB_STATUSES = ["pending", "running", "done", "failed"] as const;
export const PROVIDER_STATES = ["ok", "sealed", "unreachable", "unknown"] as const;
export type KeyPurpose = (typeof KEY_PURPOSES)[number];
export type KeyState = (typeof KEY_STATES)[number];
export type KeyProvider = (typeof KEY_PROVIDERS)[number];
export type CryptoVerb = (typeof CRYPTO_VERBS)[number];
export type JobKind = (typeof JOB_KINDS)[number];
export type JobStatus = (typeof JOB_STATUSES)[number];
export type ProviderState = (typeof PROVIDER_STATES)[number];

/** Forma de UUID sin exigir versión: admite el usuario técnico fijo (00000000-…-0001) y no acepta texto libre. */
const UUID_SHAPE = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const count = z.number().int().nonnegative();

export const cryptoKeySchema = z
  .object({
    id: z.uuid(),
    purpose: z.enum(KEY_PURPOSES),
    data_class: z.string().min(1),
    algorithm: z.string().min(1),
    version: z.number().int().positive(),
    state: z.enum(KEY_STATES),
    provider: z.enum(KEY_PROVIDERS),
    created_at: instant,
    rotated_at: instant.nullable(),
    age_days: count,
    records_count: count.nullable(),
  })
  .strict();

export const keysSummarySchema = z
  .object({
    active_count: count,
    operations_today: count,
    running_jobs: count,
    provider: z.object({ names: z.array(z.string().min(1)), state: z.enum(PROVIDER_STATES) }).strict(),
  })
  .strict();

const pageShape = { total: count, limit: z.number().int().min(1).max(200), offset: count };

export const keysPageSchema = z.object({ items: z.array(cryptoKeySchema), ...pageShape, summary: keysSummarySchema }).strict();

export const cryptoOpSchema = z
  .object({
    id: z.uuid(),
    at: instant,
    user_id: z.string().regex(UUID_SHAPE),
    verb: z.enum(CRYPTO_VERBS),
    data_class: z.string().nullable(),
    key_id: z.uuid().nullable(),
    key_version: z.number().int().positive().nullable(),
    record_id: z.uuid().nullable(),
    purpose: z.string().nullable(),
    result: z.enum(["ok", "error"]),
    batch_id: z.uuid().nullable(),
    count,
  })
  .strict();

export const cryptoOpsPageSchema = z.object({ items: z.array(cryptoOpSchema), ...pageShape }).strict();

export const cryptoJobSchema = z
  .object({
    id: z.uuid(),
    kind: z.enum(JOB_KINDS),
    data_class: z.string().nullable(),
    status: z.enum(JOB_STATUSES),
    total: count,
    done: count,
    percent: z.number().int().min(0).max(100),
    started_at: instant.nullable(),
    finished_at: instant.nullable(),
    created_at: instant,
  })
  .strict();

export const cryptoJobsPageSchema = z.object({ items: z.array(cryptoJobSchema), ...pageShape }).strict();

export const rotationStartedSchema = z.object({ job_id: z.uuid(), new_key_id: z.uuid(), previous_key_id: z.uuid() }).strict();

export type CryptoKeyView = z.infer<typeof cryptoKeySchema>;
export type KeysSummaryView = z.infer<typeof keysSummarySchema>;
export type KeysPageView = z.infer<typeof keysPageSchema>;
export type CryptoOpView = z.infer<typeof cryptoOpSchema>;
export type CryptoOpsPageView = z.infer<typeof cryptoOpsPageSchema>;
export type CryptoJobView = z.infer<typeof cryptoJobSchema>;
export type CryptoJobsPageView = z.infer<typeof cryptoJobsPageSchema>;
export type RotationStartedView = z.infer<typeof rotationStartedSchema>;
