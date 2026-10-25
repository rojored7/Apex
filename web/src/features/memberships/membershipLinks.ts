// S3-F3 · enlaces de membresías y lectura de la URL de la venta.
// - /membresias/vender: vender. `?socio=<id>` fija el socio; con `&renovar=1` renueva (US-088,
//   Q1). Un `socio` que no es un UUID se ignora (vuelve a la venta normal con buscador).
// - El nombre del socio viaja en el estado de la navegación (validado con Zod) para no pedirlo de
//   nuevo; sin él la pantalla dice "Socio elegido" hasta que exista GET /members/{id} (B9, S3-F1).
// - memberHref: la ficha del socio (/socios/:id, US-073; F1). Se define aquí y no se importa de
//   features/members (S3-D65: ninguna feature importa de otra).
import { z } from "zod";

export const SELL_PATH = "/membresias/vender";
export const MEMBERS_PATH = "/socios";
export const NEW_MEMBER_PATH = "/socios/nuevo";
export const PLANS_PATH = "/planes";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function memberHref(memberId: string): string {
  return `${MEMBERS_PATH}/${encodeURIComponent(memberId)}`;
}

/** /membresias/vender?socio=<id>&renovar=1 */
export function renewHref(memberId: string): string {
  return `${SELL_PATH}?${new URLSearchParams({ socio: memberId, renovar: "1" }).toString()}`;
}

export interface SellParams {
  /** El socio fijado por la URL, o null. */
  memberId: string | null;
  /** Renovar: solo con un socio fijo. */
  renew: boolean;
}

export function readSellParams(search: string): SellParams {
  const params = new URLSearchParams(search);
  const socio = params.get("socio");
  const memberId = socio !== null && UUID.test(socio) ? socio : null;
  return { memberId, renew: memberId !== null && params.get("renovar") === "1" };
}

/** Estado de la navegación hacia la venta: el nombre del socio ya elegido. */
export const sellLocationStateSchema = z.object({ memberName: z.string().min(1).max(250) });
export type SellLocationState = z.infer<typeof sellLocationStateSchema>;

/** El nombre del socio del estado de la navegación, o null. */
export function memberNameFromState(state: unknown): string | null {
  const parsed = sellLocationStateSchema.safeParse(state);
  return parsed.success ? parsed.data.memberName : null;
}
