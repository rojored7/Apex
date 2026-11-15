// S2-F2: contenedores que leen la sesión y entregan sus datos a los layouts presentacionales
// (PanelShell, PortalShell, TvShell) y el marco de las pantallas de acceso.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { resetThemeForTests } from "../core/theme/theme";
import { mockApi, testQueryClient } from "../test/server";
import { signInAs, signOutForTests } from "../test/session";
import { AccessLayout } from "./AccessLayout";
import { PanelShell } from "./PanelShell";
import { ENABLED_FEATURES, type Feature } from "../config/features";

// S3-F4 (E10): el host del panel de pagos se reemplaza por un marcador para saber si se descargó
// (la fábrica de vi.mock corre solo cuando alguien importa el módulo, es decir, con el import
// perezoso de PanelShell).
const paymentHost = vi.hoisted(() => ({ loaded: vi.fn() }));
vi.mock("../features/payments/components/RegisterPaymentPanelHost", () => {
  paymentHost.loaded();
  return { RegisterPaymentPanelHost: () => <p>Panel de pagos montado</p> };
});
import { GymShell, PortalShell, TvShell } from "./ZoneShells";
import { getSession } from "../core/auth";
import { KIOSK_MESSAGES } from "../core/auth/kiosk";
import { useGym } from "../shared/hooks/gymContext";

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});

function inRouter(element: ReactNode, path = "/") {
  const router = createMemoryRouter([{ element, children: [{ path: "*", element: <h1>Contenido</h1>, handle: { title: "Check-in" } }] }], {
    initialEntries: [path],
  });
  // S2-F4a: PanelShell monta el panel "Mi cuenta", que usa TanStack Query.
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, router };
}

describe("PanelShell", () => {
  it("lleva a la TopBar el correo, la etiqueta del rol y el gimnasio de la sesión", () => {
    signInAs("admin", { gymName: "Box Norte" });
    inRouter(<PanelShell />);

    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("admin@apex.test · Admin");
    expect(banner).toHaveTextContent("Box Norte");
    expect(within(screen.getByRole("main")).getByRole("heading", { name: "Contenido" })).toBeInTheDocument();
  });

  it("arma el menú con el rol de la sesión y las features del sprint", () => {
    signInAs("coach");
    inRouter(<PanelShell />);

    const nav = screen.getByRole("navigation", { name: "Menú principal" });
    expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Inicio", "Clases de hoy", "WOD de hoy", "Por avisar hoy", "Socios", "Membresías", "Pagos", "Clases", "WODs", "Movimientos", "Reglas y plantillas", "Historial de envíos"]);
  });

  it("lleva el conmutador de tema (US-068) y aplica el claro por defecto del panel", async () => {
    signInAs("admin");
    inRouter(<PanelShell />);

    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.setup().click(within(screen.getByRole("banner")).getByRole("button", { name: "Cambiar a tema oscuro" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    // L7 (revisión del Sprint 2): desmontar antes de reiniciar el tema (avisa a los suscriptores).
    cleanup();
    localStorage.clear();
    resetThemeForTests();
  });

  it("S2-F4a: 'Mi cuenta' del menú de usuario abre el panel con los datos y el cambio de contraseña", async () => {
    mockApi({
      "GET /auth/me": {
        status: 200,
        body: { id: "00000000-0000-4000-8000-000000000001", email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false },
      },
    });
    signInAs("admin");
    inRouter(<PanelShell />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /admin@apex\.test/ }));
    await user.click(within(screen.getByRole("menu", { name: "Menú de usuario" })).getByRole("menuitem", { name: "Mi cuenta" }));

    const panel = await screen.findByRole("dialog", { name: "Mi cuenta" });
    expect(await within(panel).findByText("Box Norte")).toBeInTheDocument();
    expect(within(panel).getByLabelText(/^Contraseña actual/)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog", { name: "Mi cuenta" })).not.toBeInTheDocument();
  });

  it("sin sesión pinta el marco sin usuario", () => {
    inRouter(<PanelShell />);

    expect(screen.getByRole("banner")).not.toHaveTextContent("@");
  });
});

describe("PortalShell, GymShell y TvShell", () => {
  it("PortalShell usa el gimnasio de la sesión", () => {
    signInAs("member", { gymName: "Box Sur" });
    inRouter(<PortalShell />, "/mi");

    expect(screen.getByRole("banner")).toHaveTextContent("Box Sur");
    expect(screen.getByRole("navigation", { name: "Menú del portal" })).toBeInTheDocument();
  });

  it("GymShell fuera del check-in toma el título del handle de la ruta y sale al panel", () => {
    signInAs("coach");
    inRouter(<GymShell />, "/clases/1/otra");

    expect(within(screen.getByRole("banner")).getByRole("heading", { level: 1, name: "Check-in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Salir" })).toHaveAttribute("href", "/");
  });

  const KIOSK_OUT = (kioskPath: string | null) => ({ status: 200, body: { access_token: "access-quiosco", token_type: "bearer", expires_in: 900, kiosk_path: kioskPath } });
  const CHECKIN = "/clases/1/checkin";

  it("GymShell en el check-in activa el quiosco en el servidor (POST /auth/kiosk), sin enlaces y con la salida «Clases»", async () => {
    signInAs("coach");
    const mock = mockApi({ "POST /auth/kiosk": KIOSK_OUT(CHECKIN) });
    inRouter(<GymShell />, CHECKIN);

    await waitFor(() => { expect(getSession().user?.kioskPath).toBe(CHECKIN); });
    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: CHECKIN });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Clases" })).toBeInTheDocument();
  });

  it("si el servidor no activa el quiosco lo dice y deja reintentar", async () => {
    signInAs("coach");
    let calls = 0;
    const mock = mockApi({ "POST /auth/kiosk": () => (++calls === 1 ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : KIOSK_OUT(CHECKIN)) });
    inRouter(<GymShell />, CHECKIN);

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos activar el modo tablet");
    // MEDIUM-1: sin la marca del servidor el check-in no se muestra.
    expect(screen.queryByRole("heading", { name: "Contenido" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => { expect(getSession().user?.kioskPath).toBe(CHECKIN); });
    expect(mock.callsTo("POST /auth/kiosk")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Contenido" })).toBeInTheDocument();
  });

  it("MEDIUM-1: normaliza la ruta (minúsculas, sin barra final) antes del POST y no muestra el check-in hasta tener la marca", async () => {
    signInAs("coach");
    const normal = "/clases/abc-def/checkin";
    const mock = mockApi({ "POST /auth/kiosk": () => KIOSK_OUT(normal) });
    inRouter(<GymShell />, "/clases/ABC-DEF/checkin/");

    expect(screen.queryByRole("heading", { name: "Contenido" })).not.toBeInTheDocument();
    await waitFor(() => { expect(getSession().user?.kioskPath).toBe(normal); });
    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: normal });
    expect(await screen.findByRole("heading", { name: "Contenido" })).toBeInTheDocument();
  });

  it("S7-D42: cambiar de sesión desde el quiosco llama POST /auth/kiosk con la ruta nueva y navega sin contraseña", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const otra = "/clases/2/checkin";
    const mock = mockApi({ "POST /auth/kiosk": KIOSK_OUT(otra) });
    function Probe() {
      const { switchSession } = useGym();
      return (
        <button type="button" onClick={() => void switchSession(otra)}>
          Cambiar
        </button>
      );
    }
    const router = createMemoryRouter([{ element: <GymShell />, children: [{ path: "*", element: <Probe />, handle: { title: "Check-in" } }] }], { initialEntries: [CHECKIN] });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await userEvent.setup().click(screen.getByRole("button", { name: "Cambiar" }));

    await waitFor(() => { expect(router.state.location.pathname).toBe(otra); });
    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: otra });
    // L-10: cambiar de clase reemplaza la entrada del historial («atrás» no vuelve a la clase anterior).
    expect(router.state.historyAction).toBe("REPLACE");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(getSession().user?.kioskPath).toBe(otra);
  });

  it("S7-D42: si el servidor rechaza la clase (403 kiosk_mode) no navega, la marca sigue y dice qué hacer", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const otra = "/clases/2/checkin";
    const mock = mockApi({ "POST /auth/kiosk": { status: 403, body: { error: { code: "kiosk_mode", message: "x" } } } });
    let result: string | null = null;
    function Probe() {
      const { switchSession } = useGym();
      return (
        <button
          type="button"
          onClick={() => {
            void switchSession(otra).then((message) => {
              result = message;
            });
          }}
        >
          Cambiar
        </button>
      );
    }
    const router = createMemoryRouter([{ element: <GymShell />, children: [{ path: "*", element: <Probe />, handle: { title: "Check-in" } }] }], { initialEntries: [CHECKIN] });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await userEvent.setup().click(screen.getByRole("button", { name: "Cambiar" }));

    await waitFor(() => {
      expect(result).toBe(KIOSK_MESSAGES.notToday);
    });
    expect(mock.callsTo("POST /auth/kiosk")).toHaveLength(1);
    expect(router.state.location.pathname).toBe(CHECKIN);
    expect(getSession().user?.kioskPath).toBe(CHECKIN);
  });

  it("el modo tablet se deriva de la sesión: con kioskPath sigue en otra pantalla y no vuelve a llamar al api", () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const mock = mockApi({});
    inRouter(<GymShell />, "/clases/1/otra");

    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(mock.calls).toHaveLength(0);
  });

  it("sin marca fuera del check-in no hay modo tablet", () => {
    signInAs("coach");
    inRouter(<GymShell />, "/clases/1/otra");

    expect(screen.getByRole("link", { name: "Salir" })).toBeInTheDocument();
  });

  it("salir: contraseña incorrecta no sale; la correcta usa POST /auth/kiosk/exit (nunca /auth/login) y quita la marca", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const user = userEvent.setup();
    const mock = mockApi({
      "POST /auth/kiosk/exit": (call) => ((call.body as { password?: string } | undefined)?.password === "buena" ? KIOSK_OUT(null) : { status: 401, body: { error: { code: "invalid_password", message: "No." } } }),
    });
    const { router } = inRouter(<GymShell />, CHECKIN);

    await user.click(screen.getByRole("button", { name: "Clases" }));
    await user.type(screen.getByLabelText(/Contraseña/), "mala");
    await user.click(screen.getByRole("button", { name: "Salir del modo tablet" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Contraseña incorrecta. Escríbela de nuevo.");
    expect(getSession().user?.kioskPath).toBe(CHECKIN);

    await user.clear(screen.getByLabelText(/Contraseña/));
    await user.type(screen.getByLabelText(/Contraseña/), "buena");
    await user.click(screen.getByRole("button", { name: "Salir del modo tablet" }));
    await waitFor(() => { expect(router.state.location.pathname).toBe("/clases"); });
    expect(getSession().user?.kioskPath).toBeNull();
    expect(mock.callsTo("POST /auth/login")).toHaveLength(0);
    // HIGH-1 (revisión de F4b): salir no reactiva el quiosco aunque el pathname sea el del check-in un instante.
    expect(mock.callsTo("POST /auth/kiosk")).toHaveLength(0);
  });

  it("LOW-2: tras una contraseña incorrecta y cerrar el diálogo, otra navegación vuelve a quedar retenida", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const user = userEvent.setup();
    mockApi({ "POST /auth/kiosk/exit": { status: 401, body: { error: { code: "invalid_password", message: "No." } } } });
    const { router } = inRouter(<GymShell />, CHECKIN);

    await user.click(screen.getByRole("button", { name: "Clases" }));
    await user.type(screen.getByLabelText(/Contraseña/), "mala");
    await user.click(screen.getByRole("button", { name: "Salir del modo tablet" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Volver" }));
    await act(async () => {
      await router.navigate("/socios");
    });

    expect(await screen.findByRole("dialog", { name: "¿Salir del modo tablet?" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(CHECKIN);
  });

  it("«atrás» o cualquier navegación fuera del check-in abre el diálogo de salida y se queda; con la contraseña pasa", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const user = userEvent.setup();
    mockApi({ "POST /auth/kiosk/exit": KIOSK_OUT(null) });
    const { router } = inRouter(<GymShell />, CHECKIN);

    await act(async () => {
      await router.navigate("/socios");
    });
    expect(await screen.findByRole("dialog", { name: "¿Salir del modo tablet?" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(CHECKIN);

    await user.click(screen.getByRole("button", { name: "Volver" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(CHECKIN);

    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.pathname).toBe(CHECKIN);

    await act(async () => {
      await router.navigate("/socios");
    });
    await user.type(await screen.findByLabelText(/Contraseña/), "buena");
    await user.click(screen.getByRole("button", { name: "Salir del modo tablet" }));
    await waitFor(() => { expect(router.state.location.pathname).toBe("/socios"); });
  });

  it("un cambio de query en el mismo check-in no abre el diálogo", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const { router } = inRouter(<GymShell />, CHECKIN);

    await act(async () => {
      await router.navigate(`${CHECKIN}?x=1`);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a los 10 minutos sin actividad cierra la sesión (POST /auth/logout) y la marca muere con ella", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const mock = mockApi({ "POST /auth/logout": { status: 204 } });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    try {
      inRouter(<GymShell />, CHECKIN);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10 * 60_000);
      });
    } finally {
      vi.useRealTimers();
    }

    expect(mock.callsTo("POST /auth/logout")).toHaveLength(1);
    expect(getSession().user).toBeNull();
  });

  it("TvShell monta el escenario de la TV", () => {
    inRouter(<TvShell />, "/tv");

    expect(screen.getByTestId("tv-stage")).toBeInTheDocument();
  });
});

describe("AccessLayout", () => {
  it("centra la tarjeta con el logo de fondo claro dentro de <main>", async () => {
    const { container } = render(
      <MemoryRouter>
        <AccessLayout>
          <h1>Iniciar sesión</h1>
        </AccessLayout>
      </MemoryRouter>,
    );

    const main = screen.getByRole("main");
    expect(within(main).getByRole("img", { name: "APEX Hybrid Training" })).toHaveAttribute("src", "/brand/apex-logo-light-bg.png");
    expect(within(main).getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("PanelShell · panel de pagos (S3-F4, S3-D65, E10)", () => {
  const MEMBERSHIP = "66666666-6666-4666-8666-666666666666";
  const withoutPayments: ReadonlySet<Feature> = new Set([...ENABLED_FEATURES].filter((feature) => feature !== "payments"));

  it("sin ?pago= no descarga ni monta el host", () => {
    signInAs("coach");
    inRouter(<PanelShell />, "/membresias");

    expect(screen.queryByText("Panel de pagos montado")).not.toBeInTheDocument();
    expect(paymentHost.loaded).not.toHaveBeenCalled();
  });

  it("con ?pago= descarga el host perezoso y lo monta en la ranura del banner", async () => {
    signInAs("coach");
    inRouter(<PanelShell />, `/membresias?pago=${MEMBERSHIP}`);

    expect(await screen.findByText("Panel de pagos montado")).toBeInTheDocument();
    expect(paymentHost.loaded).toHaveBeenCalledTimes(1);
    expect(within(screen.getByRole("main")).getByText("Panel de pagos montado")).toBeInTheDocument();
  });

  it("sin la feature payments no monta el host aunque la URL lo pida", async () => {
    signInAs("admin");
    inRouter(<PanelShell enabledFeatures={withoutPayments} />, `/membresias?pago=${MEMBERSHIP}`);

    expect(await screen.findByRole("heading", { name: "Contenido" })).toBeInTheDocument();
    expect(screen.queryByText("Panel de pagos montado")).not.toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Menú principal" })).queryByRole("link", { name: "Pagos" })).not.toBeInTheDocument();
  });

  it("sin sesión no monta el host", () => {
    inRouter(<PanelShell />, `/membresias?pago=${MEMBERSHIP}`);

    expect(screen.queryByText("Panel de pagos montado")).not.toBeInTheDocument();
  });
});

describe("PanelShell · permiso del panel de pagos (revisión S3-F4, M3)", () => {
  it("un rol sin payments.register no monta el host aunque la URL lo pida", async () => {
    signInAs("member");
    inRouter(<PanelShell />, "/?pago=66666666-6666-4666-8666-666666666666");

    expect(await screen.findByRole("heading", { name: "Contenido" })).toBeInTheDocument();
    expect(screen.queryByText("Panel de pagos montado")).not.toBeInTheDocument();
  });
});
