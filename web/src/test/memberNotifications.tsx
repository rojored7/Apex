// S5-F3: datos de prueba de la pestaña Avisos de la ficha y de las preferencias de canal. Imitan
// ChannelsOut (GET y PATCH /members/{id}/channels, B5) y NotificationOut (GET /members/{id}/notifications, B7).
import { apiError, HISTORY_ROWS, pageOf, RULE_IDS, RULE_ROWS } from "./notificationAdmin";
import { MEMBER_ID } from "./memberDetail";

export { MEMBER_ID };

export const CHANNELS_PATH = `/members/${MEMBER_ID}/channels`;
export const MEMBER_NOTIFICATIONS_PATH = `/members/${MEMBER_ID}/notifications`;

export interface ChannelsFixture {
  member_id: string;
  channels: { channel: "email" | "whatsapp_link"; active: boolean }[];
  effective: string[];
  has_consent: boolean;
}

/** Un socio con consentimiento y sin preferencias explícitas: efectivo solo WhatsApp (S5-D31). */
export function channelsOut(overrides: Partial<ChannelsFixture> = {}): ChannelsFixture {
  return { member_id: MEMBER_ID, channels: [], effective: ["whatsapp_link"], has_consent: true, ...overrides };
}

/** Los avisos del socio: las filas del historial, todas de este socio. */
export const MEMBER_ROWS = HISTORY_ROWS.map((row) => ({ ...row, member_id: MEMBER_ID, member_name: "Laura Gómez" }));

export { apiError, pageOf, RULE_IDS };
export { RULE_ROWS };
