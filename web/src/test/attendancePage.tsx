// S7-F5: montaje de prueba de /clases/asistencia (AttendancePage) con un marcador de la ubicación (`where`).
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import AttendancePage from "../features/classes/pages/AttendancePage";
import { handlersFor } from "./attendance";
import { mockApi, testQueryClient, type MockHandler } from "./server";

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

export function renderPageAt(entry = "/clases/asistencia", handlers: Record<string, MockHandler> = handlersFor()) {
  const mock = mockApi(handlers);
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <AttendancePage />
          <Where />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}
