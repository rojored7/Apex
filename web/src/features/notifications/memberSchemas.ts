// S5-F3 · US-123 (front): preferencias de canal de aviso de un socio (ChannelsOut y ChannelsPatch de B5).
// - channelsOutSchema: las preferencias explícitas, los canales efectivos y si el socio autorizó el uso de
//   sus datos; estricto (un campo de más es una respuesta inválida).
// - channelEnabled: lo que se ve en cada interruptor. El correo es opt-in (activo solo con una fila
//   explícita activa); WhatsApp manual rige salvo una fila explícita inactiva (S5-D31).
import { z } from "zod";
import { NOTIFICATION_CHANNELS } from "./schemas";

export const channelsOutSchema = z
  .object({
    member_id: z.string().min(1),
    channels: z.array(z.object({ channel: z.enum(NOTIFICATION_CHANNELS), active: z.boolean() }).strict()),
    effective: z.array(z.string()),
    has_consent: z.boolean(),
  })
  .strict();
export type ChannelsOutView = z.infer<typeof channelsOutSchema>;

export type MemberChannel = (typeof NOTIFICATION_CHANNELS)[number];

export interface ChannelChange {
  channel: MemberChannel;
  active: boolean;
}

export function channelEnabled(data: ChannelsOutView, channel: MemberChannel): boolean {
  const explicit = data.channels.find((item) => item.channel === channel);
  return channel === "email" ? explicit?.active === true : explicit?.active !== false;
}
