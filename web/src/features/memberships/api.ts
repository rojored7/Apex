// S3-F3 · US-084, US-085 y US-088 (front): vender (con primer pago opcional) y renovar.
// - useSellMembership(memberId): POST /members/{id}/memberships → 201 SellMembershipOut. Vender y
//   renovar usan este mismo endpoint (regla 9 de CLAUDE.md, D5). El cuerpo lleva un monto y quizá
//   una referencia: `gcTime: 0` y `reset()` en `onSettled` (S3-D52, M-9), así la caché de
//   mutaciones no conserva `variables` después de responder. Al salir bien invalida membresías,
//   socios (estado en la lista), pagos y el resumen de membresías. Sin reintentos: una escritura
//   nunca se repite sola (el cliente tampoco reintenta un 503 `busy` en escrituras).
// - useRenewalPreview(memberId, planId): GET /members/{id}/memberships/renewal-preview?plan_id=
//   con la clave ["memberships", "renewal-preview", memberId, planId]; solo con socio y plan. Al
//   cambiar de plan se pide de nuevo.
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { renewalPreviewSchema, sellMembershipOutSchema, type RenewalPreviewView, type SellMembershipBody, type SellMembershipOutView } from "./schemas";

/** Lo que una venta deja viejo (S3-D53: el resumen de membresías se relee). */
export const SELL_INVALIDATES = [["memberships"], ["members"], ["payments"], ["memberships-summary"]] as const;

export interface SellMembership {
  /** Vende con este cuerpo; rechaza con el ApiError del api. */
  sell: (body: SellMembershipBody) => Promise<SellMembershipOutView>;
  isPending: boolean;
}

const membershipsOf = (memberId: string): string => `/members/${encodeURIComponent(memberId)}/memberships`;

export function renewalPreviewKey(memberId: string | null, planId: string | null): readonly ["memberships", "renewal-preview", string, string] {
  return ["memberships", "renewal-preview", memberId ?? "", planId ?? ""];
}

export function useSellMembership(memberId: string | null): SellMembership {
  const queryClient = useQueryClient();
  // reset() de la propia mutación, para llamarlo al terminar (onSettled). Se guarda en un efecto:
  // un ref no se escribe durante el render.
  const resetRef = useRef<() => void>(() => undefined);
  const mutation = useMutation<SellMembershipOutView, Error, SellMembershipBody>({
    mutationFn: async (body) => {
      if (memberId === null) throw new Error("useSellMembership: falta el socio");
      return parseResponse(sellMembershipOutSchema, await api.post<unknown>(membershipsOf(memberId), { body }));
    },
    gcTime: 0,
    onSuccess: () => {
      // Sin esperar las relecturas: la venta ya terminó.
      for (const queryKey of SELL_INVALIDATES) void queryClient.invalidateQueries({ queryKey });
    },
    onSettled: () => {
      resetRef.current();
    },
  });
  const { reset, mutateAsync, isPending } = mutation;
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  return { sell: mutateAsync, isPending };
}

export function useRenewalPreview(memberId: string | null, planId: string | null): UseQueryResult<RenewalPreviewView> {
  return useQuery({
    queryKey: renewalPreviewKey(memberId, planId),
    queryFn: async ({ signal }) =>
      parseResponse(renewalPreviewSchema, await api.get<unknown>(`${membershipsOf(memberId ?? "")}/renewal-preview`, { query: { plan_id: planId ?? "" }, signal })),
    enabled: memberId !== null && planId !== null,
  });
}
