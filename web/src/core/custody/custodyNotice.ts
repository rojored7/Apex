// S5-F5 · US-136 (S5-D14): estado global del aviso "custodio de llaves no disponible".
// El cliente del api lo activa con un 503 `crypto_unavailable` (Retry-After: 30); el host
// (CustodyNoticeHost) lo muestra y lo retira al vencer la espera. Es un almacén mínimo
// externo a React (useSyncExternalStore): el cliente no importa componentes. Nunca guarda
// cuerpos de respuesta ni datos de la persona, solo la espera en segundos.
import { useSyncExternalStore } from "react";

/** Espera por defecto cuando el 503 no trae un Retry-After válido (S5-D14). */
export const CUSTODY_DEFAULT_RETRY_S = 30;
const CUSTODY_MIN_RETRY_S = 1;
/** Tope de la espera mostrada: un valor mayor no es un aviso "por ahora". */
const CUSTODY_MAX_RETRY_S = 300;

export interface CustodyNoticeState {
  /** Cambia en cada aviso: reinicia el temporizador del host aunque la espera sea igual. */
  readonly id: number;
  readonly retryAfterS: number;
}

let current: CustodyNoticeState | null = null;
let counter = 0;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => {
    listener();
  });
}

export function reportCustodyUnavailable(retryAfterS: number | undefined): void {
  const seconds = Math.min(Math.max(retryAfterS ?? CUSTODY_DEFAULT_RETRY_S, CUSTODY_MIN_RETRY_S), CUSTODY_MAX_RETRY_S);
  counter += 1;
  current = Object.freeze({ id: counter, retryAfterS: seconds });
  emit();
}

export function clearCustodyNotice(): void {
  if (current === null) return;
  current = null;
  emit();
}

export function getCustodyNotice(): CustodyNoticeState | null {
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useCustodyNotice(): CustodyNoticeState | null {
  return useSyncExternalStore(subscribe, getCustodyNotice, getCustodyNotice);
}
