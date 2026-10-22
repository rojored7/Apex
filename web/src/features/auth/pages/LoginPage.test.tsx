// S2-F3 · US-042 (login): pantalla de Login.html con React Hook Form + Zod.
// - Estados: inicial, enviando (botón deshabilitado), error genérico sobre la tarjeta.
// - 401 siempre "Correo o contraseña incorrectos" (sin distinguir cuenta bloqueada o
//   pendiente); conserva el correo y limpia la contraseña.
// - 429 "Demasiados intentos" con la espera de Retry-After; 403 de Origin, red o 5xx como
//   error genérico; 422 marca el campo.
// - Destino: safeNext(next, rol) o homeFor(rol); /cambiar-clave si must_change_password.
// - Avisos al llegar: cierre de sesión no confirmado (H-1) y sesión vencida.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { clearSession, getAccessToken, getSession, resetSessionForTests } from "../../../core/auth/session";
import { AccessLayout } from "../../../layouts/AccessLayout";
import { fakeTimersUser, restoreRtlTimers, useRtlFakeTimers } from "../../../test/fakeTimers";
import { mockApi, testQueryClient, type MockHandler, type MockReply } from "../../../test/server";
import { signInAs } from "../../../test/session";
import LoginPage from "./LoginPage";

const EMAIL = "ana@apex.test";
const PASSWORD = "Clave-segura-2026";

function loginOut(role: "admin" | "coach" | "member", mustChange = false): MockReply {
  return {
    status: 200,
    body: {
      access_token: `access-${role}`,
      token_type: "bearer",
      expires_in: 900,
      must_change_password: mustChange,
      user: { id: "11111111-1111-4111-8111-111111111111", email: EMAIL, role },
    },
  };
}

const ME = {
  id: "11111111-1111-4111-8111-111111111111",
  email: EMAIL,
  role: "admin",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};

function renderLogin(entry = "/login", handlers: Record<string, MockHandler> = {}, user = userEvent.setup()) {
  const mock = mockApi({ "GET /auth/me": { status: 200, body: ME }, ...handlers });
  const router = createMemoryRouter(
    [
      { element: <AccessLayout />, children: [{ path: "/login", element: <LoginPage /> }] },
      { path: "/", element: <h1>Inicio del panel</h1> },
      { path: "/mi", element: <h1>Portal del socio</h1> },
      { path: "/socios", element: <h1>Lista de socios</h1> },
      { path: "/planes", element: <h1>Planes</h1> },
      { path: "/cambiar-clave", element: <h1>Cambiar contraseña</h1> },
      { path: "/recuperar", element: <h1>Recuperar</h1> },
    ],
    { initialEntries: [entry] },
  );
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, user, ...view };
}

const emailBox = () => screen.getByRole("textbox", { name: "Correo" });
const passwordBox = () => screen.getByLabelText("Contraseña");
const submit = () => screen.getByRole("button", { name: /Entrar|Entrando/ });

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, email = EMAIL, password = PASSWORD): Promise<void> {
  await user.clear(emailBox());
  await user.type(emailBox(), email);
  await user.clear(passwordBox());
  await user.type(passwordBox(), password);
  await user.click(submit());
}

const where = (router: ReturnType<typeof renderLogin>["router"]) => `${router.state.location.pathname}${router.state.location.search}`;

beforeEach(() => {
  resetSessionForTests();
  clearSession("restore_failed");
});

afterEach(() => {
  // Desmontar antes de reiniciar la sesión: así el reinicio no actualiza una página montada.
  cleanup();
  resetSessionForTests();
  vi.unstubAllGlobals();
});

describe("LoginPage · estructura (Login.html)", () => {
  it("muestra la tarjeta de acceso con sus campos, el enlace de recuperación y la nota de destino", async () => {
    const { container } = renderLogin();

    expect(screen.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.getByText("APEX")).toBeInTheDocument();
    expect(emailBox()).toHaveAttribute("type", "email");
    expect(emailBox()).toHaveAttribute("autocomplete", "username");
    expect(passwordBox()).toHaveAttribute("type", "password");
    expect(passwordBox()).toHaveAttribute("autocomplete", "current-password");
    expect(submit()).toHaveAccessibleName("Entrar");
    expect(submit()).toHaveAttribute("type", "submit");
    expect(screen.getByRole("link", { name: "Olvidé mi contraseña" })).toHaveAttribute("href", "/recuperar");
    expect(screen.getByText("Si eres socio, entras al portal. Si eres coach o admin, al panel.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("el foco arranca en el correo", () => {
    renderLogin();

    expect(emailBox()).toHaveFocus();
  });
});

describe("LoginPage · validación (Zod)", () => {
  it("sin datos marca los dos campos y no llama al api", async () => {
    const { mock, user } = renderLogin();

    await user.click(submit());

    expect(await screen.findByText("Escribe tu correo.")).toBeInTheDocument();
    expect(screen.getByText("Escribe tu contraseña.")).toBeInTheDocument();
    expect(emailBox()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("POST /auth/login")).toHaveLength(0);
  });

  it("un correo mal escrito o una contraseña de más de 128 caracteres no se envían", async () => {
    const { mock, user } = renderLogin();

    await fillAndSubmit(user, "ana@", "x".repeat(129));

    expect(await screen.findByText("Escribe un correo válido, por ejemplo ana@correo.com.")).toBeInTheDocument();
    expect(screen.getByText("La contraseña admite hasta 128 caracteres.")).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/login")).toHaveLength(0);
  });
});

describe("LoginPage · éxito", () => {
  it("el admin entra: POST /auth/login con la cookie del mismo origen, sesión en memoria y va a Inicio", async () => {
    const { mock, router, user } = renderLogin("/login", { "POST /auth/login": loginOut("admin") });

    await fillAndSubmit(user, `  ${EMAIL.toUpperCase()} `);

    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
    expect(where(router)).toBe("/");
    const [call] = mock.callsTo("POST /auth/login");
    expect(call?.body).toEqual({ email: EMAIL.toUpperCase(), password: PASSWORD });
    expect(call?.credentials).toBe("same-origin");
    expect(call?.headers.get("Authorization")).toBeNull();
    expect(getSession()).toMatchObject({ status: "authenticated", user: { role: "admin", email: EMAIL } });
    expect(getAccessToken()).toBe("access-admin");
    expect([localStorage, sessionStorage].map((s) => Array.from({ length: s.length }, (_, i) => `${s.key(i) ?? ""}=${s.getItem(s.key(i) ?? "") ?? ""}`).join("|")).join("|")).not.toContain("access-admin");
    await waitFor(() => {
      expect(getSession().user?.gymName).toBe("Box Norte");
    });
  });

  it("con un next seguro del rol vuelve ahí", async () => {
    const { router, user } = renderLogin(`/login?next=${encodeURIComponent("/socios?estado=activo")}`, {
      "POST /auth/login": loginOut("coach"),
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("heading", { name: "Lista de socios" })).toBeInTheDocument();
    expect(where(router)).toBe("/socios?estado=activo");
  });

  it.each([
    ["otro origen", "//evil.example/x"],
    ["URL absoluta", "https://evil.example/"],
    ["barra invertida", "/\\evil.example"],
    ["ruta de otro rol", "/planes"],
    ["ruta pública", "/login"],
  ])("con un next inseguro (%s) va al inicio del rol", async (_caso, next) => {
    const { router, user } = renderLogin(`/login?next=${encodeURIComponent(next)}`, { "POST /auth/login": loginOut("coach") });

    await fillAndSubmit(user);

    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
    expect(where(router)).toBe("/");
  });

  it("el socio va al portal", async () => {
    const { router, user } = renderLogin("/login", {
      "POST /auth/login": loginOut("member"),
      "GET /auth/me": { status: 200, body: { ...ME, role: "member", member_id: "22222222-2222-4222-8222-222222222222" } },
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("heading", { name: "Portal del socio" })).toBeInTheDocument();
    expect(where(router)).toBe("/mi");
  });

  it("con must_change_password va a /cambiar-clave aunque haya next", async () => {
    const { router, user } = renderLogin(`/login?next=${encodeURIComponent("/socios")}`, {
      "POST /auth/login": loginOut("admin", true),
      "GET /auth/me": { status: 200, body: { ...ME, must_change_password: true } },
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("heading", { name: "Cambiar contraseña" })).toBeInTheDocument();
    expect(where(router)).toBe("/cambiar-clave");
    expect(getSession().user?.mustChangePassword).toBe(true);
  });

  it("con la sesión ya abierta no muestra el formulario: va al inicio del rol", async () => {
    signInAs("coach");
    const { router } = renderLogin();

    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
    expect(where(router)).toBe("/");
  });
});

describe("LoginPage · enviando", () => {
  it("deshabilita el botón y anuncia la espera mientras dura la petición", async () => {
    let release: (reply: MockReply) => void = () => undefined;
    const { user } = renderLogin("/login", {
      "POST /auth/login": () =>
        new Promise<MockReply>((resolve) => {
          release = resolve;
        }),
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("button", { name: "Entrando…" })).toBeDisabled();
    expect(submit()).toHaveAttribute("aria-busy", "true");
    await user.click(submit());
    act(() => {
      release(loginOut("admin"));
    });
    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
  });
});

describe("LoginPage · errores", () => {
  it.each(["invalid_credentials", "account_locked", "account_pending"])(
    "401 %s: 'Correo o contraseña incorrectos', conserva el correo y limpia la contraseña",
    async (code) => {
      const { user } = renderLogin("/login", {
        "POST /auth/login": { status: 401, body: { error: { code, message: "mensaje del api" } } },
      });

      await fillAndSubmit(user);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Correo o contraseña incorrectos. Revísalos e intenta de nuevo.");
      expect(alert).not.toHaveTextContent("mensaje del api");
      expect(emailBox()).toHaveValue(EMAIL);
      expect(passwordBox()).toHaveValue("");
      expect(passwordBox()).toHaveFocus();
      expect(getSession().status).toBe("anonymous");
      expect(submit()).toBeEnabled();
    },
  );

  it("429 muestra la espera de Retry-After y bloquea el botón hasta que pasa", async () => {
    useRtlFakeTimers();
    try {
      const user = fakeTimersUser();
      const { mock } = renderLogin(
        "/login",
        {
          "POST /auth/login": {
            status: 429,
            body: { error: { code: "rate_limited", message: "Too many" } },
            headers: { "Retry-After": "3" },
          },
        },
        user,
      );

      await fillAndSubmit(user);

      expect(await screen.findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera 3 s y vuelve a intentarlo.");
      await waitFor(() => {
        expect(passwordBox()).toHaveFocus();
      });
      expect(submit()).toBeDisabled();
      expect(emailBox()).toHaveValue(EMAIL);
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      expect(screen.getByRole("alert")).toHaveTextContent("Espera 2 s");
      // Cada segundo es un temporizador nuevo (el efecto lo agenda tras pintar).
      for (let i = 0; i < 2; i += 1) {
        act(() => {
          vi.advanceTimersByTime(1_000);
        });
      }
      expect(submit()).toBeEnabled();
      expect(screen.getByRole("alert")).toHaveTextContent("Ya puedes intentarlo de nuevo.");
      expect(mock.callsTo("POST /auth/login")).toHaveLength(1);
    } finally {
      restoreRtlTimers();
    }
  });

  it("429 sin Retry-After pide esperar un momento", async () => {
    const { user } = renderLogin("/login", {
      "POST /auth/login": { status: 429, body: { error: { code: "rate_limited", message: "Too many" } } },
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera un momento y vuelve a intentarlo.");
    expect(submit()).toBeEnabled();
  });

  it.each<[string, MockReply, string]>([
    [
      "403 por Origin ajeno",
      { status: 403, body: { error: { code: "forbidden", message: "Origin" } } },
      "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo.",
    ],
    [
      "500",
      { status: 500, body: { error: { code: "internal_error", message: "boom" } } },
      "El servidor tuvo un problema. Intenta de nuevo en un momento.",
    ],
    ["502 de Nginx", { status: 502, body: "<html>" }, "El servidor tuvo un problema. Intenta de nuevo en un momento."],
    [
      "respuesta con forma inesperada",
      { status: 200, body: { token: "x" } },
      "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo.",
    ],
  ])("%s: error genérico sin abrir sesión", async (_caso, reply, message) => {
    const { user } = renderLogin("/login", { "POST /auth/login": reply });

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).not.toHaveTextContent("Correo o contraseña incorrectos");
    expect(getSession().status).toBe("anonymous");
    expect(getAccessToken()).toBeNull();
  });

  it("sin red: mensaje de conexión", async () => {
    const { user } = renderLogin();
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("422 con field marca el campo", async () => {
    const { user } = renderLogin("/login", {
      "POST /auth/login": { status: 422, body: { error: { code: "validation_error", message: "bad", field: "email" } } },
    });

    await fillAndSubmit(user);

    expect(await screen.findByText("Revisa el correo: el servidor no lo aceptó.")).toBeInTheDocument();
    expect(emailBox()).toHaveAttribute("aria-invalid", "true");
  });

  it("422 sin field da el error general de datos", async () => {
    const { user } = renderLogin("/login", {
      "POST /auth/login": { status: 422, body: { error: { code: "validation_error", message: "bad" } } },
    });

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Revisa el correo y la contraseña e intenta de nuevo.");
  });

  it("el error se borra al volver a enviar", async () => {
    const { user } = renderLogin("/login", {
      "POST /auth/login": { status: 401, body: { error: { code: "invalid_credentials", message: "x" } } },
    });
    await fillAndSubmit(user);
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    mockApi({ "POST /auth/login": loginOut("admin"), "GET /auth/me": { status: 200, body: ME } });
    await user.type(passwordBox(), PASSWORD);
    await user.click(submit());

    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
  });
});

describe("LoginPage · avisos al llegar", () => {
  it("H-1: tras un cierre no confirmado avisa que no se pudo cerrar la sesión en el servidor", async () => {
    clearSession("logout_unconfirmed");
    const { container } = renderLogin();

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("No se pudo cerrar la sesión en el servidor.");
    expect(notice).toHaveTextContent("Si usas un equipo compartido, cierra el navegador.");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("tras un cierre confirmado no hay aviso", () => {
    clearSession("logout");
    renderLogin();

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("con la sesión vencida pide volver a entrar", () => {
    clearSession("expired");
    renderLogin(`/login?next=${encodeURIComponent("/socios")}`);

    expect(within(screen.getByRole("status")).getByText("Tu sesión venció. Vuelve a iniciar sesión.")).toBeInTheDocument();
  });
});
