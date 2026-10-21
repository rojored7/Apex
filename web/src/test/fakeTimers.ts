// Temporizadores falsos que funcionan con Testing Library en Vitest.
// El asyncWrapper de @testing-library/react espera un setTimeout(0) y solo lo adelanta si
// detecta los temporizadores falsos de Jest (global `jest`); sin este puente, user-event y
// findBy* se quedan colgados con vi.useFakeTimers(). Solo se falsean setTimeout y
// clearTimeout: el planificador de React sigue con setImmediate real.
import userEvent from "@testing-library/user-event";

export function useRtlFakeTimers(): void {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  vi.stubGlobal("jest", {
    advanceTimersByTime: (ms: number) => {
      vi.advanceTimersByTime(ms);
    },
  });
}

export function restoreRtlTimers(): void {
  vi.useRealTimers();
  vi.unstubAllGlobals();
}

/** user-event que adelanta los temporizadores falsos en cada pausa. */
export function fakeTimersUser(): ReturnType<typeof userEvent.setup> {
  return userEvent.setup({
    advanceTimers: (ms) => {
      vi.advanceTimersByTime(ms);
    },
  });
}
