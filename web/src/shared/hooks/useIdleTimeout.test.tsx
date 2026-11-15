// S7-F4b (LOW b): el cierre por inactividad se mide con el reloj, no solo con un temporizador; un navegador que duerme la pestaña
// (tablet en reposo) no lo congela: al volver a verse, si el instante límite ya pasó, cierra.
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useIdleTimeout } from "./useIdleTimeout";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function setVisibility(state: "visible" | "hidden"): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useIdleTimeout", () => {
  it("dispara al pasar el tiempo sin actividad y un gesto reinicia la cuenta", () => {
    vi.useFakeTimers();
    const onIdle = vi.fn();
    renderHook(() => { useIdleTimeout(1000, onIdle, true); });
    vi.advanceTimersByTime(900);
    document.dispatchEvent(new Event("pointerdown"));
    vi.advanceTimersByTime(900);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(200);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it("si el temporizador no corrió (pestaña dormida) y al volver ya pasó el límite, dispara", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const onIdle = vi.fn();
    renderHook(() => { useIdleTimeout(10 * 60_000, onIdle, true); });
    vi.setSystemTime(Date.now() + 11 * 60_000);
    setVisibility("hidden");
    expect(onIdle).not.toHaveBeenCalled();
    setVisibility("visible");
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it("al volver antes del límite no dispara", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const onIdle = vi.fn();
    renderHook(() => { useIdleTimeout(10 * 60_000, onIdle, true); });
    vi.setSystemTime(Date.now() + 60_000);
    setVisibility("visible");
    expect(onIdle).not.toHaveBeenCalled();
  });

  it("deshabilitado no escucha nada", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const onIdle = vi.fn();
    renderHook(() => { useIdleTimeout(1000, onIdle, false); });
    vi.setSystemTime(Date.now() + 5000);
    setVisibility("visible");
    expect(onIdle).not.toHaveBeenCalled();
  });
});
