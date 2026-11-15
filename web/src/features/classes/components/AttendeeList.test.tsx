// S7-F4 · US-161 (front): la lista «Ya llegaron» y «Quitar» con motivo opcional (DELETE /attendance/{id}, cuerpo opcional, E4).
// 403 `attendance_locked` (el coach solo quita hoy o ayer), 404 y 5xx dentro del modal; la lista se relee al quitar.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, ATTENDEES } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { AttendeeList } from "./AttendeeList";

const KEY = "DELETE /attendance/t1";

function renderList(handlers: Record<string, MockHandler> = {}, attendees = ATTENDEES) {
  const mock = mockApi({ [KEY]: { status: 204 }, ...handlers });
  const queryClient = testQueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <MemoryRouter>
          <AttendeeList attendees={attendees} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, invalidate, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "¿Quitar a Diego Mora de esta clase?" });

beforeEach(() => {
  signInAs("coach");
});
afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("AttendeeList", () => {
  it("cada asistente con hora de Bogotá y «Quitar»; sin nadie, el vacío guía", () => {
    renderList();
    const diego = screen.getByText("Diego Mora").closest("li") as HTMLElement;

    expect(within(diego).getByText("16:48")).toBeInTheDocument();
    expect(within(diego).getByRole("button", { name: "Quitar a Diego Mora" })).toBeInTheDocument();
    cleanup();
    renderList({}, []);
    expect(screen.getByText(/Todavía no llegó nadie/)).toBeInTheDocument();
  });

  it("quitar sin motivo manda DELETE sin cuerpo y relee la sesión", async () => {
    const { mock, user, invalidate } = renderList();
    await user.click(screen.getByRole("button", { name: "Quitar a Diego Mora" }));
    expect(dialog()).toHaveAccessibleDescription(expect.stringContaining("Queda en la auditoría") as string);
    expect(within(dialog()).getByRole("textbox", { name: /^Motivo/ })).not.toBeRequired();
    await user.click(within(dialog()).getByRole("button", { name: "Quitar asistencia" }));

    await waitFor(() => { expect(mock.callsTo(KEY)).toHaveLength(1); });
    expect(mock.callsTo(KEY)[0]?.rawBody).toBeUndefined();
    await waitFor(() => { expect(screen.queryByRole("dialog")).toBeNull(); });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["class-session"] });
    // L4: la lista de Asistencia, el resumen y la pestaña del socio se releen (clave ["attendance"]).
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["attendance"] });
  });

  it("con motivo lo manda en el cuerpo, no en la URL", async () => {
    const { mock, user } = renderList();
    await user.click(screen.getByRole("button", { name: "Quitar a Diego Mora" }));
    await user.type(within(dialog()).getByRole("textbox", { name: /^Motivo/ }), "Entró a otra clase");
    await user.click(within(dialog()).getByRole("button", { name: "Quitar asistencia" }));

    await waitFor(() => { expect(mock.callsTo(KEY)).toHaveLength(1); });
    expect(mock.callsTo(KEY)[0]?.body).toEqual({ reason: "Entró a otra clase" });
    expect(mock.callsTo(KEY)[0]?.url).not.toContain("Entr");
  });

  it("403 attendance_locked: dice que ya no se puede y a quién pedirlo; el modal sigue abierto", async () => {
    const { user } = renderList({ [KEY]: apiError(403, "attendance_locked") });
    await user.click(screen.getByRole("button", { name: "Quitar a Diego Mora" }));
    await user.click(within(dialog()).getByRole("button", { name: "Quitar asistencia" }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Esta asistencia ya no se puede quitar desde la tablet. Pídele a un administrador que la quite.");
  });

  it.each([
    [404, "attendance_not_found", "Esa asistencia ya no existe. Cierra este aviso; actualizamos la lista."],
    [500, "internal_error", "No pudimos quitar la asistencia. Intenta de nuevo en un momento."],
  ])("%i %s dentro del modal", async (status, code, text) => {
    const { user } = renderList({ [KEY]: apiError(status, code) });
    await user.click(screen.getByRole("button", { name: "Quitar a Diego Mora" }));
    await user.click(within(dialog()).getByRole("button", { name: "Quitar asistencia" }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(text);
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderList();
    expect(await axe(container)).toHaveNoViolations();
  });
});
