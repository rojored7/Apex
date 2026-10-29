// S2-F6: rutas de socios y el aviso que el alta deja a la lista (S2-D34).
// - memberHref: /socios/{id}, la ficha (US-073, S3-F1). Fase 4 del Sprint 3 (M4): las rutas y sus
//   enlaces viven en shared/lib/routes.ts y aquí se reexportan.
// - El aviso viaja en el estado de la navegación (nunca en la URL ni en localStorage) y solo con
//   el nombre, que va en claro en el leaderboard; la lista lo valida antes de mostrarlo.
import { z } from "zod";
import { isUuid } from "../../shared/lib/ids";
import { memberHref } from "../../shared/lib/routes";

export { MEMBERS_PATH, memberHref, NEW_MEMBER_PATH, SELL_PATH, sellHref } from "../../shared/lib/routes";

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
// - sellHref: /membresias/vender?socio=<id> (shared/lib/routes.ts); solo el id viaja en la URL.
// - El aviso "Cambios guardados" viaja en el estado de la navegación, validado con Zod.
export function editMemberHref(id: string): string {
  return `${memberHref(id)}/editar`;
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
export function isMemberId(id: string): boolean {
  return isUuid(id);
}

// S4A-F2 (US-106): la pestaña Historial de la ficha, hija /socios/:id/historial (S4A-D30).
export function memberHistoryHref(id: string): string {
  return `${memberHref(id)}/historial`;
}
