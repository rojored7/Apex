// S2-F6: rutas de socios y el aviso que el alta deja a la lista (S2-D34).
// - memberHref: /socios/{id}, la ficha (US-073, S3-F1). Nunca
//   se enlaza a /socios?q=<documento>: el documento quedaría en la URL, el historial y los logs.
// - El aviso viaja en el estado de la navegación (nunca en la URL ni en localStorage) y solo con
//   el nombre, que va en claro en el leaderboard; la lista lo valida antes de mostrarlo.
import { z } from "zod";

export const MEMBERS_PATH = "/socios";
export const NEW_MEMBER_PATH = "/socios/nuevo";

export function memberHref(id: string): string {
  return `${MEMBERS_PATH}/${encodeURIComponent(id)}`;
}

export interface MemberCreatedNotice {
  name: string;
  consentMissing: boolean;
}

export interface MemberCreatedState {
  memberCreated: MemberCreatedNotice;
}

const createdStateSchema = z.object({
  memberCreated: z.object({ name: z.string().min(1), consentMissing: z.boolean() }),
});

/** El aviso del alta si el estado de la navegación lo trae bien formado; si no, null. */
export function readCreatedNotice(state: unknown): MemberCreatedNotice | null {
  const parsed = createdStateSchema.safeParse(state);
  return parsed.success ? parsed.data.memberCreated : null;
}

// S3-F1: la edición, la venta desde la ficha y el aviso que la edición deja a la ficha.
// - sellHref: /membresias/vender?socio=<id>; solo el id viaja en la URL (nunca un dato cifrado).
//   SELL_PATH se repite aquí y en features/memberships (S3-D65: ninguna feature importa de otra).
// - El aviso "Cambios guardados" viaja en el estado de la navegación, validado con Zod.
export function editMemberHref(id: string): string {
  return `${memberHref(id)}/editar`;
}

export const SELL_PATH = "/membresias/vender";

export function sellHref(id: string): string {
  return `${SELL_PATH}?${new URLSearchParams({ socio: id }).toString()}`;
}

export interface MemberUpdatedState {
  memberUpdated: true;
}

const updatedStateSchema = z.object({ memberUpdated: z.literal(true) });

/** ¿La navegación viene de guardar la edición? */
export function readUpdatedNotice(state: unknown): boolean {
  return updatedStateSchema.safeParse(state).success;
}

// Revisión S3-F1 (LOW-3): el `:id` de la ruta solo viaja al api si tiene forma de UUID; si no, la
// pantalla dice "Socio no encontrado" sin pedir nada.
const MEMBER_ID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isMemberId(id: string): boolean {
  return MEMBER_ID_SHAPE.test(id);
}
