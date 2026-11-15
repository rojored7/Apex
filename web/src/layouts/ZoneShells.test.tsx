// S8-F4 · S8-D15 y S8-D27: GymShell también confina la ruta de resultados de la tablet. Entra al quiosco con la ruta
// /clases/:id/resultados (POST /auth/kiosk), sin enlaces, con la salida «Clases»; pasar del check-in a resultados de la misma
// clase es un cambio de clase (S7-D42) y no pide contraseña.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { getSession } from "../core/auth";
import { useGym } from "../shared/hooks/gymContext";
import { mockApi, testQueryClient } from "../test/server";
import { signInAs, signOutForTests } from "../test/session";
import { GymShell } from "./ZoneShells";

const KIOSK_OUT = (kioskPath: string | null) => ({ status: 200, body: { access_token: "access-quiosco", token_type: "bearer", expires_in: 900, kiosk_path: kioskPath } });
const RESULTS = "/clases/1/resultados";
const CHECKIN = "/clases/1/checkin";

function GoToResults() {
  const { switchSession } = useGym();
  return (
    <button
      type="button"
      onClick={() => {
        void switchSession(RESULTS);
      }}
    >
      Registrar resultados
    </button>
  );
}

function inRouter(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: <GymShell />,
        children: [
          { path: "/clases/:id/checkin", element: <GoToResults />, handle: { title: "Check-in" } },
          { path: "/clases/:id/resultados", element: <h1>Pantalla de resultados</h1>, handle: { title: "Registro de resultados" } },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, router };
}

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("GymShell · resultados", () => {
  it("al llegar a /resultados activa el quiosco con esa ruta y muestra la pantalla sin enlaces", async () => {
    signInAs("coach");
    const mock = mockApi({ "POST /auth/kiosk": KIOSK_OUT(RESULTS) });
    inRouter(RESULTS);

    expect(await screen.findByRole("heading", { name: "Pantalla de resultados" })).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: RESULTS });
    expect(getSession().user?.kioskPath).toBe(RESULTS);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Clases" })).toBeInTheDocument();
  });

  it("no muestra la pantalla de resultados hasta que el servidor confirma la marca", () => {
    signInAs("coach");
    mockApi({ "POST /auth/kiosk": () => new Promise(() => undefined) as never });
    inRouter(RESULTS);
    expect(screen.getByRole("status")).toHaveTextContent("Activando el modo tablet");
    expect(screen.queryByRole("heading", { name: "Pantalla de resultados" })).not.toBeInTheDocument();
  });

  it("del check-in a resultados de la misma clase: cambio de clase sin contraseña", async () => {
    signInAs("coach", { kioskPath: CHECKIN });
    const mock = mockApi({ "POST /auth/kiosk": KIOSK_OUT(RESULTS) });
    const { router } = inRouter(CHECKIN);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Registrar resultados" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(RESULTS);
    });
    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: RESULTS });
    expect(mock.callsTo("POST /auth/kiosk/exit")).toHaveLength(0);
    expect(getSession().user?.kioskPath).toBe(RESULTS);
  });
});
