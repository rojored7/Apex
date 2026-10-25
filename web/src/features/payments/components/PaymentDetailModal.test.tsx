// S3-F6 · US-099 (front): detalle de un pago (Pagos.html, "Detalle del pago"; GET /payments/{id}).
// - Socio (enlace a la ficha), membresía, valor, medio y referencia, fecha y hora de Bogotá, quién
//   registró (el correo parcial tal cual, S3-D57) y, si es retroactivo, cuándo se registró.
// - Anulado: bloque con el motivo, quién anuló (correo parcial) y cuándo.
// - Sin editar ni borrar (DESIGN.md regla 4). "Anular pago" solo con `payments.void` (admin) y solo
//   si no está anulado; abre VoidPaymentModal y al volver se ve el detalle releído.
// - Estados: carga, 404 y error con Reintentar.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { RoleProvider, type Role } from "../../../core/auth";
import { apiError } from "../../../test/memberships";
import { voidKey } from "../../../test/paymentPanel";
import { PAYMENT_ID, paymentDetail, paymentDetailKey, paymentMethods, paymentOut } from "../../../test/payments";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { PaymentDetailModal } from "./PaymentDetailModal";

const VOIDED = paymentDetail({
  voided: true,
  void_reason: "Pago duplicado",
  voided_by: "00000000-0000-4000-8000-000000000001",
  voided_by_name: "a•••@apex.test",
  voided_at: "2026-10-21T15:30:00Z",
});

function Screen({ onClose }: { onClose: () => void }) {
  const [id, setId] = useState<string | null>(PAYMENT_ID);
  return (
    <main>
      <h1>Pagos</h1>
      <PaymentDetailModal
        paymentId={id}
        onClose={() => {
          setId(null);
          onClose();
        }}
      />
    </main>
  );
}

function renderDetail(role: Role, handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({
    [paymentDetailKey()]: { status: 200, body: paymentDetail() },
    "GET /payments/methods": paymentMethods(),
    ...handlers,
  });
  const onClose = vi.fn();
  const router = createMemoryRouter(
    [
      { path: "/pagos", element: <Screen onClose={onClose} /> },
      { path: "/socios/:id", element: <h1>Ficha del socio</h1> },
    ],
    { initialEntries: ["/pagos"] },
  );
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RoleProvider value={role}>
        <RouterProvider router={router} />
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, onClose, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "Detalle del pago" });
const field = (label: string): string => {
  const term = within(dialog()).getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PaymentDetailModal · contenido", () => {
  it("muestra socio, membresía, valor, medio y referencia, fecha de Bogotá, quién registró y el estado", async () => {
    renderDetail("coach");

    expect(await screen.findByRole("dialog", { name: "Detalle del pago" })).toBeInTheDocument();
    expect(await within(dialog()).findByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", "/socios/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(field("Membresía")).toBe("Mensual 29 oct–28 nov");
    expect(field("Valor")).toBe("$ 120.000");
    expect(field("Medio · referencia")).toBe("Nequi · M12345678");
    expect(field("Fecha del pago")).toBe("20 oct 2026, 2:10 p. m.");
    expect(field("Registró")).toBe("c•••@apex.test");
    expect(field("Estado")).toBe("Válido");
  });

  it("efectivo sin referencia lo dice", async () => {
    renderDetail("coach", { [paymentDetailKey()]: { status: 200, body: paymentDetail({ method: "cash", reference: null }) } });

    await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("link", { name: "Laura Gómez" });
    expect(field("Medio · referencia")).toBe("Efectivo · sin referencia");
  });

  it("un pago retroactivo muestra la marca y cuándo se registró", async () => {
    renderDetail("coach", { [paymentDetailKey()]: { status: 200, body: paymentDetail({ backdated: true, created_at: "2026-10-23T14:00:00Z" }) } });

    await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("link", { name: "Laura Gómez" });
    expect(field("Estado")).toBe("VálidoRetroactivo");
    expect(field("Registrado el")).toBe("23 oct 2026, 9:00 a. m.");
  });

  it("registró en null muestra una raya", async () => {
    renderDetail("coach", { [paymentDetailKey()]: { status: 200, body: paymentDetail({ registered_by_name: null }) } });

    await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("link", { name: "Laura Gómez" });
    expect(field("Registró")).toBe("—");
  });

  it("un pago anulado muestra el motivo, quién lo anuló (correo parcial) y cuándo", async () => {
    renderDetail("admin", { [paymentDetailKey()]: { status: 200, body: VOIDED } });

    const voidBlock = await screen.findByRole("region", { name: "Anulación" });
    expect(within(voidBlock).getByText("Pago duplicado")).toBeInTheDocument();
    expect(field("Motivo")).toBe("Pago duplicado");
    expect(field("Anuló")).toBe("a•••@apex.test");
    expect(field("Fecha de anulación")).toBe("21 oct 2026, 10:30 a. m.");
    expect(field("Estado")).toBe("Anulado");
  });

  it("un anulado sin autor conocido muestra una raya", async () => {
    renderDetail("admin", { [paymentDetailKey()]: { status: 200, body: { ...VOIDED, voided_by_name: null } } });

    await screen.findByRole("region", { name: "Anulación" });
    expect(field("Anuló")).toBe("—");
  });

  it("no hay botones de editar ni de borrar, y explica que un pago no se edita", async () => {
    renderDetail("admin");

    await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("link", { name: "Laura Gómez" });
    expect(within(dialog()).queryByRole("button", { name: /editar|borrar|eliminar/i })).not.toBeInTheDocument();
    expect(within(dialog()).getByText("Un pago nunca se edita: si tiene un error, se anula y se registra otro.")).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    renderDetail("admin", { [paymentDetailKey()]: { status: 200, body: VOIDED } });

    await screen.findByRole("region", { name: "Anulación" });
    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("PaymentDetailModal · anular", () => {
  it("el coach no ve 'Anular pago'", async () => {
    renderDetail("coach");

    await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("link", { name: "Laura Gómez" });
    expect(within(dialog()).queryByRole("button", { name: "Anular pago" })).not.toBeInTheDocument();
  });

  it("un pago ya anulado no ofrece 'Anular pago'", async () => {
    renderDetail("admin", { [paymentDetailKey()]: { status: 200, body: VOIDED } });

    await screen.findByRole("region", { name: "Anulación" });
    expect(within(dialog()).queryByRole("button", { name: "Anular pago" })).not.toBeInTheDocument();
  });

  it("el admin abre VoidPaymentModal; Volver regresa al detalle", async () => {
    const { user } = renderDetail("admin");

    await user.click(await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("button", { name: "Anular pago" }));

    const confirm = await screen.findByRole("dialog", { name: "¿Anular este pago?" });
    expect(screen.queryByRole("dialog", { name: "Detalle del pago" })).not.toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "Volver" }));
    expect(await screen.findByRole("dialog", { name: "Detalle del pago" })).toBeInTheDocument();
  });

  it("tras anular, al cerrar 'Pago anulado' el detalle se relee y muestra la anulación", async () => {
    let voided = false;
    const { user, mock } = renderDetail("admin", {
      [paymentDetailKey()]: () => ({ status: 200, body: voided ? VOIDED : paymentDetail() }),
      [voidKey(PAYMENT_ID)]: () => {
        voided = true;
        return { status: 200, body: paymentOut({ id: PAYMENT_ID, voided: true, void_reason: "Pago duplicado" }) };
      },
    });

    await user.click(await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("button", { name: "Anular pago" }));
    const confirm = await screen.findByRole("dialog", { name: "¿Anular este pago?" });
    await user.type(within(confirm).getByRole("textbox", { name: /^Motivo/ }), "Pago duplicado");
    await user.click(within(confirm).getByRole("button", { name: "Anular pago" }));
    const done = await screen.findByRole("dialog", { name: "Pago anulado" });
    await user.click(within(done).getByRole("button", { name: "Cerrar" }));

    expect(await screen.findByRole("region", { name: "Anulación" })).toBeInTheDocument();
    expect(mock.callsTo(voidKey(PAYMENT_ID))[0]?.body).toEqual({ reason: "Pago duplicado" });
    expect(mock.callsTo(paymentDetailKey()).length).toBeGreaterThanOrEqual(2);
  });
});

describe("PaymentDetailModal · estados", () => {
  it("mientras carga lo dice y Cerrar funciona", async () => {
    const { user, onClose } = renderDetail("coach", { [paymentDetailKey()]: () => new Promise(() => undefined) });

    expect(await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByText("Cargando el pago…")).toBeInTheDocument();
    await user.click(within(dialog()).getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("un 404 dice que el pago no existe", async () => {
    renderDetail("coach", { [paymentDetailKey()]: apiError(404, "payment_not_found") });

    expect(await screen.findByRole("alert")).toHaveTextContent("No encontramos este pago. Cierra el detalle y actualiza la lista.");
  });

  it("otro error se explica y Reintentar lo pide de nuevo", async () => {
    let fail = true;
    const { user, mock } = renderDetail("coach", { [paymentDetailKey()]: () => (fail ? apiError(500, "internal_error") : { status: 200, body: paymentDetail() }) });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar el pago. Intenta de nuevo.");
    fail = false;
    await user.click(within(dialog()).getByRole("button", { name: "Reintentar" }));
    expect(await within(dialog()).findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo(paymentDetailKey()).length).toBe(2);
    });
  });

  it("sin pago elegido no pinta nada", () => {
    mockApi({});
    const router = createMemoryRouter([{ path: "*", element: <PaymentDetailModal paymentId={null} onClose={vi.fn()} /> }]);
    render(
      <QueryClientProvider client={testQueryClient()}>
        <RoleProvider value="admin">
          <RouterProvider router={router} />
        </RoleProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
