// S8-F1 · US-166 (front, S8-D6): panel lateral para crear y editar un benchmark (pestaña Benchmarks de Movimientos).
// - Nombre de 1 a 60, tipo de marca (tiempo, rondas + repeticiones, repeticiones, carga) y descripción de 0 a 2.000.
// - 409 `benchmark_exists` bajo «Nombre»; 422 `score_type_locked` bajo «Tipo de marca».
// - Con WODs que lo usan, el tipo se ve bloqueado desde el principio.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { BENCHMARKS, benchmark } from "../../../test/wods";
import type { BenchmarkView } from "../api";
import { BenchmarkPanel } from "./BenchmarkPanel";

const FRAN_PATCH = `PATCH /benchmarks/${BENCHMARKS.fran.id}`;

function renderPanel(handlers: Record<string, MockHandler> = {}, target: BenchmarkView | null = null) {
  const mock = mockApi({
    "POST /benchmarks": { status: 201, body: benchmark("e1e1e1e1-0000-4000-8000-000000000009", { name: "Grace", score_type: "reps" }) },
    [FRAN_PATCH]: { status: 200, body: { ...BENCHMARKS.fran, description: "Nueva" } },
    ...handlers,
  });
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter>
          <BenchmarkPanel open benchmark={target} onClose={onClose} onSaved={onSaved} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, onClose, onSaved, user: userEvent.setup(), ...view };
}

const save = () => screen.getByRole("button", { name: /^(Guardar|Crear benchmark)/ });

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("BenchmarkPanel · crear", () => {
  it("sin nombre no envía y lo dice bajo el campo", async () => {
    const { user, mock } = renderPanel();

    expect(screen.getByRole("dialog", { name: "Nuevo benchmark" })).toBeInTheDocument();
    await user.click(save());

    expect(await screen.findByText("Escribe el nombre del benchmark (hasta 60 caracteres).")).toBeInTheDocument();
    expect(mock.callsTo("POST /benchmarks")).toHaveLength(0);
  });

  it("ofrece los cuatro tipos de marca y envía nombre, tipo y descripción", async () => {
    const { user, mock, onSaved } = renderPanel();
    const options = Array.from(screen.getByLabelText<HTMLSelectElement>(/^Tipo de marca/).options).map((o) => o.textContent);
    expect(options).toEqual(["Tiempo", "Rondas + repeticiones", "Repeticiones", "Carga"]);
    await user.type(screen.getByLabelText(/^Nombre/), "  Grace ");
    await user.selectOptions(screen.getByLabelText(/^Tipo de marca/), "reps");
    await user.type(screen.getByLabelText(/^Descripción/), "30 clean and jerks");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo("POST /benchmarks")[0]?.body).toEqual({ name: "Grace", score_type: "reps", description: "30 clean and jerks" });
  });

  it("una descripción de más de 2.000 caracteres no se envía", async () => {
    const { user, mock } = renderPanel();
    await user.type(screen.getByLabelText(/^Nombre/), "Grace");
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: "a".repeat(2001) } });

    await user.click(save());

    expect(await screen.findByText("La descripción admite hasta 2.000 caracteres.")).toBeInTheDocument();
    expect(mock.callsTo("POST /benchmarks")).toHaveLength(0);
  });

  it("409 benchmark_exists va bajo «Nombre»", async () => {
    const { user, onSaved } = renderPanel({ "POST /benchmarks": apiError(409, "benchmark_exists", { field: "name", existing_id: BENCHMARKS.fran.id }) });
    await user.type(screen.getByLabelText(/^Nombre/), "fran");

    await user.click(save());

    expect(await screen.findByText("Ya existe un benchmark con ese nombre. Búscalo en la lista o usa otro nombre.")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("500 como aviso del panel", async () => {
    const { user } = renderPanel({ "POST /benchmarks": apiError(500, "internal_error") });
    await user.type(screen.getByLabelText(/^Nombre/), "Grace");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos guardar el benchmark. Intenta de nuevo en un momento.");
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPanel();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("BenchmarkPanel · editar", () => {
  it("precarga el benchmark y deja cambiar el tipo mientras ningún WOD lo use", () => {
    renderPanel({}, BENCHMARKS.fran);

    expect(screen.getByRole("dialog", { name: "Editar benchmark · Fran" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Nombre/)).toHaveValue("Fran");
    expect(screen.getByLabelText(/^Tipo de marca/)).toBeEnabled();
    expect(screen.getByLabelText(/^Tipo de marca/)).toHaveValue("time");
  });

  it("con WODs que lo usan el tipo queda bloqueado y lo explica", () => {
    renderPanel({}, BENCHMARKS.cindy);

    expect(screen.getByLabelText(/^Tipo de marca/)).toBeDisabled();
    expect(screen.getByText("Ya hay WODs que usan este benchmark: el tipo de marca no se puede cambiar.")).toBeInTheDocument();
  });

  it("solo manda lo que cambió", async () => {
    const { user, mock, onSaved } = renderPanel({}, BENCHMARKS.fran);
    const description = screen.getByLabelText(/^Descripción/);
    await user.clear(description);
    await user.type(description, "Nueva");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(FRAN_PATCH)[0]?.body).toEqual({ description: "Nueva" });
  });

  it("422 score_type_locked (otro coach ya lo usó en un WOD) va bajo «Tipo de marca»", async () => {
    const { user } = renderPanel({ [FRAN_PATCH]: apiError(422, "score_type_locked", { field: "score_type" }) }, BENCHMARKS.fran);
    await user.selectOptions(screen.getByLabelText(/^Tipo de marca/), "reps");

    await user.click(save());

    expect(await screen.findByText("Ya hay WODs que usan este benchmark: el tipo de marca no se puede cambiar.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Tipo de marca/)).toHaveAccessibleDescription(expect.stringContaining("el tipo de marca no se puede cambiar") as string);
  });

  it("404 dice que el benchmark ya no existe", async () => {
    const { user } = renderPanel({ [FRAN_PATCH]: apiError(404, "benchmark_not_found") }, BENCHMARKS.fran);
    await user.type(screen.getByLabelText(/^Nombre/), " 2");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este benchmark ya no existe. Cierra el panel y actualiza la lista.");
  });
});
