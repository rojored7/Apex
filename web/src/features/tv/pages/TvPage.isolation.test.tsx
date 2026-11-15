// S8-F6b (M-1): la TV vive en TvShell con su PROPIO QueryClient. El logout de L-4 vacía el QueryClient global (clearSession); si la TV
// compartiera ese cliente, la petición de GET /tv/today en vuelo se perdía en silencio y la pantalla quedaba en «Cargando…».
// La prueba usa el cliente real de la app y la sesión real (sin simular logout).
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { queryClient as appQueryClient } from "../../../core/api/queryClient";
import { mockApi } from "../../../test/server";
import { signOutForTests } from "../../../test/session";
import { tvBoard, TV_TOKEN } from "../../../test/tv";
import TvPage from "./TvPage";

const LATE_MS = 80;

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("TvPage · aislada del cliente global", () => {
  it("el logout de la TV no pierde el GET /tv/today que ya iba en vuelo", async () => {
    window.localStorage.clear();
    window.history.replaceState(null, "", `/tv#token=${TV_TOKEN}`);
    mockApi({
      "GET /tv/today": async () => {
        await new Promise((resolve) => setTimeout(resolve, LATE_MS));
        return { status: 200, body: tvBoard() };
      },
      "POST /auth/logout": { status: 204 },
    });

    render(
      <QueryClientProvider client={appQueryClient}>
        <MemoryRouter initialEntries={["/tv"]}>
          <Routes>
            <Route path="/tv" element={<TvPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Helen" })).toBeInTheDocument();
  });
});
