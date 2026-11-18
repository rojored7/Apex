// S9-F1 (revisión, L6, L7, seguridad L1 y L2): un dato en claro que vive poco. Temporizador de 60 s con `expiresAt`, y se enmascara
// al ocultar la pestaña, al salir de la página (pagehide, de forma síncrona), al volver de la caché de páginas (pageshow persistido) y
// al volver de una suspensión del equipo con el plazo vencido (visibilitychange a visible, pageshow o focus).
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { REVEAL_TTL_MS, useTimedReveal } from "./useTimedReveal";

function Harness({ onExpire }: { onExpire: () => void }) {
  const [shown, setShown] = useState(false);
  const { arm, disarm } = useTimedReveal(shown, () => {
    onExpire();
    setShown(false);
  });
  return (
    <div>
      <output aria-label="estado">{shown ? "claro" : "oculto"}</output>
      <button
        type="button"
        onClick={() => {
          setShown(true);
          arm();
        }}
      >
        mostrar
      </button>
      <button
        type="button"
        onClick={() => {
          disarm();
          setShown(false);
        }}
      >
        ocultar
      </button>
    </div>
  );
}

const state = (): string => screen.getByLabelText("estado").textContent;
const click = (name: string): void => {
  act(() => {
    screen.getByRole("button", { name }).click();
  });
};
const fire = (target: Document | Window, event: Event): void => {
  act(() => {
    target.dispatchEvent(event);
  });
};
const pageEvent = (type: "pageshow" | "pagehide", persisted: boolean): Event => Object.assign(new Event(type), { persisted });

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useTimedReveal · plazo", () => {
  it("enmascara a los 60 s, ni un milisegundo antes", () => {
    const onExpire = vi.fn();
    render(<Harness onExpire={onExpire} />);
    click("mostrar");

    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS - 1);
    });
    expect(state()).toBe("claro");
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(state()).toBe("oculto");
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("disarm cancela el plazo: no vuelve a llamar a onExpire", () => {
    const onExpire = vi.fn();
    render(<Harness onExpire={onExpire} />);
    click("mostrar");
    click("ocultar");

    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS * 2);
    });

    expect(onExpire).not.toHaveBeenCalled();
  });
});

describe("useTimedReveal · la pestaña y la página", () => {
  it("visibilitychange a hidden enmascara al instante; a visible con plazo vigente no", () => {
    render(<Harness onExpire={vi.fn()} />);
    click("mostrar");
    const visibility = vi.spyOn(document, "visibilityState", "get");

    visibility.mockReturnValue("visible");
    fire(document, new Event("visibilitychange"));
    expect(state()).toBe("claro");
    visibility.mockReturnValue("hidden");
    fire(document, new Event("visibilitychange"));

    expect(state()).toBe("oculto");
  });

  it("pagehide enmascara de forma síncrona (flushSync), sin esperar a que React reparta el render", () => {
    render(<Harness onExpire={vi.fn()} />);
    click("mostrar");

    window.dispatchEvent(new Event("pagehide"));

    expect(state()).toBe("oculto");
  });

  it("pageshow persistido (página que vuelve de la caché) enmascara aunque el plazo siga vigente", () => {
    render(<Harness onExpire={vi.fn()} />);
    click("mostrar");

    fire(window, pageEvent("pageshow", false));
    expect(state()).toBe("claro");
    fire(window, pageEvent("pageshow", true));

    expect(state()).toBe("oculto");
  });
});

describe("useTimedReveal · suspensión del equipo (expiresAt)", () => {
  /** El reloj de pared avanza, pero el temporizador del navegador no disparó (el equipo estaba dormido). */
  function sleepPastTtl(): void {
    vi.setSystemTime(Date.now() + REVEAL_TTL_MS + 1);
  }

  it.each([
    ["visibilitychange a visible", (): void => { fire(document, new Event("visibilitychange")); }],
    ["pageshow sin caché", (): void => { fire(window, pageEvent("pageshow", false)); }],
    ["focus", (): void => { fire(window, new Event("focus")); }],
  ])("al volver con %s y el plazo vencido, enmascara", (_name, wake) => {
    const onExpire = vi.fn();
    render(<Harness onExpire={onExpire} />);
    click("mostrar");
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");

    sleepPastTtl();
    wake();

    expect(state()).toBe("oculto");
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("al volver con el plazo vigente no enmascara", () => {
    render(<Harness onExpire={vi.fn()} />);
    click("mostrar");
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");

    vi.setSystemTime(Date.now() + REVEAL_TTL_MS - 1_000);
    fire(window, new Event("focus"));
    fire(document, new Event("visibilitychange"));

    expect(state()).toBe("claro");
  });
});
