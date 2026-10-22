// S2-F4a · US-045 (front): "Mi cuenta" del TopBar.
// - SidePanel "Mi cuenta" con el correo, el rol y el gimnasio de GET /auth/me y el cambio de
//   contraseña (actual, nueva de 12 a 128 caracteres y su confirmación).
// - Un 422 con field current_password o new_password se muestra bajo su campo.
// - El 200 (AccessTokenOut, S2-D37) deja el access nuevo en la sesión con setSession y lo
//   publica por el canal apex-auth para las demás pestañas.
// - El éxito cierra el panel y avisa "Contraseña actualizada".
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { clearSession, getAccessToken, getSession, installSessionBridge, resetSessionForTests } from "../../../core/auth/session";
import { installTabDoubles, posted, resetTabDoubles } from "../../../test/authChannel";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, TEST_TOKEN } from "../../../test/session";
import { ChangePasswordPanel } from "./ChangePasswordPanel";

const CURRENT = "Clave-inicial-2026";
const NEXT = "Clave-nueva-segura-2026";

const ME = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "admin@apex.test",
  role: "admin",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};

const ACCESS_OUT = { access_token: "access-nuevo", token_type: "bearer", expires_in: 900 };

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
        Abrir mi cuenta
      </button>
      <ChangePasswordPanel
        open={open}
        onClose={() => {
          setOpen(false);
        }}
      />
    </main>
  );
}

function renderPanel(handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "GET /auth/me": { status: 200, body: ME }, "POST /auth/me/password": { status: 200, body: ACCESS_OUT }, ...handlers });
  const queryClient = testQueryClient();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { mock, queryClient, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "Mi cuenta" });
const currentBox = () => screen.getByLabelText(/^Contraseña actual/);
const newBox = () => screen.getByLabelText(/^Contraseña nueva/);
const confirmBox = () => screen.getByLabelText(/^Repite la contraseña nueva/);
const saveButton = () => within(dialog()).getByRole("button", { name: /Cambiar contraseña|Guardando/ });

async function fill(user: ReturnType<typeof userEvent.setup>, current = CURRENT, next = NEXT, confirm = next): Promise<void> {
  await user.type(currentBox(), current);
  await user.type(newBox(), next);
  await user.type(confirmBox(), confirm);
}

let uninstall: (() => void) | null = null;

beforeEach(() => {
  resetSessionForTests();
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  uninstall?.();
  uninstall = null;
  resetTabDoubles();
  resetSessionForTests();
  vi.unstubAllGlobals();
});

describe("ChangePasswordPanel · mi cuenta", () => {
  it("muestra el correo, el rol y el gimnasio de GET /auth/me", async () => {
    const { mock } = renderPanel();

    expect(dialog()).toBeInTheDocument();
    const account = await within(dialog()).findByRole("list", { name: "Datos de tu cuenta" });
    expect(account).toHaveTextContent("admin@apex.test");
    expect(account).toHaveTextContent("Admin");
    expect(account).toHaveTextContent("Box Norte");
    expect(mock.callsTo("GET /auth/me")).toHaveLength(1);
  });

  it("mientras carga lo dice y, si me falla, explica qué hacer sin bloquear el cambio", async () => {
    renderPanel({ "GET /auth/me": { status: 500, body: { error: { code: "internal", message: "x" } } } });

    expect(within(dialog()).getByText("Cargando los datos de tu cuenta…")).toBeInTheDocument();
    expect(await within(dialog()).findByText("No pudimos cargar los datos de tu cuenta. Cierra el panel y vuelve a abrirlo.")).toBeInTheDocument();
    expect(currentBox()).toBeEnabled();
  });

  it("los tres campos son de contraseña con su autocompletado y la política a la vista", () => {
    renderPanel();

    expect(currentBox()).toHaveAttribute("type", "password");
    expect(currentBox()).toHaveAttribute("autocomplete", "current-password");
    expect(newBox()).toHaveAttribute("autocomplete", "new-password");
    expect(confirmBox()).toHaveAttribute("autocomplete", "new-password");
    expect(within(dialog()).getByText("Entre 12 y 128 caracteres. Evita las contraseñas comunes.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    renderPanel();
    await within(dialog()).findByRole("list", { name: "Datos de tu cuenta" });

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("ChangePasswordPanel · validación (Zod)", () => {
  it("vacío marca los tres campos y no llama al api", async () => {
    const { mock, user } = renderPanel();

    await user.click(saveButton());

    expect(await screen.findByText("Escribe tu contraseña actual.")).toBeInTheDocument();
    expect(screen.getByText("Escribe la contraseña nueva.")).toBeInTheDocument();
    expect(screen.getByText("Repite la contraseña nueva.")).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/me/password")).toHaveLength(0);
  });

  it("una nueva de menos de 12 caracteres se rechaza antes de enviar", async () => {
    const { mock, user } = renderPanel();

    await fill(user, CURRENT, "corta-123", "corta-123");
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña nueva debe tener al menos 12 caracteres.")).toBeInTheDocument();
    expect(newBox()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("POST /auth/me/password")).toHaveLength(0);
  });

  it("una nueva de más de 128 caracteres se rechaza", async () => {
    const { user } = renderPanel();
    const long = "a".repeat(129);

    await fill(user, CURRENT, long, long);
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña nueva admite hasta 128 caracteres.")).toBeInTheDocument();
  });

  it("la confirmación distinta se marca en su campo", async () => {
    const { mock, user } = renderPanel();

    await fill(user, CURRENT, NEXT, `${NEXT}x`);
    await user.click(saveButton());

    expect(await screen.findByText("Las contraseñas no coinciden. Escribe la misma en los dos campos.")).toBeInTheDocument();
    expect(confirmBox()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("POST /auth/me/password")).toHaveLength(0);
  });

  it("la nueva igual a la actual se rechaza", async () => {
    const { user } = renderPanel();

    await fill(user, NEXT, NEXT, NEXT);
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña nueva debe ser distinta de la actual.")).toBeInTheDocument();
  });
});

describe("ChangePasswordPanel · errores del api", () => {
  it("422 current_password se muestra bajo la contraseña actual", async () => {
    const { user } = renderPanel({
      "POST /auth/me/password": { status: 422, body: { error: { code: "invalid_current_password", message: "La contraseña actual no es correcta.", field: "current_password" } } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña actual no es correcta. Revísala e intenta de nuevo.")).toBeInTheDocument();
    expect(currentBox()).toHaveAttribute("aria-invalid", "true");
    expect(currentBox()).toHaveFocus();
    expect(dialog()).toBeInTheDocument();
  });

  it("422 new_password se muestra bajo la contraseña nueva con el motivo del api", async () => {
    const { user } = renderPanel({
      "POST /auth/me/password": { status: 422, body: { error: { code: "weak_password", message: "La contraseña es demasiado débil.", field: "new_password" } } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña es demasiado débil. Elige otra.")).toBeInTheDocument();
    expect(newBox()).toHaveAttribute("aria-invalid", "true");
  });

  it("429 avisa la espera de Retry-After sin cerrar la sesión", async () => {
    const { user } = renderPanel({
      "POST /auth/me/password": { status: 429, body: { error: { code: "rate_limited", message: "x" } }, headers: { "Retry-After": "30" } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera 30 s y vuelve a intentarlo.");
    expect(getSession().status).toBe("authenticated");
    expect(getAccessToken()).toBe(TEST_TOKEN);
  });

  it("sin red explica qué pasó y qué hacer", async () => {
    const { user } = renderPanel();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("un 5xx pide intentar más tarde", async () => {
    const { user } = renderPanel({ "POST /auth/me/password": { status: 500, body: { error: { code: "internal", message: "x" } } } });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("El servidor tuvo un problema. Intenta de nuevo en un momento.");
  });
});

describe("ChangePasswordPanel · éxito (S2-D37)", () => {
  it("envía actual y nueva, toma el access nuevo con setSession y lo publica por apex-auth", async () => {
    installTabDoubles();
    uninstall = installSessionBridge();
    const { mock, user } = renderPanel();

    await fill(user);
    await user.click(saveButton());

    await waitFor(() => {
      expect(getAccessToken()).toBe("access-nuevo");
    });
    expect(mock.callsTo("POST /auth/me/password")[0]?.body).toEqual({ current_password: CURRENT, new_password: NEXT });
    expect(getSession().user?.mustChangePassword).toBe(false);
    const tokens = posted.filter((m) => m.channel === "apex-auth" && (m.data as { type: string }).type === "token");
    expect(tokens).toHaveLength(1);
    expect(tokens[0]?.data).toMatchObject({ type: "token", accessToken: "access-nuevo", expiresIn: 900 });
  });

  it("la petición siguiente sale con el access nuevo", async () => {
    const { mock, user } = renderPanel();

    await fill(user);
    await user.click(saveButton());
    await screen.findByText("Contraseña actualizada");

    expect(mock.callsTo("POST /auth/me/password")[0]?.headers.get("Authorization")).toBe(`Bearer ${TEST_TOKEN}`);
    expect(getAccessToken()).toBe("access-nuevo");
  });

  it("cierra el panel, avisa 'Contraseña actualizada' y al reabrir los campos están vacíos", async () => {
    const { user } = renderPanel();

    await fill(user);
    await user.click(saveButton());

    await screen.findByText("Contraseña actualizada");
    // La región viva existía antes del aviso (se anuncia al llenarse).
    expect(screen.getByRole("status")).toHaveTextContent("Contraseña actualizada");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Abrir mi cuenta" }));
    expect(currentBox()).toHaveValue("");
    expect(newBox()).toHaveValue("");
    expect(screen.queryByText("Contraseña actualizada")).not.toBeInTheDocument();
  });

  it("el aviso se puede cerrar", async () => {
    const { user } = renderPanel();

    await fill(user);
    await user.click(saveButton());
    await screen.findByText("Contraseña actualizada");
    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(screen.queryByText("Contraseña actualizada")).not.toBeInTheDocument();
  });

  it("mientras envía el botón dice 'Guardando…' y no se envía dos veces", async () => {
    let release: (() => void) | null = null;
    const { mock, user } = renderPanel({
      "POST /auth/me/password": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: ACCESS_OUT });
          };
        }),
    });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("button", { name: "Guardando…" })).toBeDisabled();
    await user.click(saveButton());
    expect(mock.callsTo("POST /auth/me/password")).toHaveLength(1);
    await act(async () => {
      release?.();
      await Promise.resolve();
    });
    expect(await screen.findByText("Contraseña actualizada")).toBeInTheDocument();
  });
});

describe("ChangePasswordPanel · cerrar sin guardar", () => {
  it("Cancelar sin cambios cierra y al reabrir no queda nada escrito", async () => {
    const { user } = renderPanel();

    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir mi cuenta" }));

    expect(currentBox()).toHaveValue("");
  });

  it("con algo escrito pide confirmar antes de descartar", async () => {
    const { user } = renderPanel();

    await user.type(currentBox(), "algo");
    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));

    expect(screen.getByRole("dialog", { name: "¿Descartar los cambios?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Descartar cambios" }));
    expect(screen.queryByRole("dialog", { name: "Mi cuenta" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir mi cuenta" }));
    expect(currentBox()).toHaveValue("");
  });
});

describe("ChangePasswordPanel · respuestas con forma inesperada", () => {
  it("un me sin la forma del contrato muestra el error de carga", async () => {
    renderPanel({ "GET /auth/me": { status: 200, body: { id: "x" } } });

    expect(await within(dialog()).findByText("No pudimos cargar los datos de tu cuenta. Cierra el panel y vuelve a abrirlo.")).toBeInTheDocument();
  });

  it("un 200 sin access token no toca la sesión y lo explica", async () => {
    const { user } = renderPanel({ "POST /auth/me/password": { status: 200, body: { ok: true } } });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
    expect(getAccessToken()).toBe(TEST_TOKEN);
  });
});

describe("ChangePasswordPanel · correcciones de la revisión", () => {
  it("no se cierra mientras guarda (Cancelar y Escape esperan a la respuesta)", async () => {
    let release: (() => void) | null = null;
    const { user } = renderPanel({
      "POST /auth/me/password": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 422, body: { error: { code: "invalid_current_password", message: "x", field: "current_password" } } });
          };
        }),
    });

    await fill(user);
    await user.click(saveButton());
    await within(dialog()).findByRole("button", { name: "Guardando…" });
    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));
    await user.keyboard("{Escape}");
    expect(dialog()).toBeInTheDocument();

    await act(async () => {
      release?.();
      await Promise.resolve();
    });
    expect(await screen.findByText("La contraseña actual no es correcta. Revísala e intenta de nuevo.")).toBeInTheDocument();
  });

  it("si la sesión se cierra mientras guarda, no adopta el token ni dice que salió bien", async () => {
    const { user } = renderPanel({
      "POST /auth/me/password": () => {
        clearSession("logout");
        return { status: 200, body: ACCESS_OUT };
      },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(
      "La contraseña se cambió, pero tu sesión se cerró mientras tanto. Inicia sesión con la contraseña nueva.",
    );
    expect(getAccessToken()).toBeNull();
    expect(screen.queryByText("Contraseña actualizada")).not.toBeInTheDocument();
  });

  it("si otra cuenta entró mientras guardaba, el token no se le asigna", async () => {
    const { user } = renderPanel({
      "POST /auth/me/password": () => {
        signInAs("coach");
        return { status: 200, body: ACCESS_OUT };
      },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("tu sesión se cerró mientras tanto");
    expect(getAccessToken()).toBe(TEST_TOKEN);
    expect(getSession().user?.role).toBe("coach");
  });
});
