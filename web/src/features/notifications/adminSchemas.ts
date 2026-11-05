// S5-F2 · US-120 a US-122 y US-130 (front): reglas, plantillas, vista previa e historial (contrato de
// B6 y B7: RuleOut/RuleCreate/RulePatch, TemplateOut/TemplateCreate/TemplatePatch, PreviewIn/PreviewOut).
// - Las filas son estrictas: un campo que el contrato no declara es una respuesta inválida.
// - Los formularios usan texto (lo que da un <input>) y toRuleBody/toRulePatch arman el cuerpo: el
//   desfase del api es negativo antes del fin (por vencer) y positivo después (vencida).
import { z } from "zod";
import { pageSchema } from "../../core/api/page";
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";
import { NOTIFICATION_CHANNELS, NOTIFICATION_STATUSES } from "./schemas";

export const RULE_TRIGGERS = ["membership_expiring", "membership_expired"] as const;
export type RuleTrigger = (typeof RULE_TRIGGERS)[number];
export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];
export type NotificationStatus = (typeof NOTIFICATION_STATUSES)[number];

export const TRIGGER_LABELS: Readonly<Record<RuleTrigger, string>> = {
  membership_expiring: "Membresía por vencer",
  membership_expired: "Membresía vencida",
};

export const CHANNEL_LABELS: Readonly<Record<NotificationChannel, string>> = {
  email: "Correo",
  whatsapp_link: "WhatsApp manual",
};

export const STATUS_LABELS: Readonly<Record<NotificationStatus, string>> = {
  sent: "Enviado",
  failed: "Fallido",
  pending: "Pendiente",
  skipped: "Omitido",
};

/** Variables que acepta una plantilla (rules.py, ALLOWED_VARIABLES). */
export const TEMPLATE_VARIABLES = ["nombre", "plan", "vence", "dias"] as const;

export const ruleRowSchema = z
  .object({
    id: z.string().min(1),
    name: z.string(),
    trigger: z.enum(RULE_TRIGGERS),
    offset_days: z.number().int(),
    channel: z.enum(NOTIFICATION_CHANNELS),
    template_id: z.string().min(1),
    is_active: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strict();
export type RuleRowView = z.infer<typeof ruleRowSchema>;
export const rulesPageSchema = pageSchema(ruleRowSchema);

export const templateRowSchema = z
  .object({
    id: z.string().min(1),
    name: z.string(),
    subject: z.string(),
    body: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strict();
export type TemplateRowView = z.infer<typeof templateRowSchema>;
export const templatesPageSchema = pageSchema(templateRowSchema);

export const previewSchema = z.object({ subject: z.string(), body: z.string() }).strict();
export type PreviewView = z.infer<typeof previewSchema>;

/** "3 días antes del fin", "el día del fin", "1 día después del fin". */
export function ruleWhenText(rule: Pick<RuleRowView, "trigger" | "offset_days">): string {
  const days = Math.abs(rule.offset_days);
  if (days === 0) return "el día del fin";
  const unit = days === 1 ? "1 día" : `${String(days)} días`;
  return rule.trigger === "membership_expired" ? `${unit} después del fin` : `${unit} antes del fin`;
}

export const RULE_LIMITS = { nameMax: 80, daysMax: 3650 } as const;
export const TEMPLATE_LIMITS = { nameMax: 80, subjectMax: 150, bodyMax: 2000 } as const;

export const RULE_MESSAGES = {
  nameRequired: "Escribe el nombre de la regla.",
  nameTooLong: `El nombre admite hasta ${String(RULE_LIMITS.nameMax)} caracteres.`,
  daysInvalid: `Escribe un número entero de días entre 0 y ${String(RULE_LIMITS.daysMax)}.`,
  expiredNeedsDays: "Un aviso de vencida se manda 1 día o más después del fin.",
  templateRequired: "Elige la plantilla.",
} as const;

export interface RuleFormValues {
  name: string;
  trigger: RuleTrigger;
  /** Días tal como se ven: antes del fin (por vencer) o después (vencida). */
  days: string;
  channel: NotificationChannel;
  template_id: string;
  is_active: boolean;
}

export const EMPTY_RULE_FORM: RuleFormValues = { name: "", trigger: "membership_expiring", days: "0", channel: "email", template_id: "", is_active: true };

const DIGITS = /^\d{1,4}$/;

export const ruleFormSchema = z
  .object({
    name: z.string().trim().min(1, RULE_MESSAGES.nameRequired).max(RULE_LIMITS.nameMax, RULE_MESSAGES.nameTooLong),
    trigger: z.enum(RULE_TRIGGERS),
    days: z
      .string()
      .trim()
      .regex(DIGITS, RULE_MESSAGES.daysInvalid)
      .refine((value) => Number(value) <= RULE_LIMITS.daysMax, RULE_MESSAGES.daysInvalid),
    channel: z.enum(NOTIFICATION_CHANNELS),
    template_id: z.string().min(1, RULE_MESSAGES.templateRequired),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.trigger === "membership_expired" && DIGITS.test(values.days.trim()) && Number(values.days) < 1) {
      ctx.addIssue({ code: CUSTOM_ISSUE, path: ["days"], message: RULE_MESSAGES.expiredNeedsDays });
    }
  });

/** El desfase del api: negativo antes del fin (por vencer), positivo después (vencida); nunca -0. */
export function toOffsetDays(trigger: RuleTrigger, days: string): number {
  const value = Number(days.trim());
  return trigger === "membership_expiring" && value !== 0 ? -value : value;
}

export function ruleToForm(rule: RuleRowView): RuleFormValues {
  return {
    name: rule.name,
    trigger: rule.trigger,
    days: String(Math.abs(rule.offset_days)),
    channel: rule.channel,
    template_id: rule.template_id,
    is_active: rule.is_active,
  };
}

export interface RuleBody {
  name: string;
  trigger: RuleTrigger;
  offset_days: number;
  channel: NotificationChannel;
  template_id: string;
  is_active: boolean;
}

export function toRuleBody(values: RuleFormValues): RuleBody {
  return {
    name: values.name.trim(),
    trigger: values.trigger,
    offset_days: toOffsetDays(values.trigger, values.days),
    channel: values.channel,
    template_id: values.template_id,
    is_active: values.is_active,
  };
}

export type RulePatchBody = Partial<RuleBody>;
type Dirty<T> = Partial<Record<keyof T, boolean | undefined>>;

/** Solo lo que cambió (RulePatch); el evento y los días viajan juntos porque el signo depende del evento. */
export function toRulePatch(values: RuleFormValues, dirty: Dirty<RuleFormValues>): RulePatchBody {
  const body = toRuleBody(values);
  const patch: RulePatchBody = {};
  if (dirty.name) patch.name = body.name;
  if (dirty.trigger) patch.trigger = body.trigger;
  if (dirty.trigger || dirty.days) patch.offset_days = body.offset_days;
  if (dirty.channel) patch.channel = body.channel;
  if (dirty.template_id) patch.template_id = body.template_id;
  if (dirty.is_active) patch.is_active = body.is_active;
  return patch;
}

export const TEMPLATE_MESSAGES = {
  nameRequired: "Escribe el nombre de la plantilla.",
  nameTooLong: `El nombre admite hasta ${String(TEMPLATE_LIMITS.nameMax)} caracteres.`,
  subjectRequired: "Escribe el asunto.",
  subjectTooLong: `El asunto admite hasta ${String(TEMPLATE_LIMITS.subjectMax)} caracteres.`,
  bodyRequired: "Escribe el mensaje.",
  bodyTooLong: `El mensaje admite hasta ${String(TEMPLATE_LIMITS.bodyMax)} caracteres.`,
} as const;

export const templateFormSchema = z.object({
  name: z.string().trim().min(1, TEMPLATE_MESSAGES.nameRequired).max(TEMPLATE_LIMITS.nameMax, TEMPLATE_MESSAGES.nameTooLong),
  subject: z.string().trim().min(1, TEMPLATE_MESSAGES.subjectRequired).max(TEMPLATE_LIMITS.subjectMax, TEMPLATE_MESSAGES.subjectTooLong),
  body: z.string().trim().min(1, TEMPLATE_MESSAGES.bodyRequired).max(TEMPLATE_LIMITS.bodyMax, TEMPLATE_MESSAGES.bodyTooLong),
});
export type TemplateFormValues = z.infer<typeof templateFormSchema>;
export const EMPTY_TEMPLATE_FORM: TemplateFormValues = { name: "", subject: "", body: "" };

export type TemplatePatchBody = Partial<TemplateFormValues>;

export function toTemplatePatch(values: TemplateFormValues, dirty: Dirty<TemplateFormValues>): TemplatePatchBody {
  const patch: TemplatePatchBody = {};
  if (dirty.name) patch.name = values.name.trim();
  if (dirty.subject) patch.subject = values.subject.trim();
  if (dirty.body) patch.body = values.body.trim();
  return patch;
}

// Historial (US-130): los filtros que viven en la URL.
export const HISTORY_FILTERS = ["status", "channel", "rule_id", "from", "to"] as const;
export type HistoryFilter = (typeof HISTORY_FILTERS)[number];
