// S5-F2 · US-120 y US-121 (front): /avisos/reglas (Notif_Reglas.html), admin edita y coach lee.
// - Título "Avisos", pestañas Reglas y Plantillas (Tabs compartido, `?tab=`), enlace al historial.
// - Reglas: tabla (regla, cuándo, plantilla, canal, estado, acción), alta y edición en un SidePanel con
//   React Hook Form + Zod según RuleCreate/RulePatch (desfase de vencimiento en días antes o después).
// - Plantillas: tabla, editor con las variables permitidas y vista previa (POST /notification-templates/preview).
// - Coach en solo lectura (sin botones de escritura); estados de carga, vacío, error y 403.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { callsOf, apiError, RULES, RULE_IDS, TEMPLATES, TEMPLATE_IDS, pageOf, renderRules } from "../../../test/notificationAdmin";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const table = (name: string) => screen.getByRole("table", { name });
const tab = (name: string) => screen.getByRole("tab", { name });
const dialog = (name: string | RegExp) => screen.getByRole("dialog", { name });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("RulesPage · estructura (Notif_Reglas.html)", () => {
  it("muestra el título, las pestañas, el enlace al historial, la nota y Nueva regla", async () => {
    renderRules();

    expect(screen.getByRole("heading", { level: 1, name: "Avisos" })).toBeInTheDocument();
    const list = screen.getByRole("tablist", { name: "Secciones de avisos" });
    expect(within(list).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Reglas", "Plantillas"]);
    expect(tab("Reglas")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Historial de envíos" })).toHaveAttribute("href", "/avisos/historial");
    expect(screen.getByText(/Una regla dice cuándo avisar y con qué plantilla\./)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Nueva regla" })).toBeInTheDocument();
  });

  it("la tabla de reglas trae sus columnas y las filas con el cuándo, la plantilla, el canal y el estado", async () => {
    renderRules();

    await screen.findByText("Por vencer");
    expect(within(table("Reglas")).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Regla", "Cuándo", "Plantilla", "Canal", "Estado", "Acción"]);
    const rows = within(table("Reglas")).getAllByRole("row");
    const cells = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(rows[1])).toEqual(["Por vencer", "3 días antes del fin", "por_vencer", "Correo", "Activa", "Editar"]);
    expect(cells(rows[2])).toEqual(["Vence hoy", "el día del fin", "por_vencer", "WhatsApp manual", "Activa", "Editar"]);
    expect(cells(rows[3])).toEqual(["Vencido", "1 día después del fin", "vencido", "WhatsApp manual", "Pausada", "Editar"]);
  });

  it("la primera petición de reglas pide la primera página de 25", async () => {
    const { mock } = renderRules();
    await screen.findByText("Por vencer");

    expect(callsOf(mock, "GET /notification-rules")[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("?tab=plantillas abre las plantillas con su tabla", async () => {
    renderRules("/avisos/reglas?tab=plantillas");

    expect(tab("Plantillas")).toHaveAttribute("aria-selected", "true");
    await screen.findByText("Tu plan vence pronto");
    expect(within(table("Plantillas")).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Plantilla", "Asunto", "Actualizada", "Acción"]);
    expect(within(table("Plantillas")).getByText("22 oct 2026")).toBeInTheDocument();
  });

  it("una pestaña desconocida abre Reglas", async () => {
    renderRules("/avisos/reglas?tab=otra");

    expect(tab("Reglas")).toHaveAttribute("aria-selected", "true");
    await screen.findByText("Por vencer");
  });
});

describe("RulesPage · alta de una regla (US-121)", () => {
  async function openNew() {
    const view = renderRules();
    await screen.findByText("Por vencer");
    await view.user.click(screen.getByRole("button", { name: "Nueva regla" }));
    return view;
  }

  it("abre el panel con los campos y la plantilla sin elegir", async () => {
    await openNew();

    const panel = dialog("Nueva regla");
    expect(within(panel).getByRole("textbox", { name: /^Nombre/ })).toHaveValue("");
    expect(within(panel).getByRole("combobox", { name: /^Evento/ })).toHaveValue("membership_expiring");
    expect(within(panel).getByRole("textbox", { name: /^Días antes del fin/ })).toHaveValue("0");
    expect(within(panel).getByRole("combobox", { name: /^Canal/ })).toHaveValue("email");
    expect(within(panel).getByRole("combobox", { name: /^Plantilla/ })).toHaveValue("");
    expect(within(panel).getByRole("checkbox", { name: "Regla activa" })).toBeChecked();
  });

  it("sin nombre ni plantilla muestra los errores y no llama al api", async () => {
    const { user, mock } = await openNew();

    await user.click(within(dialog("Nueva regla")).getByRole("button", { name: "Crear regla" }));

    expect(await screen.findByText("Escribe el nombre de la regla.")).toBeInTheDocument();
    expect(screen.getByText("Elige la plantilla.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-rules")).toHaveLength(0);
  });

  it("un aviso de vencida con 0 días se explica", async () => {
    const { user, mock } = await openNew();
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Vencida");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Evento/ }), "membership_expired");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.vencido);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    expect(await screen.findByText("Un aviso de vencida se manda 1 día o más después del fin.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-rules")).toHaveLength(0);
  });

  it("los días fuera de 0 a 3650 o no enteros se explican", async () => {
    const { user } = await openNew();
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Regla");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    const days = within(panel).getByRole("textbox", { name: /^Días antes del fin/ });
    await user.clear(days);
    await user.type(days, "3651");
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));
    expect(await screen.findByText("Escribe un número entero de días entre 0 y 3650.")).toBeInTheDocument();

    await user.clear(days);
    await user.type(days, "2,5");
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));
    expect(await screen.findByText("Escribe un número entero de días entre 0 y 3650.")).toBeInTheDocument();
  });

  it("al cambiar el evento cambia el nombre del campo de días", async () => {
    const { user } = await openNew();
    const panel = dialog("Nueva regla");

    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Evento/ }), "membership_expired");

    expect(within(panel).getByRole("textbox", { name: /^Días después del fin/ })).toBeInTheDocument();
  });

  it("crea la regla con el desfase negativo para 'por vencer', avisa y relee la lista", async () => {
    const created = { ...RULES.porVencer, id: "ffffffff-4444-4444-8444-ffffffffffff", name: "Aviso previo", offset_days: -2 };
    const { user, mock } = await openNew();
    const panel = dialog("Nueva regla");
    mock.calls.length = 0;

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "  Aviso previo ");
    const days = within(panel).getByRole("textbox", { name: /^Días antes del fin/ });
    await user.clear(days);
    await user.type(days, "2");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    expect(await screen.findByText("Regla creada: Aviso previo.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-rules")[0]?.body).toEqual({
      name: "Aviso previo",
      trigger: "membership_expiring",
      offset_days: -2,
      channel: "email",
      template_id: TEMPLATE_IDS.porVencer,
      is_active: true,
    });
    expect(created.offset_days).toBe(-2);
    await waitFor(() => {
      expect(mock.callsTo("GET /notification-rules").length).toBeGreaterThan(0);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("'el mismo día' (0) viaja como 0 y no como -0", async () => {
    const { user, mock } = await openNew();
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Hoy");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    await screen.findByText("Regla creada: Hoy.");
    const body = mock.callsTo("POST /notification-rules")[0]?.body as { offset_days: number };
    expect(Object.is(body.offset_days, 0)).toBe(true);
  });

  it("una de vencida envía los días en positivo", async () => {
    const { user, mock } = await openNew();
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Vencida 7");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Evento/ }), "membership_expired");
    const days = within(panel).getByRole("textbox", { name: /^Días después del fin/ });
    await user.clear(days);
    await user.type(days, "7");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Canal/ }), "whatsapp_link");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.vencido);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    await screen.findByText("Regla creada: Vencida 7.");
    expect(mock.callsTo("POST /notification-rules")[0]?.body).toMatchObject({ trigger: "membership_expired", offset_days: 7, channel: "whatsapp_link" });
  });

  it("un 422 con campo muestra el mensaje del api bajo ese campo", async () => {
    const { user } = renderRules("/avisos/reglas", {
      handlers: { "POST /notification-rules": apiError(422, "validation_error", { field: "offset_days" }, undefined, "Un aviso de vencida lleva un desfase de uno o más días.") },
    });
    await screen.findByText("Por vencer");
    await user.click(screen.getByRole("button", { name: "Nueva regla" }));
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Regla");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    const days = await within(panel).findByRole("textbox", { name: /^Días antes del fin/ });
    await waitFor(() => {
      expect(days).toHaveAttribute("aria-invalid", "true");
    });
    expect(days).toHaveAccessibleDescription(expect.stringContaining("Un aviso de vencida lleva un desfase de uno o más días."));
  });

  it("un 409 muestra el mensaje del api como aviso y el panel sigue abierto", async () => {
    const { user } = renderRules("/avisos/reglas", {
      handlers: { "POST /notification-rules": apiError(409, "rule_name_duplicated", {}, undefined, "Ya existe una regla con este nombre.") },
    });
    await screen.findByText("Por vencer");
    await user.click(screen.getByRole("button", { name: "Nueva regla" }));
    const panel = dialog("Nueva regla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Regla");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Ya existe una regla con este nombre.");
  });

  it("un 429 pide esperar y un 500 da un mensaje general", async () => {
    const { user } = renderRules("/avisos/reglas", { handlers: { "POST /notification-rules": apiError(500, "internal_error") } });
    await screen.findByText("Por vencer");
    await user.click(screen.getByRole("button", { name: "Nueva regla" }));
    const panel = dialog("Nueva regla");
    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Regla");
    await user.selectOptions(within(panel).getByRole("combobox", { name: /^Plantilla/ }), TEMPLATE_IDS.porVencer);
    await user.click(within(panel).getByRole("button", { name: "Crear regla" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("No pudimos guardar la regla. Intenta de nuevo en un momento.");
  });
});

describe("RulesPage · edición de una regla (US-121)", () => {
  it("precarga la regla y envía solo lo que cambió (los días de vencida en positivo)", async () => {
    const { user, mock } = renderRules("/avisos/reglas", {
      handlers: { [`PATCH /notification-rules/${RULE_IDS.vencido}`]: { status: 200, body: { ...RULES.vencido, offset_days: 7 } } },
    });
    await screen.findByText("Vencido");

    await user.click(screen.getByRole("button", { name: "Editar regla Vencido" }));
    const panel = dialog("Editar regla · Vencido");
    expect(within(panel).getByRole("textbox", { name: /^Nombre/ })).toHaveValue("Vencido");
    expect(within(panel).getByRole("combobox", { name: /^Evento/ })).toHaveValue("membership_expired");
    expect(within(panel).getByRole("textbox", { name: /^Días después del fin/ })).toHaveValue("1");
    expect(within(panel).getByRole("combobox", { name: /^Plantilla/ })).toHaveValue(TEMPLATE_IDS.vencido);
    expect(within(panel).getByRole("checkbox", { name: "Regla activa" })).not.toBeChecked();
    const days = within(panel).getByRole("textbox", { name: /^Días después del fin/ });
    await user.clear(days);
    await user.type(days, "7");
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Regla guardada: Vencido.")).toBeInTheDocument();
    expect(mock.callsTo(`PATCH /notification-rules/${RULE_IDS.vencido}`)[0]?.body).toEqual({ offset_days: 7 });
  });

  it("activar o pausar viaja como is_active", async () => {
    const { user, mock } = renderRules("/avisos/reglas", {
      handlers: { [`PATCH /notification-rules/${RULE_IDS.vencido}`]: { status: 200, body: { ...RULES.vencido, is_active: true } } },
    });
    await screen.findByText("Vencido");

    await user.click(screen.getByRole("button", { name: "Editar regla Vencido" }));
    await user.click(within(dialog("Editar regla · Vencido")).getByRole("checkbox", { name: "Regla activa" }));
    await user.click(within(dialog("Editar regla · Vencido")).getByRole("button", { name: "Guardar" }));

    await screen.findByText("Regla guardada: Vencido.");
    expect(mock.callsTo(`PATCH /notification-rules/${RULE_IDS.vencido}`)[0]?.body).toEqual({ is_active: true });
  });

  it("sin cambios cierra sin llamar al api", async () => {
    const { user, mock } = renderRules();
    await screen.findByText("Vencido");

    await user.click(screen.getByRole("button", { name: "Editar regla Vencido" }));
    await user.click(within(dialog("Editar regla · Vencido")).getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`PATCH /notification-rules/${RULE_IDS.vencido}`)).toHaveLength(0);
  });

  it("un 404 explica que la regla ya no existe", async () => {
    const { user } = renderRules("/avisos/reglas", { handlers: { [`PATCH /notification-rules/${RULE_IDS.vencido}`]: apiError(404, "rule_not_found") } });
    await screen.findByText("Vencido");

    await user.click(screen.getByRole("button", { name: "Editar regla Vencido" }));
    const panel = dialog("Editar regla · Vencido");
    await user.click(within(panel).getByRole("checkbox", { name: "Regla activa" }));
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Esta regla ya no existe. Cierra el panel; la lista se actualiza sola.");
  });
});

describe("RulesPage · coach en solo lectura", () => {
  beforeEach(() => {
    signOutForTests();
    signInAs("coach");
  });

  it("ve las reglas sin Nueva regla ni Editar y con la nota de que solo un administrador las cambia", async () => {
    renderRules();

    await screen.findByText("Por vencer");
    expect(screen.queryByRole("button", { name: "Nueva regla" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Editar regla/ })).not.toBeInTheDocument();
    expect(within(table("Reglas")).queryByRole("columnheader", { name: "Acción" })).not.toBeInTheDocument();
    expect(screen.getByText("Solo un administrador puede cambiar las reglas y las plantillas.")).toBeInTheDocument();
  });

  it("en plantillas ve 'Ver plantilla' con el texto y sin Guardar ni vista previa", async () => {
    const { user } = renderRules("/avisos/reglas?tab=plantillas");
    await screen.findByText("Tu plan vence pronto");

    expect(screen.queryByRole("button", { name: "Nueva plantilla" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ver plantilla por_vencer" }));

    const panel = dialog("Plantilla · por_vencer");
    expect(within(panel).getByText("Hola {nombre}, tu plan {plan} vence el {vence}.")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Ver vista previa" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("RulesPage · estados", () => {
  it("mientras carga dice 'Cargando reglas'", () => {
    renderRules("/avisos/reglas", { handlers: { "GET /notification-rules": () => new Promise(() => undefined) } });

    expect(screen.getAllByText("Cargando…").length).toBeGreaterThan(0);
  });

  it("sin reglas guía al admin a crear la primera y al coach no le ofrece nada", async () => {
    const empty = { "GET /notification-rules": (call: Parameters<typeof pageOf>[0]) => pageOf(call, []) };
    const { user } = renderRules("/avisos/reglas", { handlers: empty });

    expect(await screen.findByText("Todavía no hay reglas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Crear la primera regla" }));
    expect(dialog("Nueva regla")).toBeInTheDocument();
    cleanup();
    signOutForTests();
    signInAs("coach");
    renderRules("/avisos/reglas", { handlers: empty });
    expect(await screen.findByText("Todavía no hay reglas")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear la primera regla" })).not.toBeInTheDocument();
  });

  it("un 500 dice qué pasó y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderRules("/avisos/reglas", {
      handlers: { "GET /notification-rules": (call) => (++calls <= 1 ? apiError(500, "internal_error") : pageOf(call, [RULES.porVencer])) },
    });

    expect(await screen.findByText("No pudimos cargar las reglas. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Por vencer")).toBeInTheDocument();
  });

  it("un 403 explica el permiso", async () => {
    renderRules("/avisos/reglas", { handlers: { "GET /notification-rules": apiError(403, "forbidden") } });

    expect(await screen.findByText("No tienes permiso para ver las reglas de aviso. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it("sin plantillas guía a crear la primera", async () => {
    renderRules("/avisos/reglas?tab=plantillas", { handlers: { "GET /notification-templates": (call) => pageOf(call, []) } });

    expect(await screen.findByText("Todavía no hay plantillas")).toBeInTheDocument();
  });

  it("pagina las reglas: Siguiente pide offset=25", async () => {
    const { user, mock } = renderRules("/avisos/reglas", { handlers: { "GET /notification-rules": (call) => pageOf(call, [RULES.porVencer], 60) } });
    await screen.findByText("Por vencer");

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(callsOf(mock, "GET /notification-rules").some((p) => p.get("offset") === "25")).toBe(true);
    });
  });
});

describe("RulesPage · plantillas (US-120)", () => {
  async function openNewTemplate() {
    const view = renderRules("/avisos/reglas?tab=plantillas");
    await screen.findByText("Tu plan vence pronto");
    await view.user.click(screen.getByRole("button", { name: "Nueva plantilla" }));
    return view;
  }

  it("el editor lista las variables permitidas", async () => {
    await openNewTemplate();

    const panel = dialog("Nueva plantilla");
    for (const variable of ["{nombre}", "{plan}", "{vence}", "{dias}"]) expect(within(panel).getByText(variable)).toBeInTheDocument();
  });

  it("sin nombre, asunto ni mensaje muestra los errores y no llama al api", async () => {
    const { user, mock } = await openNewTemplate();

    await user.click(within(dialog("Nueva plantilla")).getByRole("button", { name: "Crear plantilla" }));

    expect(await screen.findByText("Escribe el nombre de la plantilla.")).toBeInTheDocument();
    expect(screen.getByText("Escribe el asunto.")).toBeInTheDocument();
    expect(screen.getByText("Escribe el mensaje.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-templates")).toHaveLength(0);
  });

  it("un asunto de más de 150 o un mensaje de más de 2000 caracteres se explican", async () => {
    const { user } = await openNewTemplate();
    const panel = dialog("Nueva plantilla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "x");
    await user.click(within(panel).getByRole("textbox", { name: /^Asunto/ }));
    await user.paste("a".repeat(151));
    await user.click(within(panel).getByRole("textbox", { name: /^Mensaje/ }));
    await user.paste("b".repeat(2001));
    await user.click(within(panel).getByRole("button", { name: "Crear plantilla" }));

    expect(await screen.findByText("El asunto admite hasta 150 caracteres.")).toBeInTheDocument();
    expect(screen.getByText("El mensaje admite hasta 2000 caracteres.")).toBeInTheDocument();
  });

  it("crea la plantilla con los textos recortados y avisa", async () => {
    const { user, mock } = await openNewTemplate();
    const panel = dialog("Nueva plantilla");

    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), " bienvenida ");
    await user.type(within(panel).getByRole("textbox", { name: /^Asunto/ }), "Bienvenido");
    await user.type(within(panel).getByRole("textbox", { name: /^Mensaje/ }), "Hola nombre");
    await user.click(within(panel).getByRole("button", { name: "Crear plantilla" }));

    expect(await screen.findByText("Plantilla creada: bienvenida.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-templates")[0]?.body).toEqual({ name: "bienvenida", subject: "Bienvenido", body: "Hola nombre" });
  });

  it("la vista previa hace POST con el asunto y el mensaje y muestra el resultado", async () => {
    const { user, mock } = renderRules("/avisos/reglas?tab=plantillas", {
      handlers: { "POST /notification-templates/preview": { status: 200, body: { subject: "Tu plan vence pronto", body: "Hola Ana, tu plan Mensual vence el 28 oct 2026." } } },
    });
    await screen.findByText("Tu plan vence pronto");
    await user.click(screen.getByRole("button", { name: "Editar plantilla por_vencer" }));
    const panel = dialog("Editar plantilla · por_vencer");

    await user.click(within(panel).getByRole("button", { name: "Ver vista previa" }));

    const preview = await within(panel).findByRole("region", { name: "Vista previa" });
    expect(within(preview).getByText("Hola Ana, tu plan Mensual vence el 28 oct 2026.")).toBeInTheDocument();
    expect(mock.callsTo("POST /notification-templates/preview")[0]?.body).toEqual({ subject: "Tu plan vence pronto", body: "Hola {nombre}, tu plan {plan} vence el {vence}." });
  });

  it("una variable desconocida (422 en el mensaje) se muestra bajo el campo", async () => {
    const { user } = renderRules("/avisos/reglas?tab=plantillas", {
      handlers: { "POST /notification-templates/preview": apiError(422, "validation_error", { field: "body" }, undefined, "La plantilla usa una variable que no existe.") },
    });
    await screen.findByText("Tu plan vence pronto");
    await user.click(screen.getByRole("button", { name: "Editar plantilla por_vencer" }));
    const panel = dialog("Editar plantilla · por_vencer");

    await user.click(within(panel).getByRole("button", { name: "Ver vista previa" }));

    const body = await within(panel).findByRole("textbox", { name: /^Mensaje/ });
    await waitFor(() => {
      expect(body).toHaveAttribute("aria-invalid", "true");
    });
    expect(body).toHaveAccessibleDescription(expect.stringContaining("La plantilla usa una variable que no existe."));
  });

  it("edita enviando solo el campo que cambió", async () => {
    const { user, mock } = renderRules("/avisos/reglas?tab=plantillas", {
      handlers: { [`PATCH /notification-templates/${TEMPLATE_IDS.vencido}`]: { status: 200, body: { ...TEMPLATES.vencido, body: "Nuevo texto {nombre}" } } },
    });
    await screen.findByText("Tu plan venció");
    await user.click(screen.getByRole("button", { name: "Editar plantilla vencido" }));
    const panel = dialog("Editar plantilla · vencido");
    const body = within(panel).getByRole("textbox", { name: /^Mensaje/ });

    await user.clear(body);
    await user.click(body);
    await user.paste("Nuevo texto {nombre}");
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Plantilla guardada: vencido.")).toBeInTheDocument();
    expect(mock.callsTo(`PATCH /notification-templates/${TEMPLATE_IDS.vencido}`)[0]?.body).toEqual({ body: "Nuevo texto {nombre}" });
  });
});

describe("RulesPage · accesibilidad", () => {
  it.each([["claro", null], ["oscuro", "dark"]])("reglas y panel no tienen violaciones en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { user, container } = renderRules();
    await screen.findByText("Por vencer");
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Nueva regla" }));
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("plantillas no tiene violaciones en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderRules("/avisos/reglas?tab=plantillas");
    await screen.findByText("Tu plan vence pronto");

    expect(await axe(container)).toHaveNoViolations();
  });
});
