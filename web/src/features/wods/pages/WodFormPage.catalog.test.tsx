// S9-F2 (E8, S9-D40): el formulario del WOD toma las opciones de movimientos y benchmarks de shared/data/catalog.ts.
// La prueba reemplaza SOLO ese módulo por un catálogo propio («Zercher Squat» y «Murph»), mientras el api simulado devuelve el de
// siempre (Back Squat, Fran): si la página siguiera leyendo de features/wods/api, se vería el del api y no el del módulo compartido.
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { SessionRoleProvider } from "../../../core/auth";
import { mockApi, testQueryClient } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { benchmarksPage, movementsPage } from "../../../test/wods";
import WodFormPage from "./WodFormPage";

const SHARED_MOVEMENT = {
  id: "aaaaaaaa-0000-4000-8000-0000000000a1",
  name: "Zercher Squat",
  category: "weightlifting",
  unit: "kg",
  is_active: true,
  wod_count: 0,
  created_at: "2026-10-01T15:00:00Z",
  updated_at: "2026-10-01T15:00:00Z",
} as const;

const SHARED_BENCHMARK = {
  id: "bbbbbbbb-0000-4000-8000-0000000000b1",
  name: "Murph",
  description: "",
  score_type: "time",
  wod_count: 0,
  created_at: "2026-10-01T15:00:00Z",
  updated_at: "2026-10-01T15:00:00Z",
} as const;

vi.mock("../../../shared/data/catalog", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../../shared/data/catalog")>();
  const page = <T,>(item: T) => ({ items: [item], total: 1, limit: 100, offset: 0 });
  return {
    ...original,
    useMovements: () => useQuery({ queryKey: ["shared-catalog-test", "movements"], queryFn: () => Promise.resolve(page(SHARED_MOVEMENT)) }),
    useBenchmarks: () => useQuery({ queryKey: ["shared-catalog-test", "benchmarks"], queryFn: () => Promise.resolve(page(SHARED_BENCHMARK)) }),
  };
});

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("WodFormPage · catálogo compartido", () => {
  it("ofrece los movimientos y benchmarks de shared/data/catalog, no los de features/wods/api", async () => {
    mockApi({ "GET /movements": movementsPage(), "GET /benchmarks": benchmarksPage() });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <SessionRoleProvider>
          <MemoryRouter initialEntries={["/wods/nuevo?date=2026-10-24"]}>
            <Routes>
              <Route path="/wods/nuevo" element={<WodFormPage />} />
            </Routes>
          </MemoryRouter>
        </SessionRoleProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("option", { name: "Zercher Squat" })).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Murph" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Back Squat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Fran" })).not.toBeInTheDocument();
  });
});
