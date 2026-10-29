// S4A-F2 · US-106 (front), S4A-D32: la frase de una entrada del historial del socio, con el nombre de
// quien actuó y sin valores: "ana editó teléfono y correo", "juan mostró el documento", "ana vendió
// una membresía", "juan registró un pago", "ana anuló un pago". GET /members/{id}/audit solo trae
// nombres de campo (`fields`, sin `reference` ni `void_reason`, S4A-D109) y nunca valores.
// - Quien actuó: "Sistema" para el usuario técnico (N-15) aunque `user_name` diga otra cosa; sin
//   nombre, "Usuario" (actorLabel de shared/lib/audit-labels.ts).
// - El job de vencimientos (S4A-B2) solo cambia `status` de la membresía y el historial no trae el
//   valor nuevo: la frase dice "como vencida o por vencer" (puede ser cualquiera de los dos).
// - Una tabla o acción sin frase propia da "<quien> <acción> (<entidad>)" sin lanzar.
import { actionLabel, actorLabel, entityLabel, fieldNameLabel, SYSTEM_USER_ID } from "../../../shared/lib/audit-labels";
import type { MemberHistoryItemView } from "../schemas";

const MEMBERS_TABLE = "members.members";
const MEMBERSHIPS_TABLE = "memberships.memberships";
const PAYMENTS_TABLE = "payments.payments";

/** El campo revelado con su artículo (los cinco cifrados de v0.1). */
const REVEALED_FIELDS: Readonly<Record<string, string>> = Object.freeze({
  document: "el documento",
  phone: "el teléfono",
  email: "el correo",
  birth_date: "la fecha de nacimiento",
  emergency_contact: "el contacto de emergencia",
});

const CANCEL_FIELDS: readonly string[] = ["cancel_reason", "cancelled_at", "cancelled_by"];
const VOID_FIELD = "voided";
const STATUS_FIELD = "status";

/** "a", "a y b", "a, b y c". */
export function joinWords(words: readonly string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  return `${words.slice(0, -1).join(", ")} y ${words.at(-1) ?? ""}`;
}

/** Los nombres de los campos en minúscula, como van dentro de una frase. */
function fieldWords(fields: readonly string[]): string {
  return joinWords(fields.map((field) => fieldNameLabel(field).toLowerCase()));
}

function memberWhat(item: MemberHistoryItemView): string | null {
  switch (item.action) {
    case "insert":
      return "creó el socio";
    case "delete":
      return "eliminó al socio";
    case "update":
      return item.fields.length > 0 ? `editó ${fieldWords(item.fields)}` : "editó la ficha";
    default:
      return null;
  }
}

function membershipWhat(item: MemberHistoryItemView): string | null {
  if (item.action === "insert") return "vendió una membresía";
  if (item.action !== "update") return null;
  if (item.fields.some((field) => CANCEL_FIELDS.includes(field))) return "anuló una membresía";
  const onlyStatus = item.fields.length === 1 && item.fields[0] === STATUS_FIELD;
  if (onlyStatus && item.user_id === SYSTEM_USER_ID) return "marcó la membresía como vencida o por vencer";
  return item.fields.length > 0 ? `modificó una membresía: ${fieldWords(item.fields)}` : "modificó una membresía";
}

function paymentWhat(item: MemberHistoryItemView): string | null {
  if (item.action === "insert") return "registró un pago";
  if (item.action !== "update") return null;
  if (item.fields.includes(VOID_FIELD)) return "anuló un pago";
  return item.fields.length > 0 ? `modificó un pago: ${fieldWords(item.fields)}` : "modificó un pago";
}

function revealWhat(item: MemberHistoryItemView): string {
  const field = item.fields[0];
  return `mostró ${(field !== undefined ? REVEALED_FIELDS[field] : undefined) ?? "un dato"}`;
}

function what(item: MemberHistoryItemView): string {
  if (item.action === "reveal") return revealWhat(item);
  const byTable =
    item.table_name === MEMBERS_TABLE ? memberWhat(item) : item.table_name === MEMBERSHIPS_TABLE ? membershipWhat(item) : item.table_name === PAYMENTS_TABLE ? paymentWhat(item) : null;
  return byTable ?? `${actionLabel(item.action)} (${entityLabel(item.table_name)})`;
}

/** La frase de la entrada: quien actuó y qué hizo, sin valores. */
export function historyPhrase(item: MemberHistoryItemView): string {
  return `${actorLabel({ actor_id: item.user_id, actor_name: item.user_name })} ${what(item)}`;
}
