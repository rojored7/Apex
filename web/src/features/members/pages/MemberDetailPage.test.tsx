// S3-F1 · US-073 y US-076 (front): /socios/:id (Socio_Ficha.html).
// - PageHeader con el nombre, el StatusTag de la membresía y la línea "Socio desde … · plan · vence";
//   migas Socios › nombre; acciones por rol con useCan (Editar con members.update, Vender con
//   memberships.sell, Dar de baja solo con members.delete).
// - Tabs con las pestañas de la ficha: Datos es la ruta hija índice (<Outlet />, S3-D65); Membresías
//   y Pagos son rutas hijas que navegan y montan su pestaña (S3-F7; deshabilitadas si su ruta no está
//   disponible, isPageAvailable); Historial (S4A-F2, US-106) es hija de members, habilitada y la última.
// - Los cinco sensibles enmascarados con el texto del api y "Mostrar"; aviso si falta la
//   autorización de datos (Q16); un dado de baja es de solo lectura con "Dado de baja" y
//   "Reactivar" solo para el admin; 404 "Socio no encontrado"; error con "Reintentar".
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, DELETED_OVERRIDES, DETAIL_PATH, DUPLICATE_ID, MEMBER_ID, memberDetailBody, ok, REVEAL_PATH, renderMemberDetail } from "../../../test/memberDetail";
import { setViewportWidth, testQueryClient } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

// S3-F7: una prueba simula una pestaña cuya ruta hija no está disponible (su feature deshabilitada);
// las demás usan la regla real.
const availability = vi.hoisted(() => ({ blocked: new Set<string>() }));
vi.mock("../../../core/auth/routeAccess", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../core/auth/routeAccess")>();
  return {
    ...actual,
    isPageAvailable: (...args: Parameters<typeof actual.isPageAvailable>) => !availability.blocked.has(args[1].split("/").at(-1) ?? "") && actual.isPageAvailable(...args),
  };
});

const header = (): HTMLElement => screen.getByRole("heading", { level: 1 }).closest("header") as HTMLElement;
const actionNames = (): string[] => {
  const region = header();
  return within(region)
    .queryAllByRole("link")
    .concat(within(region).queryAllByRole("button"))
    .map((el) => el.textContent)
    .filter((text) => ["Editar", "Vender membresía", "Dar de baja", "Reactivar"].includes(text))
    .sort();
};

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
  availability.blocked.clear();
});

describe("MemberDetailPage · encabezado (Socio_Ficha.html)", () => {
  it("pide GET /members/{id} y muestra el nombre, la membresía y las migas", async () => {
    const { mock } = renderMemberDetail();

    expect(await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ })).toBeInTheDocument();
    expect(mock.callsTo(`GET ${DETAIL_PATH}`)).toHaveLength(1);
    const crumbs = screen.getByRole("navigation", { name: "Migas" });
    expect(within(crumbs).getByRole("link", { name: "Socios" })).toHaveAttribute("href", "/socios");
    expect(within(crumbs).getByText("Laura Gómez")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Al día")).toBeInTheDocument();
    expect(screen.getByText("Socio desde 12 mar 2026 · Mensual · vence 28 oct 2026")).toBeInTheDocument();
  });

  it("sin membresía dice 'Sin membresía' y la etiqueta 'Sin plan'", async () => {
    renderMemberDetail(undefined, {
      handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ membership_status: "none", plan_name: null, membership_end_date: null })) },
    });

    expect(await screen.findByText("Socio desde 12 mar 2026 · Sin membresía")).toBeInTheDocument();
    expect(screen.getByText("Sin plan")).toBeInTheDocument();
  });

  it("mientras carga lo anuncia", () => {
    renderMemberDetail(undefined, { handlers: { [`GET ${DETAIL_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getByRole("status")).toHaveTextContent("Cargando la ficha del socio…");
  });
});

describe("MemberDetailPage · acciones por rol (useCan)", () => {
  it("el admin ve Editar, Vender membresía y Dar de baja; Vender enlaza a la venta con el socio", async () => {
    renderMemberDetail();
    await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ });

    expect(actionNames()).toEqual(["Dar de baja", "Editar", "Vender membresía"]);
    expect(screen.getByRole("link", { name: "Editar" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/editar`);
    expect(screen.getByRole("link", { name: "Vender membresía" })).toHaveAttribute("href", `/membresias/vender?socio=${MEMBER_ID}`);
  });

  it("el coach ve Editar y Vender, pero no Dar de baja ni Reactivar", async () => {
    signInAs("coach");
    renderMemberDetail();
    await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ });

    expect(actionNames()).toEqual(["Editar", "Vender membresía"]);
  });
});

describe("MemberDetailPage · pestañas (rutas hijas, S3-D65)", () => {
  it("Datos es la activa en /socios/:id; Membresías, Pagos (S3-F7) e Historial (S4A-F2) están habilitadas; las demás, deshabilitadas, e Historial es la última", async () => {
    renderMemberDetail();
    const tablist = await screen.findByRole("tablist", { name: "Secciones del socio" });
    const tabs = within(tablist).getAllByRole("tab");

    expect(tabs.map((tab) => tab.firstChild?.textContent)).toEqual(["Datos", "Membresías", "Pagos", "Asistencia", "Resultados", "Atleta", "Avisos", "Adjuntos", "Historial"]);
    expect(within(tablist).getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
    for (const name of ["Membresías", "Pagos", "Historial"]) expect(within(tablist).getByRole("tab", { name })).not.toHaveAttribute("aria-disabled");
    for (const name of [/^Asistencia/, /^Resultados/, /^Atleta/, /^Avisos/, /^Adjuntos/]) {
      expect(within(tablist).getByRole("tab", { name })).toHaveAttribute("aria-disabled", "true");
    }
    expect(within(tablist).getByRole("tab", { name: /^Asistencia/ })).toHaveTextContent("Disponible en v0.4");
    expect(within(tablist).getByRole("tab", { name: /^Avisos/ })).toHaveTextContent("Disponible en v0.2");
    expect(within(tablist).getByRole("tab", { name: "Historial" })).not.toHaveTextContent("Disponible en");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Datos de contacto");
  });

  it("S4A-F2: Historial navega a /socios/:id/historial y monta la pestaña con GET /members/{id}/audit sin volver a pedir la ficha", async () => {
    const { mock, user } = renderMemberDetail();
    await user.click(await screen.findByRole("tab", { name: "Historial" }));

    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}/historial`);
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    expect(await within(screen.getByRole("tabpanel")).findByText("Sin cambios registrados")).toBeInTheDocument();
    expect(mock.callsTo(`GET ${DETAIL_PATH}/audit`).some((call) => new URL(call.url, "http://apex.test").searchParams.get("limit") === "25")).toBe(true);
    expect(mock.callsTo(`GET ${DETAIL_PATH}`)).toHaveLength(1);
  });

  it("S4A-F2: el coach también ve la pestaña Historial habilitada (members.history.view)", async () => {
    signInAs("coach");
    renderMemberDetail(`/socios/${MEMBER_ID}/historial`);

    expect(await screen.findByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Historial" })).not.toHaveAttribute("aria-disabled");
  });

  it("pulsar Datos estando en Datos no cambia de ruta (la hija índice vive en la ruta del padre)", async () => {
    const { user } = renderMemberDetail();
    await user.click(await screen.findByRole("tab", { name: "Datos" }));

    expect(screen.getByTestId("location")).toHaveTextContent(`/socios/${MEMBER_ID}`);
    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}`);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Datos de contacto");
  });

  it("S3-F7: Membresías navega a /socios/:id/membresias y monta su pestaña en el <Outlet /> sin volver a pedir la ficha", async () => {
    const { mock, user } = renderMemberDetail();
    await user.click(await screen.findByRole("tab", { name: "Membresías" }));

    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}/membresias`);
    expect(screen.getByRole("tab", { name: "Membresías" })).toHaveAttribute("aria-selected", "true");
    expect(await within(screen.getByRole("tabpanel")).findByText("Este socio no tiene membresías.")).toBeInTheDocument();
    expect(mock.callsTo(`GET ${DETAIL_PATH}/memberships`)).toHaveLength(1);
    expect(mock.callsTo(`GET ${DETAIL_PATH}`)).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: /Laura Gómez/ })).toBeInTheDocument();
  });

  it("S3-F7: Pagos navega a /socios/:id/pagos, monta su pestaña y vuelve a Datos sin segmento", async () => {
    const { mock, user } = renderMemberDetail();
    await user.click(await screen.findByRole("tab", { name: "Pagos" }));

    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}/pagos`);
    expect(await within(screen.getByRole("tabpanel")).findByText("Este socio no tiene pagos.")).toBeInTheDocument();
    expect(mock.callsTo(`GET ${DETAIL_PATH}/payments`)).toHaveLength(1);

    await user.click(screen.getByRole("tab", { name: "Datos" }));
    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}`);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Datos de contacto");
  });

  it("S3-F7: entrar directo a /socios/:id/pagos selecciona Pagos; la pestaña lee el socio dado de baja de la ficha", async () => {
    renderMemberDetail(`/socios/${MEMBER_ID}/pagos`, {
      handlers: {
        [`GET ${DETAIL_PATH}`]: ok(memberDetailBody(DELETED_OVERRIDES)),
        [`GET ${DETAIL_PATH}/payments`]: ok({ items: [], total: 0, limit: 25, offset: 0 }),
      },
    });

    expect(await screen.findByRole("tab", { name: "Pagos" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Este socio no tiene pagos.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Registrar pago" })).not.toBeInTheDocument();
  });

  it("S3-F7: cambiar de pestaña no arrastra la página de la lista anterior (offset)", async () => {
    const { user } = renderMemberDetail(`/socios/${MEMBER_ID}/membresias?offset=25`);
    await user.click(await screen.findByRole("tab", { name: "Pagos" }));

    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}/pagos`);
  });

  it("S3-F7: una pestaña cuya ruta hija no está disponible (feature deshabilitada) se ve deshabilitada", async () => {
    availability.blocked.add("pagos");
    renderMemberDetail();
    const tablist = await screen.findByRole("tablist", { name: "Secciones del socio" });

    expect(within(tablist).getByRole("tab", { name: /^Pagos/ })).toHaveAttribute("aria-disabled", "true");
    expect(within(tablist).getByRole("tab", { name: /^Pagos/ })).toHaveTextContent("No disponible");
    expect(within(tablist).getByRole("tab", { name: /^Pagos/ })).not.toHaveTextContent("Disponible en");
    expect(within(tablist).getByRole("tab", { name: "Membresías" })).not.toHaveAttribute("aria-disabled");
  });
});

describe("MemberDetailPage · Datos (US-073, US-074)", () => {
  it("muestra los cinco campos sensibles con el enmascarado del api y un 'Mostrar' por cada uno", async () => {
    const { mock } = renderMemberDetail();
    const panel = await screen.findByRole("tabpanel");

    for (const masked of ["CC •••• 4417", "••/••/1991", "••• ••• 4567", "l•••@•••.co", "Registrado"]) expect(within(panel).getByText(masked)).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: "Mostrar" })).toHaveLength(5);
    expect(within(panel).getByText("Femenino")).toBeInTheDocument();
    expect(mock.callsTo(`POST ${REVEAL_PATH}`)).toHaveLength(0);
  });

  it("Mostrar del teléfono pide solo ese campo y lo muestra en claro", async () => {
    const { mock, user } = renderMemberDetail();
    const panel = await screen.findByRole("tabpanel");
    const phone = within(panel).getByText("••• ••• 4567").closest("div") as HTMLElement;

    await user.click(within(phone).getByRole("button", { name: "Mostrar" }));

    expect(await within(panel).findByText("3001234567")).toBeInTheDocument();
    expect(mock.callsTo(`POST ${REVEAL_PATH}`).map((c) => c.body)).toEqual([{ field: "phone" }]);
  });

  it("un campo vacío dice 'Sin dato' y no ofrece Mostrar", async () => {
    renderMemberDetail(undefined, { handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ email: null, sex: null })) } });
    const panel = await screen.findByRole("tabpanel");

    expect(within(panel).getAllByRole("button", { name: "Mostrar" })).toHaveLength(4);
    expect(within(panel).getByText("Sin dato")).toBeInTheDocument();
    expect(within(panel).getByText("Sin indicar")).toBeInTheDocument();
  });

  it("con la autorización registrada la muestra con su fecha y no avisa", async () => {
    renderMemberDetail();
    const panel = await screen.findByRole("tabpanel");

    expect(within(panel).getByText("Registrada el 12 mar 2026 · versión 2026-03")).toBeInTheDocument();
    expect(screen.queryByText("Sin autorización de datos registrada")).not.toBeInTheDocument();
  });

  it("sin autorización de datos avisa en la ficha (Q16)", async () => {
    renderMemberDetail(undefined, {
      handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ data_consent_at: null, data_consent_version: null, warnings: ["data_consent_missing"] })) },
    });

    expect(await screen.findByText("Sin autorización de datos registrada")).toBeInTheDocument();
    expect(screen.getByText(/Edita el socio y marca "Registrar autorización"/)).toBeInTheDocument();
  });

  it("al volver de la edición avisa 'Cambios guardados'", async () => {
    renderMemberDetail(`/socios/${MEMBER_ID}`, { state: { memberUpdated: true } });

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
  });
});

describe("MemberDetailPage · dado de baja (US-076, N-20)", () => {
  const deleted = { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody(DELETED_OVERRIDES)) };

  it("es de solo lectura: etiqueta 'Dado de baja' con la fecha y sin Editar, Vender ni Dar de baja; Mostrar sigue", async () => {
    renderMemberDetail(undefined, { handlers: deleted });
    await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ });

    expect(within(header()).getByText("Dado de baja")).toBeInTheDocument();
    expect(screen.getByText(/Dado de baja el 20 oct 2026/)).toBeInTheDocument();
    expect(actionNames()).toEqual(["Reactivar"]);
    expect(within(screen.getByRole("tabpanel")).getAllByRole("button", { name: "Mostrar" })).toHaveLength(5);
  });

  it("el coach no ve Reactivar", async () => {
    signInAs("coach");
    renderMemberDetail(undefined, { handlers: deleted });
    await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ });

    expect(actionNames()).toEqual([]);
  });

  it("Dar de baja abre la confirmación, hace DELETE y la ficha queda de solo lectura con aviso", async () => {
    let gone = false;
    const { mock, user } = renderMemberDetail(undefined, {
      handlers: {
        [`GET ${DETAIL_PATH}`]: () => ok(memberDetailBody(gone ? DELETED_OVERRIDES : {})),
        [`DELETE ${DETAIL_PATH}`]: () => {
          gone = true;
          return { status: 204 };
        },
      },
    });
    await user.click(await screen.findByRole("button", { name: "Dar de baja" }));
    const dialog = screen.getByRole("dialog", { name: "¿Dar de baja a Laura Gómez?" });

    await user.click(within(dialog).getByRole("button", { name: "Dar de baja" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`DELETE ${DETAIL_PATH}`)).toHaveLength(1);
    expect(await screen.findByText("Socio dado de baja")).toBeInTheDocument();
    expect(await screen.findByText(/Dado de baja el 20 oct 2026/)).toBeInTheDocument();
    expect(actionNames()).toEqual(["Reactivar"]);
  });

  it("Reactivar confirma, hace POST reactivate y vuelve a la ficha activa", async () => {
    let back = false;
    const { mock, user } = renderMemberDetail(undefined, {
      handlers: {
        [`GET ${DETAIL_PATH}`]: () => ok(memberDetailBody(back ? {} : DELETED_OVERRIDES)),
        [`POST ${DETAIL_PATH}/reactivate`]: () => {
          back = true;
          return ok(memberDetailBody());
        },
      },
    });
    await user.click(await screen.findByRole("button", { name: "Reactivar" }));
    const dialog = screen.getByRole("dialog", { name: "¿Reactivar a Laura Gómez?" });

    await user.click(within(dialog).getByRole("button", { name: "Reactivar" }));

    expect(await screen.findByText("Socio reactivado")).toBeInTheDocument();
    expect(mock.callsTo(`POST ${DETAIL_PATH}/reactivate`)).toHaveLength(1);
    await waitFor(() => {
      expect(actionNames()).toEqual(["Dar de baja", "Editar", "Vender membresía"]);
    });
  });

  it("Reactivar con el documento tomado por otro socio vivo avisa con enlace a ese socio (409, existing_id)", async () => {
    const { user } = renderMemberDetail(undefined, {
      handlers: {
        ...deleted,
        [`POST ${DETAIL_PATH}/reactivate`]: apiError(409, "member_document_duplicated", { field: "document", existing_id: DUPLICATE_ID }),
      },
    });
    await user.click(await screen.findByRole("button", { name: "Reactivar" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reactivar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No se puede reactivar: otro socio activo ya tiene este documento.");
    const link = within(alert).getByRole("link", { name: "Ver el socio con ese documento" });
    expect(link).toHaveAttribute("href", `/socios/${DUPLICATE_ID}`);
    await user.click(link);
    expect(screen.getByTestId("location")).toHaveTextContent(`/socios/${DUPLICATE_ID}`);
  });
});

describe("MemberDetailPage · errores", () => {
  it("un 404 dice 'Socio no encontrado' con la salida a Socios", async () => {
    renderMemberDetail(undefined, { handlers: { [`GET ${DETAIL_PATH}`]: apiError(404, "member_not_found") } });

    expect(await screen.findByRole("heading", { level: 1, name: "Socio no encontrado" })).toBeInTheDocument();
    expect(screen.getByText("Puede que el enlace esté mal escrito. Búscalo en la lista de socios.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a Socios" })).toHaveAttribute("href", "/socios");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("un 500 avisa y 'Reintentar' vuelve a pedir la ficha", async () => {
    let fail = true;
    const { mock, user } = renderMemberDetail(undefined, {
      handlers: { [`GET ${DETAIL_PATH}`]: () => (fail ? apiError(500, "internal_error") : ok(memberDetailBody())) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar la ficha del socio. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("heading", { level: 1, name: /Laura Gómez/ })).toBeInTheDocument();
    expect(mock.callsTo(`GET ${DETAIL_PATH}`).length).toBeGreaterThanOrEqual(2);
  });

  it("un 429 dice cuánto esperar", async () => {
    renderMemberDetail(undefined, { handlers: { [`GET ${DETAIL_PATH}`]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Abriste muchas fichas seguidas. Espera 30 segundos e intenta de nuevo.");
  });

  it("una respuesta con otra forma no se pinta", async () => {
    renderMemberDetail(undefined, { handlers: { [`GET ${DETAIL_PATH}`]: ok({ id: MEMBER_ID }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida.");
  });
});

describe("MemberDetailPage · accesibilidad", () => {
  it("sin violaciones de axe en la ficha activa y en la de un dado de baja", async () => {
    const { container } = renderMemberDetail();
    await screen.findByRole("tabpanel");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones de axe con el aviso de autorización y dado de baja", async () => {
    const { container } = renderMemberDetail(undefined, {
      handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ ...DELETED_OVERRIDES, data_consent_at: null, data_consent_version: null })) },
    });
    await screen.findByRole("tabpanel");
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberDetailPage · revisión S3-F1", () => {
  it("TS LOW-7 y LOW-8: tras dar de baja el aviso llega con la ficha ya de solo lectura y recibe el foco", async () => {
    let gone = false;
    const { user } = renderMemberDetail(undefined, {
      handlers: {
        [`GET ${DETAIL_PATH}`]: () => ok(memberDetailBody(gone ? DELETED_OVERRIDES : {})),
        [`DELETE ${DETAIL_PATH}`]: () => {
          gone = true;
          return { status: 204 };
        },
      },
    });
    await user.click(await screen.findByRole("button", { name: "Dar de baja" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));

    const notice = await screen.findByText("Socio dado de baja");
    expect(screen.getByText(/Dado de baja el 20 oct 2026/)).toBeInTheDocument();
    expect(actionNames()).toEqual(["Reactivar"]);
    await waitFor(() => {
      expect(notice).toHaveFocus();
    });
  });

  it("TS LOW-6: el aviso de la edición se lee una vez y se borra del historial", async () => {
    const { router } = renderMemberDetail(`/socios/${MEMBER_ID}`, { state: { memberUpdated: true } });

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    await waitFor(() => {
      expect(router.state.location.state).toBeNull();
    });
    expect(screen.getByText("Cambios guardados")).toBeInTheDocument();
  });

  it("TS MEDIUM-1: una relectura fallida no quita la ficha; solo avisa", async () => {
    let fail = false;
    const queryClient = testQueryClient();
    renderMemberDetail(undefined, { queryClient, handlers: { [`GET ${DETAIL_PATH}`]: () => (fail ? apiError(500, "internal_error") : ok(memberDetailBody())) } });
    await screen.findByRole("tabpanel");

    fail = true;
    await queryClient.invalidateQueries({ queryKey: ["members"] });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos actualizar la ficha; se muestran los últimos datos cargados.");
    expect(screen.getByRole("heading", { level: 1, name: /Laura Gómez/ })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Datos de contacto");
  });

  it("LOW-3 de seguridad: un :id sin forma de UUID da 'Socio no encontrado' sin pedir nada", async () => {
    const { mock } = renderMemberDetail("/socios/..");

    expect(await screen.findByRole("heading", { level: 1, name: "Socio no encontrado" })).toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });
});
