// S2-F3 (US-043, blueprint 7.6, L-6): coordinación de la sesión entre pestañas.
// - Canal `apex-auth` (BroadcastChannel) con dos mensajes: `token` (access y vencimiento;
//   nunca el refresh, que solo vive en la cookie HttpOnly) y `logout`.
// - Cada mensaje lleva `seq`, un reloj de Lamport: al publicar es mayor que todo lo visto
//   (y que la hora actual, para ordenar pestañas que nunca hablaron); al recibir se adelanta.
//   Un `token` con secuencia no mayor que la última vista llega tarde y se descarta. Un
//   `logout` nunca se descarta: perder un cierre de sesión es peor que repetirlo.
// - Candado `apex-refresh` (Web Locks): un solo refresh a la vez entre pestañas. Sin
//   navigator.locks (decisión 23) la función corre directa y rigen la promesa única y el canal.
// - Todo mensaje se valida con Zod; lo que no tenga la forma se ignora.
import { z } from "zod";

export const AUTH_CHANNEL = "apex-auth";
export const REFRESH_LOCK = "apex-refresh";

const tokenMessageSchema = z
  .object({
    type: z.literal("token"),
    seq: z.number().int().nonnegative(),
    accessToken: z.string().min(1),
    expiresIn: z.number().int().positive(),
  })
  .strict();

const logoutMessageSchema = z.object({ type: z.literal("logout"), seq: z.number().int().nonnegative() }).strict();

const messageSchema = z.discriminatedUnion("type", [tokenMessageSchema, logoutMessageSchema]);

export type AuthMessage = z.infer<typeof messageSchema>;
export type OutgoingAuthMessage =
  | { type: "token"; accessToken: string; expiresIn: number }
  | { type: "logout" };

export interface TabSync {
  publish: (message: OutgoingAuthMessage) => void;
  close: () => void;
}

/** Abre el canal; sin BroadcastChannel (navegador viejo, pruebas sin doble) devuelve null. */
export function openTabSync(onMessage: (message: AuthMessage) => void): TabSync | null {
  if (typeof BroadcastChannel !== "function") return null;
  const channel = new BroadcastChannel(AUTH_CHANNEL);
  let clock = 0;
  let lastTokenSeq = 0;

  const listener = (event: MessageEvent): void => {
    const parsed = messageSchema.safeParse(event.data);
    if (!parsed.success) return;
    const message = parsed.data;
    clock = Math.max(clock, message.seq);
    if (message.type === "token") {
      if (message.seq <= lastTokenSeq) return;
      lastTokenSeq = message.seq;
    } else {
      lastTokenSeq = Math.max(lastTokenSeq, message.seq);
    }
    onMessage(message);
  };
  channel.addEventListener("message", listener);

  return {
    publish(message) {
      clock = Math.max(clock + 1, Date.now());
      lastTokenSeq = clock;
      channel.postMessage({ ...message, seq: clock });
    },
    close() {
      channel.removeEventListener("message", listener);
      channel.close();
    },
  };
}

/** navigator.locks si existe (los tipos del DOM lo dan por hecho; Safari < 15.4 y jsdom no lo tienen). */
function lockManager(): LockManager | undefined {
  if (typeof navigator === "undefined") return undefined;
  const maybe: { locks?: LockManager | undefined } = navigator;
  return maybe.locks;
}

/** ¿Hay Web Locks en este navegador? */
export function hasRefreshLock(): boolean {
  return lockManager() !== undefined;
}

/** Corre `task` con el candado `apex-refresh` (exclusivo entre pestañas) si existe. */
export function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = lockManager();
  if (!locks) return task();
  return locks.request(REFRESH_LOCK, task) as Promise<T>;
}
