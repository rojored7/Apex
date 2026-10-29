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
// - S3-B9b (D35): la fila gana `membership_end_date` (fecha de fin de la membresía que decide el
//   estado, "Vence") y la ficha `plan_name` y `membership_end_date`, opcionales y `null` por
//   defecto, en el mismo checkpoint del backend; la lógica de pantalla llega con F1 y F2.
// - S3-F1 (US-073 a US-076): la ficha (memberDetailViewSchema), revelar (revealOutSchema,
//   flattenRevealed) y la edición (memberEditSchema, toMemberPatch); ver su bloque al final.
// - S3-F2 (US-071): los siete chips de la lista (`MEMBERSHIP_CHIPS`) y su traducción a filtros de
//   GET /members (`chipToFilter`, como `chip_to_filter` del api; `chipFromFilters` lee la URL).
import type { FieldNamesMarkedBoolean } from "react-hook-form";
import { z } from "zod";
import { pageSchema } from "../../core/api/page";
import type { components, operations } from "../../core/api/types";
import { formatDate, todayBogota } from "../../core/i18n/format";
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";

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

/** El único estado de la cuenta que la lista ofrece en la URL: los dados de baja (N-20). */
export const DELETED_STATUS = "deleted";

/** `membership_status` de GET /members (MembershipFilterStatus de S3-B9b, D22). */
export type MembershipFilterStatus = NonNullable<NonNullable<operations["list_members_api_v1_members_get"]["parameters"]["query"]>["membership_status"]>;

export const MEMBERSHIP_FILTER_STATUSES = ["active", "expiring", "expired", "frozen", "pending_payment", "none"] as const satisfies readonly MembershipFilterStatus[];

/**
 * S3-F2 · US-071: los siete chips de la lista en el orden de Socios_Lista.html, como
 * `MEMBER_CHIPS` de `members/rules.py` (S3-B9b). "Todos" no es un chip: es no tener ninguno.
 */
export const MEMBERSHIP_CHIPS = [...MEMBERSHIP_FILTER_STATUSES, DELETED_STATUS] as const;
export type MemberChip = (typeof MEMBERSHIP_CHIPS)[number];

export const MEMBERSHIP_CHIP_LABELS: Readonly<Record<MemberChip, string>> = {
  active: "Al día",
  expiring: "Por vencer",
  expired: "Vencidos",
  frozen: "Congelados",
  // DESIGN-GAP (Q3): "Pendiente de pago" no está dibujado en Socios_Lista.html.
  pending_payment: "Pendiente de pago",
  none: "Sin membresía",
  deleted: "Dados de baja",
};

/** Los filtros de GET /members que fija un chip (`chip_to_filter` de S3-B9b). */
export interface MemberChipFilter {
  status?: typeof DELETED_STATUS;
  membership_status?: MembershipFilterStatus;
}

export function chipToFilter(chip: MemberChip | null): MemberChipFilter {
  if (chip === null) return {};
  return chip === DELETED_STATUS ? { status: DELETED_STATUS } : { membership_status: chip };
}

const isMembershipFilter = (value: string | undefined): value is MembershipFilterStatus =>
  value !== undefined && (MEMBERSHIP_FILTER_STATUSES as readonly string[]).includes(value);

/**
 * El chip que dicen los filtros de la URL, o null ("Todos"). La baja manda: con `status=deleted`
 * un `membership_status` de más no cuenta (los chips son de modo único). Lo desconocido es null.
 */
export function chipFromFilters(status: readonly string[], membershipStatus: readonly string[]): MemberChip | null {
  if (status[0] === DELETED_STATUS) return DELETED_STATUS;
  const membership = membershipStatus[0];
  return isMembershipFilter(membership) ? membership : null;
}

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
    if (contact.name === "") ctx.addIssue({ code: CUSTOM_ISSUE, path: ["name"], message: MEMBER_MESSAGES.contactNameRequired });
    if (contact.phone === "") ctx.addIssue({ code: CUSTOM_ISSUE, path: ["phone"], message: MEMBER_MESSAGES.contactPhoneRequired });
  });

/** Reglas del alta; `today` (AAAA-MM-DD, Bogotá) se inyecta en las pruebas. */
export function memberFormSchema(today: string = todayBogota()): z.ZodType<MemberFormValues, MemberFormValues> {
  return z.object({
    first_name: requiredName(MEMBER_MESSAGES.firstNameRequired, MEMBER_MESSAGES.firstNameTooLong),
    last_name: requiredName(MEMBER_MESSAGES.lastNameRequired, MEMBER_MESSAGES.lastNameTooLong),
    sex: z.union([z.literal(""), z.enum(SEXES)], { error: MEMBER_MESSAGES.sex }),
    document_type: z.enum(DOCUMENT_TYPES, { error: MEMBER_MESSAGES.documentType }),
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
        if (!isCalendarDate(value)) ctx.addIssue({ code: CUSTOM_ISSUE, message: MEMBER_MESSAGES.birthDateInvalid });
        // AAAA-MM-DD se compara como texto en orden de calendario.
        else if (value > today) ctx.addIssue({ code: CUSTOM_ISSUE, message: MEMBER_MESSAGES.birthDateFuture });
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
    membership_end_date: z.string().nullable().optional().default(null),
  })
  .strict();

export type MemberRowView = z.infer<typeof memberRowSchema>;
export const membersPageSchema = pageSchema(memberRowSchema);

/** Lo que el alta usa de MemberDetailOut: el id, el nombre y los avisos (`data_consent_missing`);
 *  desde S3-B9b (D35) también acepta el plan y el fin de la membresía que decide el estado. */
export const memberDetailSchema = z.object({
  id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  warnings: z.array(z.string()),
  plan_name: z.string().nullable().optional().default(null),
  membership_end_date: z.string().nullable().optional().default(null),
});

export const DATA_CONSENT_MISSING = "data_consent_missing";

// ---------------------------------------------------------------------------------------------
// S3-F1 · US-073 a US-076 (front): ficha, revelar, editar, dar de baja y reactivar.
// - memberDetailViewSchema: GET /members/{id} (MemberDetailOut de B9b). Los cinco sensibles llegan
//   enmascarados por el api (N-01) y se pintan tal cual. Una clave que no está en el contrato se
//   descarta al validar: nunca llega a la pantalla.
// - revealOutSchema: POST /members/{id}/reveal (RevealOut, B10). Estricto y con el tipo del valor
//   atado al campo (el contacto es un objeto; los demás, texto). flattenRevealed lo vuelve texto de
//   pantalla. El claro solo vive en el estado de MaskedValue (S3-D52).
// - Edición (MemberPatch cerrado, S3-D46): los sensibles nunca se precargan en claro; cada uno
//   está en "keep" (no viaja), "change" (se escribe el valor nuevo) o "remove" (viaja `null`; el
//   documento no se puede quitar). toMemberPatch arma el cuerpo solo con lo modificado:
//   `dirtyFields` para lo no sensible y el modo para lo sensible. `data_consent` solo viaja `true`
//   (retirarla da 422 `consent_cannot_be_withdrawn`); nunca `status`, `deleted_at` ni
//   `data_consent_at`.

/** Los cinco campos cifrados que `POST /members/{id}/reveal` acepta (RevealIn). */
export const REVEAL_FIELDS = ["document", "phone", "email", "birth_date", "emergency_contact"] as const satisfies readonly components["schemas"]["RevealIn"]["field"][];
export type RevealField = (typeof REVEAL_FIELDS)[number];

/** Cuerpo de `PATCH /members/{id}` (MemberPatch cerrado, S3-D46). */
export type MemberPatchBody = components["schemas"]["MemberPatch"];

const nullableText = z.string().nullable();

/** GET /members/{id} (MemberDetailOut): los cinco sensibles llegan enmascarados (N-01). */
export const memberDetailViewSchema = z.object({
  id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  sex: z.enum(SEXES).nullable(),
  status: z.enum(["active", "inactive"]),
  document_type: z.enum(DOCUMENT_TYPES),
  document: nullableText,
  phone: nullableText,
  email: nullableText,
  birth_date: nullableText,
  emergency_contact: nullableText,
  data_consent_at: nullableText,
  data_consent_version: nullableText,
  deleted_at: nullableText,
  membership_status: nullableText.optional().default(null),
  plan_name: nullableText.optional().default(null),
  membership_end_date: nullableText.optional().default(null),
  created_at: z.string(),
  updated_at: z.string(),
  warnings: z.array(z.string()),
});
export type MemberDetailView = z.infer<typeof memberDetailViewSchema>;

const revealedContactSchema = z.object({ name: z.string(), phone: z.string(), relationship: nullableText.optional() }).strict();
export type RevealedContact = z.infer<typeof revealedContactSchema>;

/** POST /members/{id}/reveal (RevealOut): un solo campo en claro, con el tipo que le corresponde. */
export const revealOutSchema = z
  .object({ field: z.enum(REVEAL_FIELDS), value: z.union([z.string(), revealedContactSchema, z.null()]) })
  .strict()
  .refine((out) => out.value === null || (out.field === "emergency_contact") === (typeof out.value === "object"), { error: "El valor no corresponde al campo." });
export type RevealOutView = z.infer<typeof revealOutSchema>;
export type RevealedValue = RevealOutView["value"];

/** Lo que dice la pantalla de un campo sin valor (el mismo texto de MaskedValue). */
export const NO_VALUE_TEXT = "Sin dato";
const CONTACT_SEPARATOR = " · ";

/** El valor revelado como texto de pantalla: el contacto como "Nombre · Parentesco · Teléfono". */
export function flattenRevealed(field: RevealField, value: RevealedValue): string {
  if (value === null) return NO_VALUE_TEXT;
  if (typeof value === "object") return [value.name, value.relationship ?? "", value.phone].filter((part) => part !== "").join(CONTACT_SEPARATOR);
  return field === "birth_date" ? formatDate(value) : value;
}

/** Los campos sensibles de la edición: los mismos cinco que se revelan. */
export const SENSITIVE_EDIT_FIELDS = REVEAL_FIELDS;
export type SensitiveEditField = RevealField;
/** "keep": no viaja; "change": viaja el valor nuevo; "remove": viaja `null` (no el documento). */
export type SensitiveEditMode = "keep" | "change" | "remove";
/** Los que se pueden quitar (`null` en MemberPatch); el documento no (PATCH_NOT_NULL). */
export const REMOVABLE_FIELDS: readonly SensitiveEditField[] = ["phone", "email", "birth_date", "emergency_contact"];

export interface MemberEditValues {
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
  modes: Record<SensitiveEditField, SensitiveEditMode>;
}

export type MemberEditDirtyFields = Partial<Readonly<FieldNamesMarkedBoolean<MemberEditValues>>>;

export const EDIT_MESSAGES = {
  documentChange: "Escribe el nuevo número de documento o cancela el cambio.",
  birthDateChange: "Escribe la nueva fecha de nacimiento o cancela el cambio.",
  phoneChange: "Escribe el nuevo teléfono o cancela el cambio.",
  emailChange: "Escribe el nuevo correo o cancela el cambio.",
} as const;

const KEEP_ALL: Readonly<Record<SensitiveEditField, SensitiveEditMode>> = Object.freeze({
  document: "keep",
  phone: "keep",
  email: "keep",
  birth_date: "keep",
  emergency_contact: "keep",
});

/** Valores iniciales: lo no sensible de la ficha; lo sensible vacío y sin cambio (nunca el claro). */
export function editDefaults(member: MemberDetailView): MemberEditValues {
  return {
    first_name: member.first_name,
    last_name: member.last_name,
    sex: member.sex ?? "",
    document_type: member.document_type,
    document: "",
    birth_date: "",
    phone: "",
    email: "",
    emergency_contact: { name: "", phone: "", relationship: "" },
    data_consent: false,
    modes: { ...KEEP_ALL },
  };
}

type IssueAdder = (path: (string | number)[], message: string) => void;

/** Reglas del alta sobre un sensible en "change" (el valor ya viene recortado). */
function checkChangedField(field: SensitiveEditField, values: MemberEditValues, today: string, add: IssueAdder): void {
  const value = field === "emergency_contact" ? "" : values[field].trim();
  if (field === "document") {
    if (value === "") add(["document"], EDIT_MESSAGES.documentChange);
    else if (value.length < MEMBER_LIMITS.documentMin || value.length > MEMBER_LIMITS.documentMax) add(["document"], MEMBER_MESSAGES.documentLength);
  } else if (field === "birth_date") {
    if (value === "") add(["birth_date"], EDIT_MESSAGES.birthDateChange);
    else if (!isCalendarDate(value)) add(["birth_date"], MEMBER_MESSAGES.birthDateInvalid);
    else if (value > today) add(["birth_date"], MEMBER_MESSAGES.birthDateFuture);
  } else if (field === "phone") {
    if (value === "") add(["phone"], EDIT_MESSAGES.phoneChange);
    else if (value.length > MEMBER_LIMITS.phoneMax) add(["phone"], MEMBER_MESSAGES.phoneTooLong);
    else if (value.replace(NON_DIGITS, "").length < MEMBER_LIMITS.phoneMinDigits) add(["phone"], MEMBER_MESSAGES.phoneDigits);
  } else if (field === "email") {
    if (value === "") add(["email"], EDIT_MESSAGES.emailChange);
    else if (value.length > MEMBER_LIMITS.emailMax) add(["email"], MEMBER_MESSAGES.emailTooLong);
    else if (!EMAIL_SHAPE.test(value)) add(["email"], MEMBER_MESSAGES.emailInvalid);
  } else {
    const contact = values.emergency_contact;
    if (contact.name.trim() === "") add(["emergency_contact", "name"], MEMBER_MESSAGES.contactNameRequired);
    else if (contact.name.trim().length > MEMBER_LIMITS.name) add(["emergency_contact", "name"], MEMBER_MESSAGES.firstNameTooLong);
    if (contact.phone.trim() === "") add(["emergency_contact", "phone"], MEMBER_MESSAGES.contactPhoneRequired);
    else if (contact.phone.trim().length > MEMBER_LIMITS.phoneMax) add(["emergency_contact", "phone"], MEMBER_MESSAGES.phoneTooLong);
    if (contact.relationship.trim().length > MEMBER_LIMITS.relationshipMax) add(["emergency_contact", "relationship"], MEMBER_MESSAGES.relationshipTooLong);
  }
}

/**
 * Reglas de la edición; `today` (AAAA-MM-DD, Bogotá) se inyecta en las pruebas. Los nombres siguen
 * obligatorios; un sensible solo se valida si está en "change", con las reglas del alta.
 */
export function memberEditSchema(today: string = todayBogota()): z.ZodType<MemberEditValues, MemberEditValues> {
  const mode = z.enum(["keep", "change", "remove"]);
  return z
    .object({
      first_name: requiredName(MEMBER_MESSAGES.firstNameRequired, MEMBER_MESSAGES.firstNameTooLong),
      last_name: requiredName(MEMBER_MESSAGES.lastNameRequired, MEMBER_MESSAGES.lastNameTooLong),
      sex: z.union([z.literal(""), z.enum(SEXES)], { error: MEMBER_MESSAGES.sex }),
      document_type: z.enum(DOCUMENT_TYPES, { error: MEMBER_MESSAGES.documentType }),
      document: z.string(),
      birth_date: z.string(),
      phone: z.string(),
      email: z.string(),
      emergency_contact: z.object({ name: z.string(), phone: z.string(), relationship: z.string() }),
      data_consent: z.boolean(),
      modes: z.object({ document: mode, phone: mode, email: mode, birth_date: mode, emergency_contact: mode }),
    })
    .superRefine((values, ctx) => {
      const add: IssueAdder = (path, message) => {
        ctx.addIssue({ code: CUSTOM_ISSUE, path, message });
      };
      for (const field of SENSITIVE_EDIT_FIELDS) if (values.modes[field] === "change") checkChangedField(field, values, today, add);
    });
}

type TextSensitiveField = Exclude<SensitiveEditField, "emergency_contact">;

/** El valor de un sensible de texto en el cuerpo: el nuevo, `null` al quitarlo, o undefined si no viaja. */
function textPatch(field: TextSensitiveField, values: MemberEditValues): string | null | undefined {
  const mode = values.modes[field];
  if (mode === "remove") return REMOVABLE_FIELDS.includes(field) ? null : undefined;
  return mode === "change" ? values[field].trim() : undefined;
}

/** El contacto de emergencia en el cuerpo: el nuevo (parentesco solo si se escribió), `null` o undefined. */
function contactPatch(values: MemberEditValues): MemberPatchBody["emergency_contact"] | undefined {
  const mode = values.modes.emergency_contact;
  if (mode === "remove") return null;
  if (mode !== "change") return undefined;
  const { name, phone, relationship } = values.emergency_contact;
  const kin = relationship.trim();
  return { name: name.trim(), phone: phone.trim(), ...(kin ? { relationship: kin } : {}) };
}

/** Cuerpo de PATCH /members/{id} con solo lo modificado (S3-D46). */
export function toMemberPatch(values: MemberEditValues, dirtyFields: MemberEditDirtyFields): MemberPatchBody {
  const document = textPatch("document", values);
  const birthDate = textPatch("birth_date", values);
  const phone = textPatch("phone", values);
  const email = textPatch("email", values);
  const contact = contactPatch(values);
  return {
    ...(dirtyFields.first_name ? { first_name: values.first_name.trim() } : {}),
    ...(dirtyFields.last_name ? { last_name: values.last_name.trim() } : {}),
    ...(dirtyFields.sex ? { sex: values.sex === "" ? null : values.sex } : {}),
    ...(dirtyFields.document_type ? { document_type: values.document_type } : {}),
    ...(document === undefined ? {} : { document }),
    ...(birthDate === undefined ? {} : { birth_date: birthDate }),
    ...(phone === undefined ? {} : { phone }),
    ...(email === undefined ? {} : { email }),
    ...(contact === undefined ? {} : { emergency_contact: contact }),
    ...(dirtyFields.data_consent && values.data_consent ? { data_consent: true } : {}),
  };
}

// ---------------------------------------------------------------------------------------------
// S4A-F2 · US-106 (front): una entrada de GET /members/{id}/audit (MemberHistoryItem de S4A-B5).
// Estricto: una entrada con `before`, `after`, `user_email` o cualquier valor es una respuesta
// inválida y no se pinta (S4A-D20, S4A-D54). `fields` son solo nombres de campo (sin `reference` ni
// `void_reason`, S4A-D109) y `purpose` es `notify`, `auth_link` o null (S4A-D50).
export const HISTORY_ACTIONS = ["insert", "update", "delete", "reveal", "export", "download", "login", "verify"] as const satisfies readonly components["schemas"]["MemberHistoryItem"]["action"][];
export const HISTORY_PURPOSES = ["notify", "auth_link"] as const;

export const memberHistoryItemSchema = z
  .object({
    seq: z.number().int().positive(),
    at: z.string().min(1),
    user_id: z.string().min(1),
    user_name: z.string().nullable(),
    action: z.enum(HISTORY_ACTIONS),
    table_name: z.string().min(1),
    record_id: z.string().nullable(),
    fields: z.array(z.string()),
    purpose: z.enum(HISTORY_PURPOSES).nullable(),
  })
  .strict();
export type MemberHistoryItemView = z.infer<typeof memberHistoryItemSchema>;
export const memberHistoryPageSchema = pageSchema(memberHistoryItemSchema);
