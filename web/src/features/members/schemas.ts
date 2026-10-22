// S2-F6 · US-069 y US-070 (front): formulario del alta y lista de socios.
// - memberFormSchema(hoy): las reglas de MemberCreate de B7 en el cliente (nombres y apellidos
//   de 1 a 100, documento de 3 a 30, teléfono con al menos 7 dígitos, correo con forma, fecha de
//   nacimiento real y no futura en hora de Bogotá, contacto de emergencia con nombre y teléfono
//   si se llena) con mensajes "qué pasó y qué hacer". Lo que solo sabe el servidor (L-3: un
//   documento que se normaliza a vacío) llega como 422 y va bajo su campo.
// - toMemberCreate: el cuerpo de POST /members. M-4: `data_consent` es el booleano de la casilla
//   y el servidor fija la fecha; el cliente nunca envía `data_consent_at`. M-5: no hay notas.
//   Los opcionales vacíos no viajan.
// - memberRowSchema es estricto: una fila con un campo de más (por ejemplo un dato cifrado o
//   enmascarado) es una respuesta inválida y no se pinta (N-01).
import { z } from "zod";
import { pageSchema } from "../../core/api/page";
import type { components } from "../../core/api/types";
import { todayBogota } from "../../core/i18n/format";

export type MemberCreateBody = components["schemas"]["MemberCreate"];

export const DOCUMENT_TYPES = ["CC", "CE", "TI", "PA"] as const satisfies readonly MemberCreateBody["document_type"][];
export type DocumentType = (typeof DOCUMENT_TYPES)[number];
/** Socio_Form.html: CC, CE, TI y Pasaporte (S2-D16). */
export const DOCUMENT_TYPE_LABELS: Readonly<Record<DocumentType, string>> = { CC: "CC", CE: "CE", TI: "TI", PA: "Pasaporte" };

export const SEXES = ["f", "m", "x"] as const;
export type Sex = (typeof SEXES)[number];
export const SEX_LABELS: Readonly<Record<Sex, string>> = { f: "Femenino", m: "Masculino", x: "Otro" };

/** Órdenes de GET /members (`MemberSort` de B8). */
export const MEMBER_SORTS = ["last_name", "-last_name", "first_name", "-first_name", "-created_at", "created_at"] as const;
export type MemberSort = (typeof MEMBER_SORTS)[number];
export const DEFAULT_MEMBER_SORT: MemberSort = "last_name";
export const MEMBER_SORT_LABELS: Readonly<Record<MemberSort, string>> = {
  last_name: "Apellido A–Z",
  "-last_name": "Apellido Z–A",
  first_name: "Nombre A–Z",
  "-first_name": "Nombre Z–A",
  "-created_at": "Más reciente",
  created_at: "Más antiguo",
};
/** Campos de orden que acepta la URL (useListParams compara el campo sin el signo). */
export const MEMBER_SORT_FIELDS = ["last_name", "first_name", "created_at"] as const;

/** El único estado que la lista ofrece en la URL: los dados de baja (N-20). */
export const DELETED_STATUS = "deleted";

/** Topes de `MemberCreate` (api/src/app/modules/members/schemas.py). */
export const MEMBER_LIMITS = {
  name: 100,
  documentMin: 3,
  documentMax: 30,
  phoneMax: 30,
  phoneMinDigits: 7,
  emailMax: 254,
  relationshipMax: 50,
} as const;

export const MEMBER_MESSAGES = {
  firstNameRequired: "Escribe el nombre del socio.",
  firstNameTooLong: `El nombre admite hasta ${String(MEMBER_LIMITS.name)} caracteres.`,
  lastNameRequired: "Escribe el apellido del socio.",
  lastNameTooLong: `El apellido admite hasta ${String(MEMBER_LIMITS.name)} caracteres.`,
  documentRequired: "Escribe el número de documento.",
  documentLength: `El documento debe tener entre ${String(MEMBER_LIMITS.documentMin)} y ${String(MEMBER_LIMITS.documentMax)} caracteres.`,
  documentType: "Elige el tipo de documento.",
  sex: "Elige una opción de la lista.",
  birthDateInvalid: "Escribe una fecha válida.",
  birthDateFuture: "La fecha de nacimiento no puede ser futura.",
  phoneDigits: `El teléfono debe tener al menos ${String(MEMBER_LIMITS.phoneMinDigits)} dígitos.`,
  phoneTooLong: `El teléfono admite hasta ${String(MEMBER_LIMITS.phoneMax)} caracteres.`,
  emailInvalid: "Escribe un correo válido, por ejemplo ana@correo.com.",
  emailTooLong: `El correo admite hasta ${String(MEMBER_LIMITS.emailMax)} caracteres.`,
  contactNameRequired: "Escribe el nombre del contacto de emergencia.",
  contactPhoneRequired: "Escribe el teléfono del contacto de emergencia.",
  relationshipTooLong: `El parentesco admite hasta ${String(MEMBER_LIMITS.relationshipMax)} caracteres.`,
} as const;

export interface EmergencyContactValues {
  name: string;
  phone: string;
  relationship: string;
}

export interface MemberFormValues {
  first_name: string;
  last_name: string;
  sex: "" | Sex;
  document_type: DocumentType;
  document: string;
  birth_date: string;
  phone: string;
  email: string;
  emergency_contact: EmergencyContactValues;
  data_consent: boolean;
}

/** M-4: la casilla de autorización nunca empieza marcada. */
export const EMPTY_MEMBER_FORM: MemberFormValues = Object.freeze({
  first_name: "",
  last_name: "",
  sex: "",
  document_type: "CC",
  document: "",
  birth_date: "",
  phone: "",
  email: "",
  emergency_contact: Object.freeze({ name: "", phone: "", relationship: "" }),
  data_consent: false,
});

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const NON_DIGITS = /\D/g;
/** La misma forma que check_email_shape del api (core/validators.py, `_FORMA_DE_CORREO`). */
const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function isCalendarDate(value: string): boolean {
  const match = ISO_DATE.exec(value);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

const requiredName = (required: string, tooLong: string) => z.string().trim().min(1, required).max(MEMBER_LIMITS.name, tooLong);

const optionalPhone = z
  .string()
  .trim()
  .max(MEMBER_LIMITS.phoneMax, MEMBER_MESSAGES.phoneTooLong)
  .refine((value) => value === "" || value.replace(NON_DIGITS, "").length >= MEMBER_LIMITS.phoneMinDigits, MEMBER_MESSAGES.phoneDigits);

const optionalEmail = z
  .string()
  .trim()
  .max(MEMBER_LIMITS.emailMax, MEMBER_MESSAGES.emailTooLong)
  .refine((value) => value === "" || EMAIL_SHAPE.test(value), MEMBER_MESSAGES.emailInvalid);

const emergencyContactSchema = z
  .object({
    name: z.string().trim().max(MEMBER_LIMITS.name, MEMBER_MESSAGES.firstNameTooLong),
    phone: z.string().trim().max(MEMBER_LIMITS.phoneMax, MEMBER_MESSAGES.phoneTooLong),
    relationship: z.string().trim().max(MEMBER_LIMITS.relationshipMax, MEMBER_MESSAGES.relationshipTooLong),
  })
  .superRefine((contact, ctx) => {
    const isEmpty = contact.name === "" && contact.phone === "" && contact.relationship === "";
    if (isEmpty) return;
    if (contact.name === "") ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["name"], message: MEMBER_MESSAGES.contactNameRequired });
    if (contact.phone === "") ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["phone"], message: MEMBER_MESSAGES.contactPhoneRequired });
  });

/** Reglas del alta; `today` (AAAA-MM-DD, Bogotá) se inyecta en las pruebas. */
export function memberFormSchema(today: string = todayBogota()): z.ZodType<MemberFormValues, z.ZodTypeDef, MemberFormValues> {
  return z.object({
    first_name: requiredName(MEMBER_MESSAGES.firstNameRequired, MEMBER_MESSAGES.firstNameTooLong),
    last_name: requiredName(MEMBER_MESSAGES.lastNameRequired, MEMBER_MESSAGES.lastNameTooLong),
    sex: z.union([z.literal(""), z.enum(SEXES)], { errorMap: () => ({ message: MEMBER_MESSAGES.sex }) }),
    document_type: z.enum(DOCUMENT_TYPES, { errorMap: () => ({ message: MEMBER_MESSAGES.documentType }) }),
    document: z
      .string()
      .trim()
      .min(1, MEMBER_MESSAGES.documentRequired)
      .refine((value) => value.length >= MEMBER_LIMITS.documentMin && value.length <= MEMBER_LIMITS.documentMax, MEMBER_MESSAGES.documentLength),
    birth_date: z
      .string()
      .trim()
      .superRefine((value, ctx) => {
        if (value === "") return;
        if (!isCalendarDate(value)) ctx.addIssue({ code: z.ZodIssueCode.custom, message: MEMBER_MESSAGES.birthDateInvalid });
        // AAAA-MM-DD se compara como texto en orden de calendario.
        else if (value > today) ctx.addIssue({ code: z.ZodIssueCode.custom, message: MEMBER_MESSAGES.birthDateFuture });
      }),
    phone: optionalPhone,
    email: optionalEmail,
    emergency_contact: emergencyContactSchema,
    data_consent: z.boolean(),
  });
}

/** Cuerpo de POST /members: sin opcionales vacíos, sin notas y sin `data_consent_at` (M-4, M-5). */
export function toMemberCreate(values: MemberFormValues): MemberCreateBody {
  const contact = values.emergency_contact;
  const hasContact = contact.name !== "" || contact.phone !== "";
  return {
    first_name: values.first_name,
    last_name: values.last_name,
    ...(values.sex ? { sex: values.sex } : {}),
    document_type: values.document_type,
    document: values.document,
    ...(values.birth_date ? { birth_date: values.birth_date } : {}),
    ...(values.phone ? { phone: values.phone } : {}),
    ...(values.email ? { email: values.email } : {}),
    ...(hasContact ? { emergency_contact: { name: contact.name, phone: contact.phone, ...(contact.relationship ? { relationship: contact.relationship } : {}) } } : {}),
    data_consent: values.data_consent,
  };
}

/** Fila de GET /members (MemberRowOut de B8): nada sensible, ni enmascarado (N-01). */
export const memberRowSchema = z
  .object({
    id: z.string().min(1),
    first_name: z.string(),
    last_name: z.string(),
    sex: z.enum(SEXES).nullable(),
    status: z.enum(["active", "inactive"]),
    deleted_at: z.string().nullable(),
    membership_status: z.string().nullable().default(null),
    plan_name: z.string().nullable().default(null),
  })
  .strict();

export type MemberRowView = z.infer<typeof memberRowSchema>;
export const membersPageSchema = pageSchema(memberRowSchema);

/** Lo que el alta usa de MemberDetailOut: el id, el nombre y los avisos (`data_consent_missing`). */
export const memberDetailSchema = z.object({
  id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  warnings: z.array(z.string()),
});

export const DATA_CONSENT_MISSING = "data_consent_missing";
