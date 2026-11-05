// S5-F3 · US-123 y US-130 (front): datos de la pestaña Avisos de la ficha del socio (contrato de B5 y B7).
// - useMemberChannels(id): GET /members/{id}/channels con la clave ["member-channels", id].
// - useSetMemberChannel(id): PATCH /members/{id}/channels con un solo canal ({items: [{channel, active}]});
//   al salir bien deja la respuesta en la caché de esa clave. Un 404 o un 409 relee (el socio cambió).
// - useMemberNotifications(id, params): GET /members/{id}/notifications con la clave
//   ["notifications", "member", id, params] (cuelga de ["notifications"], que invalidan abrir WhatsApp y omitir).
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { refreshIfStale } from "./api";
import { channelsOutSchema, type ChannelChange, type ChannelsOutView } from "./memberSchemas";
import { notificationsPageSchema, type NotificationRowView } from "./schemas";

export const memberChannelsKey = (id: string) => ["member-channels", id] as const;
export const memberNotificationsKey = (id: string, params: { limit: number; offset: number }) => ["notifications", "member", id, params] as const;

const memberPath = (id: string): string => `/members/${encodeURIComponent(id)}`;

export function useMemberChannels(id: string): UseQueryResult<ChannelsOutView> {
  return useQuery({
    queryKey: memberChannelsKey(id),
    queryFn: async ({ signal }) => parseResponse(channelsOutSchema, await api.get<unknown>(`${memberPath(id)}/channels`, { signal })),
    refetchOnWindowFocus: false,
  });
}

export function useSetMemberChannel(id: string): UseMutationResult<ChannelsOutView, Error, ChannelChange> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<ChannelsOutView, Error, ChannelChange>({
    mutationFn: async (change) => parseResponse(channelsOutSchema, await api.patch<unknown>(`${memberPath(id)}/channels`, { body: { items: [change] } })),
    onSuccess: (saved) => {
      queryClient.setQueryData(memberChannelsKey(id), saved);
    },
    onError: refreshIfStale(() => {
      void queryClient.invalidateQueries({ queryKey: memberChannelsKey(id) });
    }),
  });
}

export function useMemberNotifications(id: string, params: { limit: number; offset: number }): UseQueryResult<Page<NotificationRowView>> {
  return useQuery({
    queryKey: memberNotificationsKey(id, params),
    queryFn: async ({ signal }) =>
      parseResponse(notificationsPageSchema, await api.get<unknown>(`${memberPath(id)}/notifications`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}
