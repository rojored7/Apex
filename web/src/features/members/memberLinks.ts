// S2-F6: rutas de socios y el aviso que el alta deja a la lista (S2-D34).
// - memberHref: /socios/{id}. La ficha llega con US-073 (S3-F1); hasta entonces da NotFound. Nunca
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
