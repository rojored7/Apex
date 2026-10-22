// S2-F3: dobles de BroadcastChannel y de navigator.locks para simular varias pestañas en
// una misma prueba (cada "pestaña" es una instancia nueva de core/auth/session.ts, cargada
// con vi.resetModules()).
// - FakeBroadcastChannel entrega cada mensaje a las demás instancias con el mismo nombre en
//   una microtarea (como el navegador: nunca a quien lo envía y nunca en el mismo tick) y
//   guarda todo lo publicado en `posted`.
// - FakeLockManager serializa las peticiones con el mismo nombre (el modo exclusivo de Web
//   Locks), en orden de llegada.

export interface PostedMessage {
  channel: string;
  data: unknown;
}

type Listener = (event: MessageEvent) => void;

const registry = new Map<string, Set<FakeBroadcastChannel>>();
export const posted: PostedMessage[] = [];

export class FakeBroadcastChannel {
  readonly name: string;
  onmessage: Listener | null = null;
  private readonly listeners = new Set<Listener>();
  private closed = false;

  constructor(name: string) {
    this.name = name;
    const peers = registry.get(name) ?? new Set<FakeBroadcastChannel>();
    peers.add(this);
    registry.set(name, peers);
  }

  postMessage(data: unknown): void {
    if (this.closed) throw new Error("canal cerrado");
    const copy: unknown = structuredClone(data);
    posted.push({ channel: this.name, data: copy });
    for (const peer of registry.get(this.name) ?? []) {
      if (peer !== this) queueMicrotask(() => {
        peer.deliver(copy);
      });
    }
  }

  addEventListener(type: string, listener: Listener): void {
    if (type === "message") this.listeners.add(listener);
  }

  removeEventListener(type: string, listener: Listener): void {
    if (type === "message") this.listeners.delete(listener);
  }

  close(): void {
    this.closed = true;
    registry.get(this.name)?.delete(this);
  }

  /** Solo pruebas: entrega un mensaje como si llegara de otra pestaña. */
  deliver(data: unknown): void {
    if (this.closed) return;
    const event = new MessageEvent("message", { data });
    this.onmessage?.(event);
    for (const listener of this.listeners) listener(event);
  }
}

/** Instancias abiertas con ese nombre (para entregar mensajes a mano). */
export function openChannels(name: string): FakeBroadcastChannel[] {
  return [...(registry.get(name) ?? [])];
}

export class FakeLockManager {
  readonly requested: string[] = [];
  private readonly tails = new Map<string, Promise<unknown>>();

  request<T>(name: string, callback: () => Promise<T> | T): Promise<T> {
    this.requested.push(name);
    const previous = this.tails.get(name) ?? Promise.resolve();
    const run = previous.then(
      () => callback(),
      () => callback(),
    );
    this.tails.set(
      name,
      run.catch(() => undefined),
    );
    return run;
  }
}

/** Instala los dos dobles; devuelve el gestor de candados (o ninguno con `locks: false`). */
export function installTabDoubles({ locks = true }: { locks?: boolean } = {}): FakeLockManager | null {
  vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
  const manager = locks ? new FakeLockManager() : null;
  Object.defineProperty(navigator, "locks", { value: manager ?? undefined, configurable: true });
  return manager;
}

export function resetTabDoubles(): void {
  for (const peers of registry.values()) for (const peer of peers) peer.close();
  registry.clear();
  posted.length = 0;
  Reflect.deleteProperty(navigator, "locks");
}
