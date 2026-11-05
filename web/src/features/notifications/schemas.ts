// S5-F1 · US-127 a US-129 (front): contrato de los avisos del día (NotificationOut, WaLinkOut, SkipIn).
// - notificationRowSchema: NotificationOut tal cual y estricto; un campo que el contrato no declara
//   (por ejemplo un teléfono) es una respuesta inválida y no se pinta.
// - waLinkSchema: solo un enlace https://wa.me/<dígitos>[?texto]; cualquier otro origen se rechaza
//   antes de abrirlo.
// - skipBodySchema: el motivo, recortado, de 3 a 500 caracteres visibles (SkipIn).
import { z } from "zod";
import { pageSchema } from "../../core/api/page";

export const NOTIFICATION_CHANNELS = ["email", "whatsapp_link"] as const;
export const NOTIFICATION_STATUSES = ["pending", "sent", "failed", "skipped"] as const;

export const notificationRowSchema = z
  .object({
    id: z.string().min(1),
    rule_id: z.string().min(1),
    member_id: z.string().min(1),
    member_name: z.string(),
    membership_id: z.string().min(1),
    target_date: z.string().min(1),
    channel: z.enum(NOTIFICATION_CHANNELS),
    status: z.enum(NOTIFICATION_STATUSES),
    rendered_subject: z.string(),
    rendered_body: z.string(),
    attempts: z.number().int(),
    last_error: z.string().nullable(),
    sent_at: z.string().nullable(),
    sent_by: z.string().nullable(),
    skip_reason: z.string().nullable(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strict();
export type NotificationRowView = z.infer<typeof notificationRowSchema>;

export const notificationsPageSchema = pageSchema(notificationRowSchema);

const WA_URL = /^https:\/\/wa\.me\/\d{8,15}(\?[^\s#]*)?$/;

export const waLinkSchema = z.object({ url: z.string().regex(WA_URL) }).strict();
export type WaLinkView = z.infer<typeof waLinkSchema>;

export const SKIP_REASON_LIMITS = { min: 3, max: 500 } as const;

export const skipBodySchema = z
  .object({
    reason: z
      .string()
      .transform((value) => value.trim())
      .refine((value) => {
        const length = Array.from(value).length;
        return length >= SKIP_REASON_LIMITS.min && length <= SKIP_REASON_LIMITS.max;
      }),
  })
  .strict();
export type SkipBody = z.infer<typeof skipBodySchema>;

export const CANAL_FILTERS = ["whatsapp", "correo"] as const;
export type CanalFilter = (typeof CANAL_FILTERS)[number] | "todos";

/** `last_error` del aviso (conjunto cerrado de D24) en palabras. */
export const LAST_ERROR_LABELS: Readonly<Record<string, string>> = {
  timeout: "tiempo agotado",
  auth: "credenciales rechazadas",
  refused: "rechazado por el servidor",
  invalid_recipient: "correo no válido",
  unknown: "error desconocido",
};
