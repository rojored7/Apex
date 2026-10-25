// S3-F1 (S3-D65): la ficha que MemberDetailPage pasa a sus pestañas por el contexto del <Outlet />.
// La pestaña "Datos" (hija índice) la lee sin un segundo observador de GET /members/{id}. Las
// pestañas de otras features (S3-F7) no lo importan (ninguna feature importa de otra): piden lo suyo
// con el `:id` de la ruta.
import { useOutletContext } from "react-router";
import type { MemberDetailView } from "./schemas";

export interface MemberOutletContext {
  member: MemberDetailView;
}

/** La ficha del padre, o null si la pestaña se pinta sin él. */
export function useMemberOutlet(): MemberDetailView | null {
  const context = useOutletContext<MemberOutletContext | undefined>();
  return context?.member ?? null;
}
