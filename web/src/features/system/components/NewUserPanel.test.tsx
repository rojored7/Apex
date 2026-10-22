// S2-F4a · US-047 (front) y L-7: alta de un usuario del equipo en un SidePanel.
// - Correo y rol (solo admin o coach, L-2); POST /users.
// - 201: el enlace de activación en un campo de solo lectura con "Copiar" y "Entrega este
//   enlace por un medio seguro; vence en 72 horas". La mutación usa gcTime: 0 y, al cerrar el
//   panel, reset(): el enlace ya no está ni en la pantalla ni en la caché de TanStack Query.
// - 409 email_taken: el error va bajo el correo con un enlace al usuario existente.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { axe } from "vitest-axe";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { NewUserPanel } from "./NewUserPanel";

const EXISTING_ID = "44444444-4444-4444-8444-444444444444";
const URL_ACTIVACION = "https://apex.test/restablecer/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789";

const CREATED = {
  status: 201,
  body: {
    user: {
      id: "55555555-5555-4555-8555-555555555555",
      email: "carlos@apex.test",
      role: "coach",
      status: "pending_activation",
      member_id: null,
      must_change_password: false,
    },
    activation_url: URL_ACTIVACION,
    expires_at: "2026-10-25T19:30:00Z",
  },
};

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <main>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Abrir alta
      </button>
      <Where />
      <NewUserPanel
        open={open}
        onClose={() => {
          setOpen(false);
        }}
      />
    </main>
  );
}

function renderPanel(handlers: Record<string, MockHandler> = {}, queryClient: QueryClient = testQueryClient()) {
  const mock = mockApi({ "POST /users": CREATED, ...handlers });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { mock, queryClient, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "Nuevo usuario del equipo" });
const emailBox = () => within(dialog()).getByRole("textbox", { name: /^Correo/ });
const roleSelect = () => within(dialog()).getByRole("combobox", { name: /^Rol/ });
const createButton = () => within(dialog()).getByRole("button", { name: /Crear usuario|Creando/ });
const linkBox = () => within(dialog()).getByRole("textbox", { name: "Enlace de activación" });

async function create(user: ReturnType<typeof userEvent.setup>, email = "carlos@apex.test"): Promise<void> {
  await user.type(emailBox(), email);
  await user.click(createButton());
}

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("NewUserPanel · formulario", () => {
  it("pide correo y rol; el rol solo ofrece Coach y Admin, con Coach por defecto", async () => {
    renderPanel();

    expect(emailBox()).toHaveAttribute("type", "email");
    expect(within(roleSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Coach", "Admin"]);
    expect(roleSelect()).toHaveValue("coach");
    expect(within(dialog()).getByText("Los socios entran al portal desde su ficha; aquí se crean solo cuentas del equipo.")).toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("sin correo o con uno inválido no llama al api", async () => {
    const { mock, user } = renderPanel();

    await user.click(createButton());
    expect(await within(dialog()).findByText("Escribe el correo del usuario.")).toBeInTheDocument();
    await user.type(emailBox(), "carlos");
    await user.click(createButton());
    expect(await within(dialog()).findByText("Escribe un correo válido, por ejemplo ana@correo.com.")).toBeInTheDocument();
    expect(mock.callsTo("POST /users")).toHaveLength(0);
  });

  it("envía el correo recortado y el rol elegido", async () => {
    const { mock, user } = renderPanel();

    await user.selectOptions(roleSelect(), "Admin");
    await create(user, "  nueva@apex.test ");

    await screen.findByRole("textbox", { name: "Enlace de activación" });
    expect(mock.callsTo("POST /users")[0]?.body).toEqual({ email: "nueva@apex.test", role: "admin" });
  });

  it("mientras crea el botón dice 'Creando…' y está deshabilitado", async () => {
    const { user } = renderPanel({ "POST /users": () => new Promise(() => undefined) });

    await create(user);

    expect(await within(dialog()).findByRole("button", { name: "Creando…" })).toBeDisabled();
  });
});

describe("NewUserPanel · 201 con el enlace de activación", () => {
  it("muestra el enlace en solo lectura, cuándo vence y cómo entregarlo", async () => {
    const { user } = renderPanel();

    await create(user);

    expect(await within(dialog()).findByText("Usuario creado: carlos@apex.test")).toBeInTheDocument();
    expect(linkBox()).toHaveValue(URL_ACTIVACION);
    expect(linkBox()).toHaveAttribute("readonly");
    expect(within(dialog()).getByText("Entrega este enlace por un medio seguro; vence en 72 horas.")).toBeInTheDocument();
    expect(within(dialog()).getByText("Vence el 25 oct 2026, 2:30 p. m. Al cerrar este panel ya no se puede volver a ver.")).toBeInTheDocument();
    expect(within(dialog()).queryByRole("button", { name: /Crear usuario/ })).not.toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("'Copiar' copia el enlace al portapapeles y lo confirma", async () => {
    const { user } = renderPanel();
    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });
    const write = vi.spyOn(navigator.clipboard, "writeText");

    await user.click(within(dialog()).getByRole("button", { name: "Copiar" }));

    expect(write).toHaveBeenCalledWith(URL_ACTIVACION);
    expect(await within(dialog()).findByRole("status")).toHaveTextContent("Enlace copiado.");
  });

  it("si el portapapeles falla, pide copiarlo a mano", async () => {
    const { user } = renderPanel();
    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denegado"));

    await user.click(within(dialog()).getByRole("button", { name: "Copiar" }));

    expect(await within(dialog()).findByRole("status")).toHaveTextContent("No pudimos copiar el enlace. Selecciónalo y cópialo a mano.");
  });

  it("invalida la lista de usuarios para que aparezca el nuevo", async () => {
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { user } = renderPanel({}, queryClient);

    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["users"] });
  });

  it("L-7: la mutación usa gcTime 0 y al cerrar el enlace desaparece de la pantalla y de la caché", async () => {
    const { queryClient, user } = renderPanel();
    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });
    const [mutation] = queryClient.getMutationCache().getAll();
    expect(mutation?.options.gcTime).toBe(0);
    expect(JSON.stringify(mutation?.state.data)).toContain(URL_ACTIVACION);

    await user.click(within(dialog()).getByRole("button", { name: "Listo" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(document.body.innerHTML).not.toContain(URL_ACTIVACION);
    await user.click(screen.getByRole("button", { name: "Abrir alta" }));
    expect(emailBox()).toHaveValue("");
    expect(screen.queryByRole("textbox", { name: "Enlace de activación" })).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(URL_ACTIVACION);
  });

  it("cerrar con ✕ también descarta el enlace", async () => {
    const { queryClient, user } = renderPanel();
    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });

    await user.click(within(dialog()).getByRole("button", { name: "Cerrar" }));
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });

    expect(document.body.innerHTML).not.toContain(URL_ACTIVACION);
  });
});

describe("NewUserPanel · errores", () => {
  it("409 email_taken va bajo el correo con enlace al usuario existente", async () => {
    const { user } = renderPanel({
      "POST /users": { status: 409, body: { error: { code: "email_taken", message: "Ya existe una cuenta con este correo.", field: "email", existing_id: EXISTING_ID } } },
    });

    await create(user, "ana@apex.test");

    expect(await within(dialog()).findByText(/Ya existe una cuenta con este correo\./)).toBeInTheDocument();
    expect(emailBox()).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog()).getByRole("link", { name: "Ver el usuario existente" })).toHaveAttribute("href", `/sistema/usuarios?usuario=${EXISTING_ID}`);
    expect(emailBox()).toHaveValue("ana@apex.test");
  });

  it("un 409 sin existing_id muestra el error sin enlace", async () => {
    const { user } = renderPanel({
      "POST /users": { status: 409, body: { error: { code: "email_taken", message: "Ya existe una cuenta con este correo.", field: "email" } } },
    });

    await create(user, "ana@apex.test");

    expect(await within(dialog()).findByText("Ya existe una cuenta con este correo.")).toBeInTheDocument();
    expect(within(dialog()).queryByRole("link")).not.toBeInTheDocument();
  });

  it("422 de email se marca en el campo", async () => {
    const { user } = renderPanel({
      "POST /users": { status: 422, body: { error: { code: "validation_error", message: "value is not a valid email", field: "email" } } },
    });

    await create(user, "ana@apex.test");

    expect(await within(dialog()).findByText("El servidor no aceptó este correo. Revísalo e intenta de nuevo.")).toBeInTheDocument();
  });

  it("403 explica que solo un admin crea usuarios", async () => {
    const { user } = renderPanel({ "POST /users": { status: 403, body: { error: { code: "forbidden", message: "x" } } } });

    await create(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Solo un administrador puede crear usuarios. Si lo necesitas, pídeselo a uno.");
  });

  it("5xx y red explican qué hacer y conservan lo escrito", async () => {
    const { user } = renderPanel({ "POST /users": { status: 500, body: { error: { code: "internal", message: "x" } } } });

    await create(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos crear el usuario. Intenta de nuevo en un momento.");
    expect(emailBox()).toHaveValue("carlos@apex.test");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await user.click(createButton());
    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("una respuesta 201 sin enlace es un error, no un alta a medias", async () => {
    const { user } = renderPanel({ "POST /users": { status: 201, body: { user: { id: "x" } } } });

    await create(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
  });
});

describe("NewUserPanel · cerrar sin crear", () => {
  it("con el correo escrito pide confirmar y luego vuelve vacío", async () => {
    const { user } = renderPanel();

    await user.type(emailBox(), "carlos@apex.test");
    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));
    await user.click(screen.getByRole("button", { name: "Descartar cambios" }));
    await user.click(screen.getByRole("button", { name: "Abrir alta" }));

    expect(emailBox()).toHaveValue("");
  });
});

describe("NewUserPanel · más casos de error", () => {
  it("429 pide esperar y otro 4xx pide revisar los datos", async () => {
    const { user } = renderPanel({ "POST /users": { status: 429, body: { error: { code: "rate_limited", message: "x" } } } });

    await create(user);
    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera un momento y vuelve a intentarlo.");
  });

  it("un 400 sin campo da el mensaje genérico", async () => {
    const { user } = renderPanel({ "POST /users": { status: 400, body: { error: { code: "bad_request", message: "x" } } } });

    await create(user);
    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos crear el usuario. Revisa los datos e intenta de nuevo.");
  });

  it("422 de role se marca en el rol", async () => {
    const { user } = renderPanel({ "POST /users": { status: 422, body: { error: { code: "validation_error", message: "x", field: "role" } } } });

    await create(user);
    expect(await within(dialog()).findByText("Elige un rol: Coach o Admin.")).toBeInTheDocument();
  });

  it("sin portapapeles en el navegador pide copiarlo a mano", async () => {
    const { user } = renderPanel();
    await create(user);
    await screen.findByRole("textbox", { name: "Enlace de activación" });
    const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });

    await user.click(within(dialog()).getByRole("button", { name: "Copiar" }));

    expect(await within(dialog()).findByRole("status")).toHaveTextContent("No pudimos copiar el enlace. Selecciónalo y cópialo a mano.");
    if (original) Object.defineProperty(navigator, "clipboard", original);
  });
});

describe("NewUserPanel · correcciones de la revisión", () => {
  it("no se cierra mientras el alta está en curso: el enlace, que viaja una sola vez, no se pierde", async () => {
    let release: (() => void) | null = null;
    const { user } = renderPanel({
      "POST /users": () =>
        new Promise((resolve) => {
          release = () => {
            resolve(CREATED);
          };
        }),
    });

    await create(user);
    await within(dialog()).findByRole("button", { name: "Creando…" });
    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));
    await user.keyboard("{Escape}");
    expect(dialog()).toBeInTheDocument();

    await act(async () => {
      release?.();
      await Promise.resolve();
    });
    expect(await within(dialog()).findByRole("textbox", { name: "Enlace de activación" })).toHaveValue(URL_ACTIVACION);
  });

  it("'Ver el usuario existente' navega dentro de la app y cierra el panel", async () => {
    const { user } = renderPanel({
      "POST /users": { status: 409, body: { error: { code: "email_taken", message: "x", field: "email", existing_id: EXISTING_ID } } },
    });

    await create(user, "ana@apex.test");
    await user.click(await within(dialog()).findByRole("link", { name: "Ver el usuario existente" }));

    expect(screen.getByTestId("where")).toHaveTextContent(`/sistema/usuarios?usuario=${EXISTING_ID}`);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
