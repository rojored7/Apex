// S9-F1 · US-184 (Atleta_Perfil.html): pestaña Atleta de la ficha (/socios/:id/atleta), admin y coach (`athletes.view`).
// - Cinco subpestañas en `?tab=` (píldoras): Resumen (por defecto), Medidas corporales, RMs por movimiento, Récords y Benchmarks.
// - «+ Registrar medidas» (athletes.write) abre el panel; con el socio dado de baja no hay acciones (la ficha es de solo lectura, N-20).
// - H-1: si la ficha trae `data_consent_at: null` el botón del panel nace deshabilitado con el enlace a la ficha.
// - Guardar una medida relee el resumen y la lista (invalidateAthleteViews). Abrir la pestaña nunca pide un reveal.
// S9-F2: RMs por movimiento y Récords con su contenido, y «+ Registrar récord» (panel RecordPanel). DESIGN-GAP: «Exportar progreso».
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, CATALOG_HANDLERS, CLEAR, derivedRm, MEMBER_ID, METRICS_PATH, metric, metricId, movementId, pageReply, record, RECORDS_PATH, revealPath, rm, RMS_PATH, SUMMARY_PATH, summary } from "../../../test/athletes";
import { DELETED_TAB_MEMBER, TAB_MEMBER, renderMemberTab } from "../../../test/memberTabs";
import { setViewportWidth, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import AthleteTab from "./AthleteTab";

const SUMMARY = `GET ${SUMMARY_PATH}`;
const LIST = `GET ${METRICS_PATH}`;
const POST = `POST ${METRICS_PATH}`;
const BASE = `/socios/${MEMBER_ID}/atleta`;
const ROWS = [metric(1), metric(2, { measured_on: "2026-09-01" })];
const WITH_CONSENT = { ...TAB_MEMBER, data_consent_at: "2026-03-12T15:00:00Z" };
const WITHOUT_CONSENT = { ...TAB_MEMBER, data_consent_at: null };

const defaults = (): Record<string, MockHandler> => ({
  [SUMMARY]: { status: 200, body: summary() },
  [LIST]: (call) => pageReply(call, ROWS),
  [POST]: { status: 201, body: metric(3) },
  [`POST ${revealPath(metricId(1))}`]: (call) => ({ status: 200, body: { field: (call.body as { field: keyof typeof CLEAR }).field, value: CLEAR[(call.body as { field: keyof typeof CLEAR }).field] } }),
});

const renderTab = (entry = BASE, handlers: Record<string, MockHandler> = {}, member: Parameters<typeof renderMemberTab>[3] = { member: WITH_CONSENT }) =>
  renderMemberTab(AthleteTab, "atleta", entry, { handlers: { ...defaults(), ...handlers }, ...member });
const subtabs = (): HTMLElement => screen.getByRole("tablist", { name: "Secciones del atleta" });
const register = () => screen.getByRole("button", { name: /Registrar medidas/ });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("AthleteTab · subpestañas en ?tab=", () => {
  it("muestra cinco píldoras con los nombres del diseño y Resumen activa por defecto", async () => {
    renderTab();

    const tabs = within(await screen.findByRole("tablist", { name: "Secciones del atleta" })).getAllByRole("tab");
    expect(tabs.map((tab) => tab.firstChild?.textContent)).toEqual(["Resumen", "Medidas corporales", "RMs por movimiento", "Récords", "Benchmarks"]);
    expect(screen.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
    expect(subtabs()).toHaveAttribute("data-variant", "pills");
  });

  it("Resumen monta las tarjetas con GET /athletes/{id}/summary y todavía no pide la lista de medidas", async () => {
    const { mock } = renderTab();

    expect(await screen.findByRole("heading", { level: 2, name: "Récords recientes" })).toBeInTheDocument();
    expect(mock.callsTo(SUMMARY)).toHaveLength(1);
    expect(mock.callsTo(LIST)).toHaveLength(0);
  });

  it("?tab=medidas abre Medidas corporales con la lista paginada y sin pedir el resumen", async () => {
    const { mock } = renderTab(`${BASE}?tab=medidas`);

    expect(await screen.findByRole("table", { name: "Medidas corporales del socio" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Medidas corporales" })).toHaveAttribute("aria-selected", "true");
    expect(new URL(mock.callsTo(LIST)[0]?.url ?? "", "http://apex.test").searchParams.get("limit")).toBe("25");
    expect(mock.callsTo(SUMMARY)).toHaveLength(0);
  });

  it("una subpestaña desconocida en la URL cae en Resumen", async () => {
    renderTab(`${BASE}?tab=cualquier-cosa`);

    expect(await screen.findByRole("heading", { level: 2, name: "Medidas corporales" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
  });

  it("elegir una subpestaña la deja en la URL (?tab=medidas) conservando la ruta, y «Ver todas (9)» del resumen hace lo mismo", async () => {
    const { user } = renderTab();
    await screen.findByRole("heading", { level: 2, name: "Medidas corporales" });

    await user.click(screen.getByRole("link", { name: "Ver todas (9)" }));

    expect(screen.getByTestId("location")).toHaveTextContent(`${BASE}?tab=medidas`);
    expect(await screen.findByRole("table", { name: "Medidas corporales del socio" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Resumen" }));
    expect(screen.getByTestId("location")).toHaveTextContent(`${BASE}?tab=resumen`);
  });

  it("la flecha derecha pasa de Resumen a Medidas corporales y cambia el panel", async () => {
    const { user } = renderTab();
    await screen.findByRole("heading", { level: 2, name: "Medidas corporales" });

    await user.click(screen.getByRole("tab", { name: "Resumen" }));
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("tab", { name: "Medidas corporales" })).toHaveFocus();
    expect(await screen.findByRole("table", { name: "Medidas corporales del socio" })).toBeInTheDocument();
  });

  it("RMs, Récords y Benchmarks existen como subpestañas del contrato (su contenido llega en F2 y F3)", async () => {
    renderTab(`${BASE}?tab=rms`);

    await screen.findByRole("tablist", { name: "Secciones del atleta" });
    expect(screen.getByRole("tab", { name: /^RMs por movimiento/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Récords/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Benchmarks/ })).toBeInTheDocument();
  });
});

describe("AthleteTab · registrar medidas", () => {
  it.each(["admin", "coach"] as const)("el %s ve «+ Registrar medidas» y abre el panel", async (role) => {
    signInAs(role);
    const { user } = renderTab();

    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));

    expect(screen.getByRole("dialog", { name: "Registrar medidas" })).toBeInTheDocument();
  });

  it("con el socio dado de baja no hay «Registrar medidas» (la ficha es de solo lectura)", async () => {
    renderTab(BASE, {}, { member: DELETED_TAB_MEMBER });

    await screen.findByRole("heading", { level: 2, name: "Medidas corporales" });
    expect(screen.queryByRole("button", { name: /Registrar medidas/ })).not.toBeInTheDocument();
  });

  it("con el socio dado de baja la lista de medidas se ve, sin «Anular»", async () => {
    renderTab(`${BASE}?tab=medidas`, {}, { member: DELETED_TAB_MEMBER });

    expect(await screen.findByText("1 oct 2026")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it("H-1: si la ficha dice que falta la autorización de datos, el botón del panel nace deshabilitado con el enlace a la ficha", async () => {
    const { user } = renderTab(BASE, {}, { member: WITHOUT_CONSENT });

    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));

    expect(screen.getByRole("button", { name: "Guardar medidas" })).toBeDisabled();
    expect(screen.getByText("Falta la autorización de datos del socio. Regístrala en su ficha para guardar medidas.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a la ficha del socio" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
  });

  it("con la autorización registrada el botón del panel está habilitado", async () => {
    const { user } = renderTab();

    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));

    expect(screen.getByRole("button", { name: "Guardar medidas" })).toBeEnabled();
  });

  it("guardar cierra el panel y relee el resumen (invalidateAthleteViews)", async () => {
    const { user, mock } = renderTab();
    await screen.findByRole("heading", { level: 2, name: "Medidas corporales" });
    await user.click(register());
    await user.type(screen.getByLabelText(/^Peso/), "61,2");

    await user.click(screen.getByRole("button", { name: "Guardar medidas" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Registrar medidas" })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(mock.callsTo(SUMMARY).length).toBeGreaterThanOrEqual(2);
    });
    expect(mock.callsTo(POST)).toHaveLength(1);
  });

  it("guardar desde Medidas corporales relee la lista", async () => {
    const { user, mock } = renderTab(`${BASE}?tab=medidas`);
    await screen.findByText("1 oct 2026");
    await user.click(register());
    await user.type(screen.getByLabelText(/^Peso/), "61,2");

    await user.click(screen.getByRole("button", { name: "Guardar medidas" }));

    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
    expect(screen.queryByRole("dialog", { name: "Registrar medidas" })).not.toBeInTheDocument();
  });

  it("si el api responde 409 consent_required, el panel sigue abierto con el mensaje y el enlace a la ficha", async () => {
    const { user } = renderTab(BASE, { [POST]: apiError(409, "consent_required") });
    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));
    await user.type(screen.getByLabelText(/^Peso/), "61,2");

    await user.click(screen.getByRole("button", { name: "Guardar medidas" }));

    expect(await screen.findByRole("link", { name: "Ir a la ficha del socio" })).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Registrar medidas" })).toBeInTheDocument();
  });
});

describe("AthleteTab · datos sensibles", () => {
  it("abrir la pestaña (resumen o medidas) nunca pide un reveal ni deja un valor en pantalla", async () => {
    const { mock, unmount } = renderTab(`${BASE}?tab=medidas`);
    await screen.findByText("1 oct 2026");

    expect(mock.calls.filter((c) => c.path.includes("/reveal"))).toHaveLength(0);
    expect(document.body).not.toHaveTextContent(/61,2 kg|165 cm|22 %/);
    unmount();
  });

  it("mostrar un valor no cambia la URL: el valor nunca va en la dirección", async () => {
    const { user } = renderTab(`${BASE}?tab=medidas`);
    const first = (await screen.findByText("1 oct 2026")).closest("tr") as HTMLElement;

    await user.click(within(first).getByRole("button", { name: "Mostrar peso" }));
    await within(first).findByText("61,2 kg");

    expect(screen.getByTestId("location").textContent).toBe(`${BASE}?tab=medidas`);
  });
});

describe("AthleteTab · accesibilidad", () => {
  it("no tiene violaciones de axe en Resumen ni en Medidas", async () => {
    const first = renderTab();
    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    expect(await axe(first.container)).toHaveNoViolations();
    cleanup();

    const second = renderTab(`${BASE}?tab=medidas`);
    await screen.findByText("1 oct 2026");
    expect(await axe(second.container)).toHaveNoViolations();
  });
});

// S9-F1 (revisión M3 y hueco de prueba): aviso al guardar y cambio de socio con la pestaña abierta.
describe("AthleteTab · revisión", () => {
  it("guardar avisa «Medidas guardadas.» en un role=status, sin ningún valor", async () => {
    const { user } = renderTab();
    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));
    await user.type(screen.getByLabelText(/^Peso/), "61,2");

    await user.click(screen.getByRole("button", { name: "Guardar medidas" }));

    const notice = await screen.findByText("Medidas guardadas.");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice.textContent).not.toMatch(/61/);
  });

  it("al cambiar de socio con la pestaña abierta pide los datos del nuevo y suelta lo revelado del anterior", async () => {
    const OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const { user, mock, router } = renderTab(`${BASE}?tab=medidas`, { [`GET /athletes/${OTHER}/metrics`]: (call) => pageReply(call, [metric(9, { measured_on: "2026-05-05" })]) }, { member: null });
    const first = (await screen.findByText("1 oct 2026")).closest("tr") as HTMLElement;
    await user.click(within(first).getByRole("button", { name: "Mostrar peso" }));
    await within(first).findByText("61,2 kg");

    await act(async () => {
      await router.navigate(`/socios/${OTHER}/atleta?tab=medidas`);
    });

    expect(await screen.findByText("5 may 2026")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("61,2 kg");
    expect(mock.callsTo(`GET /athletes/${OTHER}/metrics`)).toHaveLength(1);
  });
});

// S9-F2 · US-180 a US-182: las subpestañas RMs y Récords ya no son «llega en la siguiente entrega» y «+ Registrar récord» abre el panel.
describe("AthleteTab · RMs y Récords (S9-F2)", () => {
  const RMS_LIST = `GET ${RMS_PATH}`;
  const RECORDS_LIST = `GET ${RECORDS_PATH}`;
  const RECORD_POST = `POST ${RECORDS_PATH}`;
  const COMING_SOON = "Esta sección llega en la siguiente entrega del perfil del atleta.";
  const extra = (): Record<string, MockHandler> => ({
    ...CATALOG_HANDLERS,
    [RMS_LIST]: (call) => pageReply(call, [rm(1)]),
    [RECORDS_LIST]: (call) => pageReply(call, [record(1), derivedRm(2)]),
    [RECORD_POST]: { status: 201, body: record(9) },
  });
  const registerRecord = () => screen.getByRole("button", { name: /Registrar récord/ });

  it("?tab=rms monta la lista de RMs con su petición y ya no dice «llega en la siguiente entrega»", async () => {
    const { mock } = renderTab(`${BASE}?tab=rms`, extra());

    expect(await screen.findByRole("table", { name: "RMs por movimiento del socio" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "RMs por movimiento" })).toHaveAttribute("aria-selected", "true");
    expect(mock.callsTo(RMS_LIST)).toHaveLength(1);
    expect(mock.callsTo(SUMMARY)).toHaveLength(0);
    expect(screen.queryByText(COMING_SOON)).not.toBeInTheDocument();
  });

  it("?tab=records monta la lista de récords con sus chips y ya no dice «llega en la siguiente entrega»", async () => {
    const { mock } = renderTab(`${BASE}?tab=records`, extra());

    expect(await screen.findByRole("table", { name: "Récords del socio" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tipo de récord" })).toBeInTheDocument();
    expect(mock.callsTo(RECORDS_LIST)).toHaveLength(1);
    expect(screen.queryByText(COMING_SOON)).not.toBeInTheDocument();
  });

  it("Benchmarks sigue pendiente de F3: conserva el aviso de que llega en la siguiente entrega", async () => {
    renderTab(`${BASE}?tab=benchmarks`, extra());

    expect(await screen.findByText(COMING_SOON)).toBeInTheDocument();
  });

  it.each(["admin", "coach"] as const)("el %s ve «+ Registrar récord» y abre el panel «Registrar récord»", async (role) => {
    signInAs(role);
    const { user } = renderTab(BASE, extra());

    await user.click(await screen.findByRole("button", { name: /Registrar récord/ }));

    expect(screen.getByRole("dialog", { name: "Registrar récord" })).toBeInTheDocument();
  });

  it("con el socio dado de baja no hay «+ Registrar récord» ni «Invalidar» (la ficha es de solo lectura)", async () => {
    renderTab(`${BASE}?tab=records`, extra(), { member: DELETED_TAB_MEMBER });

    await screen.findByRole("table", { name: "Récords del socio" });
    expect(screen.queryByRole("button", { name: /Registrar récord/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Invalidar / })).not.toBeInTheDocument();
  });

  it("un récord no es dato de salud: sin autorización de datos el botón y el panel siguen disponibles", async () => {
    const { user } = renderTab(BASE, extra(), { member: WITHOUT_CONSENT });

    await user.click(await screen.findByRole("button", { name: /Registrar récord/ }));

    expect(screen.getByRole("button", { name: "Guardar récord" })).toBeEnabled();
    expect(screen.queryByText(/autorización de datos/)).not.toBeInTheDocument();
  });

  it("guardar un RM cierra el panel, avisa «Récord guardado.» en un role=status y relee los RMs", async () => {
    const { user, mock } = renderTab(`${BASE}?tab=rms`, extra());
    await screen.findByRole("table", { name: "RMs por movimiento del socio" });
    await user.click(registerRecord());
    await screen.findByRole("option", { name: "Back Squat" });
    await user.selectOptions(screen.getByLabelText(/^Movimiento/), "Back Squat");
    await user.type(screen.getByLabelText(/^Carga \(kg\)/), "100");

    await user.click(screen.getByRole("button", { name: "Guardar récord" }));

    const notice = await screen.findByText("Récord guardado.");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice.textContent).not.toMatch(/100/);
    expect(screen.queryByRole("dialog", { name: "Registrar récord" })).not.toBeInTheDocument();
    expect(mock.callsTo(RECORD_POST)).toHaveLength(1);
    expect(mock.callsTo(RECORD_POST)[0]?.body).toMatchObject({ kind: "rm", movement_id: movementId(1), value_g: 100_000 });
    await waitFor(() => {
      expect(mock.callsTo(RMS_LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("guardar un récord desde Récords relee la lista de récords", async () => {
    const { user, mock } = renderTab(`${BASE}?tab=records`, extra());
    await screen.findByRole("table", { name: "Récords del socio" });
    await user.click(registerRecord());
    await screen.findByRole("option", { name: "Deadlift" });
    await user.selectOptions(screen.getByLabelText(/^Movimiento/), "Deadlift");
    await user.type(screen.getByLabelText(/^Carga \(kg\)/), "120");

    await user.click(screen.getByRole("button", { name: "Guardar récord" }));

    await waitFor(() => {
      expect(mock.callsTo(RECORDS_LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("el aviso de medidas y el de récord no se mezclan: abrir el panel de récord borra «Medidas guardadas.»", async () => {
    const { user } = renderTab(BASE, extra());
    await user.click(await screen.findByRole("button", { name: /Registrar medidas/ }));
    await user.type(screen.getByLabelText(/^Peso/), "61,2");
    await user.click(screen.getByRole("button", { name: "Guardar medidas" }));
    await screen.findByText("Medidas guardadas.");

    await user.click(registerRecord());

    expect(screen.queryByText("Medidas guardadas.")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de axe en RMs ni en Récords", async () => {
    const first = renderTab(`${BASE}?tab=rms`, extra());
    await screen.findByRole("table", { name: "RMs por movimiento del socio" });
    expect(await axe(first.container)).toHaveNoViolations();
    cleanup();

    const second = renderTab(`${BASE}?tab=records`, extra());
    await screen.findByRole("table", { name: "Récords del socio" });
    expect(await axe(second.container)).toHaveNoViolations();
  });
});

// Revisión S9-F2 (seguridad L3): sin la ficha cargada (member null) la pestaña no ofrece acciones de escritura.
describe("AthleteTab · ficha sin cargar (revisión)", () => {
  it("con member null no hay «+ Registrar récord» ni «+ Registrar medidas»", async () => {
    renderTab(`${BASE}?tab=records`, {}, { member: null });

    await screen.findByRole("tablist", { name: "Secciones del atleta" });
    expect(screen.queryByRole("button", { name: /Registrar/ })).not.toBeInTheDocument();
  });
});
