// S9-F2 · US-180, US-181, US-182 (Atleta_Perfil.html, subpestaña «Récords»): la lista completa de récords, paginada en el servidor.
// - GET /athletes/{id}/records?limit&offset[&kind][&include_invalidated] (`kind` e `invalidated=1` en la URL).
// - Chips «RMs» y «Benchmarks» (grupo «Tipo de récord», uno u ninguno) y «Ver invalidados» (grupo «Estado del récord»).
// - «Vigente» con texto; origen con palabras: «Manual · quien lo registró», «Automático del WOD» o «Automático (tablet)» (L-4).
// - Un derivado enlaza a su WOD y explica que se corrige desde el resultado; no tiene «Invalidar». «Invalidar» solo en un manual vivo,
//   con ConfirmModal sin motivo (S9-D13) y POST .../invalidate sin cuerpo; con el socio dado de baja no hay «Invalidar» (S9-D14).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import {
  apiError,
  derivedBenchmark,
  derivedRm,
  invalidatePath,
  MEMBER_ID,
  OTHER_WOD_ID,
  pageReply,
  record,
  RECORDS_PATH,
  recordId,
  renderAthlete,
  WOD_ID,
} from "../../../test/athletes";
import { setViewportWidth, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { RecordsTab } from "./RecordsTab";

const LIST = `GET ${RECORDS_PATH}`;
const BASE = `/socios/${MEMBER_ID}/atleta?tab=records`;

const MANUAL_CURRENT = record(1);
const DERIVED_RM = derivedRm(2);
const DERIVED_HELEN = derivedBenchmark(3, { result_source: "kiosk" });
const MANUAL_OLD = record(4, { value_g: 100_000, achieved_on: "2026-08-01", is_current: false });
const INVALIDATED = record(5, { movement_name: "Thruster", value_g: 40_000, achieved_on: "2026-07-23", is_current: false, invalidated_at: "2026-07-24T15:00:00Z", invalidated_reason: "manual_error" });
const ALIVE = [MANUAL_CURRENT, DERIVED_RM, DERIVED_HELEN, MANUAL_OLD];

/** Como el api: sin `include_invalidated=true` no salen los invalidados; `kind` filtra. */
const listOf =
  (all: readonly (typeof MANUAL_CURRENT)[] = [...ALIVE, INVALIDATED]) =>
  (call: RecordedCall): MockReply => {
    const params = new URL(call.url, "http://apex.test").searchParams;
    const kind = params.get("kind");
    const withInvalidated = params.get("include_invalidated") === "true";
    return pageReply(
      call,
      all.filter((r) => (kind === null || r.kind === kind) && (withInvalidated || r.invalidated_at === null)),
    );
  };

const renderTab = (handlers: Record<string, MockHandler> = {}, deleted = false, route = BASE) =>
  renderAthlete(<RecordsTab memberId={MEMBER_ID} memberDeleted={deleted} />, { handlers: { [LIST]: listOf(), ...handlers }, route });
const table = () => screen.getByRole("table", { name: "Récords del socio" });
const rowOf = (title: string, date?: string): HTMLElement => {
  const rows = within(table()).getAllByRole("row").slice(1);
  const found = rows.find((row) => row.textContent.includes(title) && (date === undefined || row.textContent.includes(date)));
  if (!found) throw new Error(`Sin fila ${title} ${date ?? ""}`);
  return found;
};
const paramsOf = (call: { url: string } | undefined): URLSearchParams => new URL(call?.url ?? "", "http://apex.test").searchParams;
const invalidateButton = (title: string, date: string) => screen.getByRole("button", { name: `Invalidar ${title} del ${date}` });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("RecordsTab · contenido", () => {
  it("pide la lista con limit 25 y offset 0, sin filtro de tipo ni invalidados, y muestra sus columnas", async () => {
    const { mock } = renderTab();

    await screen.findByText("Helen (benchmark)");
    const params = paramsOf(mock.callsTo(LIST)[0]);
    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("0");
    expect(params.get("kind")).toBeNull();
    expect(params.get("include_invalidated")).not.toBe("true");
    expect(screen.getByRole("heading", { level: 2, name: "Récords" })).toBeInTheDocument();
    for (const name of ["Fecha", "Récord", "Valor", "Origen", "Estado", "Acciones"]) expect(within(table()).getByRole("columnheader", { name })).toBeInTheDocument();
  });

  it("cada fila dice qué récord es y su valor: «Deadlift 1RM» 110 kg, «Back Squat 1RM» 85 kg y «Helen (benchmark)» 11:42 RX", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    expect(within(table()).getAllByRole("row")).toHaveLength(ALIVE.length + 1);
    expect(rowOf("Deadlift 1RM", "4 sept 2026")).toHaveTextContent("110 kg");
    expect(rowOf("Back Squat 1RM")).toHaveTextContent("85 kg");
    expect(rowOf("Back Squat 1RM")).toHaveTextContent("19 oct 2026");
    expect(rowOf("Helen (benchmark)")).toHaveTextContent("11:42 RX");
    expect(rowOf("Helen (benchmark)")).toHaveTextContent("20 oct 2026");
    expect(rowOf("Deadlift 1RM", "1 ago 2026")).toHaveTextContent("100 kg");
  });

  it("«Vigente» es texto en los tres vigentes y el que dejó de serlo dice «Histórico»", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    expect(within(table()).getAllByText("Vigente")).toHaveLength(3);
    expect(within(rowOf("Deadlift 1RM", "1 ago 2026")).getByText("Histórico")).toBeInTheDocument();
    expect(within(rowOf("Deadlift 1RM", "1 ago 2026")).queryByText("Vigente")).not.toBeInTheDocument();
  });

  it("el origen se dice con palabras: «Manual» con quien lo registró, «Automático del WOD» y «Automático (tablet)»", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    const manual = rowOf("Deadlift 1RM", "4 sept 2026");
    expect(within(manual).getByText(/Manual/)).toBeInTheDocument();
    expect(manual).toHaveTextContent("Carlos");
    expect(within(rowOf("Back Squat 1RM")).getByText("Automático del WOD")).toBeInTheDocument();
    expect(within(rowOf("Helen (benchmark)")).getByText("Automático (tablet)")).toBeInTheDocument();
    expect(within(rowOf("Helen (benchmark)")).queryByText("Automático del WOD")).not.toBeInTheDocument();
  });

  it("un derivado sin `result_source` sigue siendo «Automático del WOD»", async () => {
    renderTab({ [LIST]: listOf([derivedRm(2, { result_source: null })]) });

    expect(await screen.findByText("Automático del WOD")).toBeInTheDocument();
  });

  it("un manual sin nombre de quien lo registró no deja un hueco: dice «Manual»", async () => {
    renderTab({ [LIST]: listOf([record(1, { recorded_by_name: null })]) });

    expect(await screen.findByText(/Manual/)).toBeInTheDocument();
  });
});

describe("RecordsTab · derivados y manuales (S9-D13)", () => {
  it("un derivado enlaza a su WOD y explica que se corrige desde el resultado", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    const squat = rowOf("Back Squat 1RM");
    expect(within(squat).getByRole("link", { name: "Ver el WOD de Back Squat 1RM" })).toHaveAttribute("href", `/wods/${WOD_ID}`);
    expect(squat).toHaveTextContent("Se corrige corrigiendo el resultado que lo originó.");
    const helen = rowOf("Helen (benchmark)");
    expect(within(helen).getByRole("link", { name: "Ver el WOD de Helen (benchmark)" })).toHaveAttribute("href", `/wods/${OTHER_WOD_ID}`);
  });

  it("un derivado no tiene «Invalidar»", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    expect(within(rowOf("Back Squat 1RM")).queryByRole("button", { name: /Invalidar/ })).not.toBeInTheDocument();
    expect(within(rowOf("Helen (benchmark)")).queryByRole("button", { name: /Invalidar/ })).not.toBeInTheDocument();
  });

  it("un manual no explica nada del resultado ni enlaza a un WOD", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    const manual = rowOf("Deadlift 1RM", "4 sept 2026");
    expect(manual).not.toHaveTextContent("Se corrige corrigiendo el resultado");
    expect(within(manual).queryByRole("link")).not.toBeInTheDocument();
  });

  it("«Invalidar» solo aparece en los manuales vivos (dos en esta lista) y nombra el récord y la fecha", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    expect(screen.getAllByRole("button", { name: /^Invalidar / })).toHaveLength(2);
    expect(invalidateButton("Deadlift 1RM", "4 sept 2026")).toBeInTheDocument();
    expect(invalidateButton("Deadlift 1RM", "1 ago 2026")).toBeInTheDocument();
  });

  it("con el socio dado de baja no hay «Invalidar» en ninguna fila, pero el enlace al WOD sí", async () => {
    renderTab({}, true);
    await screen.findByText("Helen (benchmark)");

    expect(screen.queryByRole("button", { name: /^Invalidar / })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver el WOD de Back Squat 1RM" })).toBeInTheDocument();
  });
});

describe("RecordsTab · filtros (chips)", () => {
  it("ofrece los chips «RMs», «Benchmarks» y «Ver invalidados» sin ninguno activo", async () => {
    renderTab();
    await screen.findByText("Helen (benchmark)");

    const kinds = screen.getByRole("group", { name: "Tipo de récord" });
    expect(within(kinds).getByRole("button", { name: "RMs" })).toHaveAttribute("aria-pressed", "false");
    expect(within(kinds).getByRole("button", { name: "Benchmarks" })).toHaveAttribute("aria-pressed", "false");
    expect(within(screen.getByRole("group", { name: "Estado del récord" })).getByRole("button", { name: "Ver invalidados" })).toHaveAttribute("aria-pressed", "false");
  });

  it("«Benchmarks» pide kind=benchmark desde la primera página, lo deja en la URL y muestra solo Helen; pulsarlo otra vez lo quita", async () => {
    const { mock, user } = renderTab({}, false, `${BASE}&offset=25`);
    await screen.findByText("Helen (benchmark)");

    await user.click(screen.getByRole("button", { name: "Benchmarks" }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("kind")).toBe("benchmark");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
    expect(screen.getByRole("button", { name: "Benchmarks" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("where")).toHaveTextContent("kind=benchmark");
    await waitFor(() => {
      expect(screen.queryByText("Back Squat 1RM")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Helen (benchmark)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Benchmarks" }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("kind")).toBeNull();
    });
    expect(await screen.findByText("Back Squat 1RM")).toBeInTheDocument();
  });

  it("«RMs» pide kind=rm y deja fuera los benchmarks", async () => {
    const { mock, user } = renderTab();
    await screen.findByText("Helen (benchmark)");

    await user.click(screen.getByRole("button", { name: "RMs" }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("kind")).toBe("rm");
    });
    await waitFor(() => {
      expect(screen.queryByText("Helen (benchmark)")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "RMs" })).toHaveAttribute("aria-pressed", "true");
  });

  it("«Ver invalidados» pide include_invalidated=true y muestra el invalidado con su motivo; sin él no sale", async () => {
    const { mock, user } = renderTab();
    await screen.findByText("Helen (benchmark)");
    expect(screen.queryByText("Thruster 1RM")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ver invalidados" }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("include_invalidated")).toBe("true");
    });
    expect(screen.getByRole("button", { name: "Ver invalidados" })).toHaveAttribute("aria-pressed", "true");
    const row = await waitFor(() => rowOf("Thruster 1RM"));
    expect(within(row).getByText("Invalidado")).toBeInTheDocument();
    expect(row).toHaveTextContent("Error de digitación");
    expect(within(row).queryByText("Vigente")).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /^Invalidar / })).not.toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("invalidated=1");
  });

  it.each([
    ["superseded", "Resultado corregido"],
    ["voided", "Resultado anulado"],
    ["manual_error", "Error de digitación"],
  ] as const)("un invalidado por «%s» dice «%s»", async (reason, text) => {
    renderTab({ [LIST]: listOf([record(5, { invalidated_at: "2026-07-24T15:00:00Z", invalidated_reason: reason, is_current: false })]) }, false, `${BASE}&invalidated=1`);

    expect(await screen.findByText("Invalidado")).toBeInTheDocument();
    expect(table()).toHaveTextContent(text);
  });

  it("lee kind e invalidated de la URL al cargar (sobrevive a recargar)", async () => {
    const { mock } = renderTab({}, false, `${BASE}&kind=benchmark&invalidated=1`);

    await screen.findByText("Helen (benchmark)");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("kind")).toBe("benchmark");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("include_invalidated")).toBe("true");
    expect(screen.getByRole("button", { name: "Benchmarks" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Ver invalidados" })).toHaveAttribute("aria-pressed", "true");
  });

  it("un `kind` inválido en la URL se ignora y no llega al api", async () => {
    const { mock } = renderTab({}, false, `${BASE}&kind=todo`);

    await screen.findByText("Helen (benchmark)");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("kind")).toBeNull();
  });
});

describe("RecordsTab · Invalidar (S9-D13, S9-D33)", () => {
  const INVALIDATE = `POST ${invalidatePath(recordId(1))}`;
  const invalidated = { status: 200, body: record(1, { is_current: false, invalidated_at: "2026-10-21T15:00:00Z", invalidated_reason: "manual_error" }) };
  const openModal = async (user: ReturnType<typeof renderTab>["user"]) => {
    await screen.findByText("Helen (benchmark)");
    await user.click(invalidateButton("Deadlift 1RM", "4 sept 2026"));
    return screen.getByRole("dialog", { name: "¿Invalidar este récord?" });
  };

  it("«Invalidar» abre un ConfirmModal que explica la consecuencia y no pide motivo", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: invalidated });

    const dialog = await openModal(user);

    expect(within(dialog).getByText("El récord deja de contarse y se conserva en la auditoría. El mejor récord que quede pasa a ser el vigente. No se puede deshacer.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    expect(mock.callsTo(INVALIDATE)).toHaveLength(0);
  });

  it("cancelar no invalida nada", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: invalidated });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(INVALIDATE)).toHaveLength(0);
  });

  it("confirmar hace POST invalidate de ESE récord sin cuerpo y relee la lista", async () => {
    let reads = 0;
    const { user, mock } = renderTab({
      [INVALIDATE]: invalidated,
      [LIST]: (call) => {
        reads += 1;
        return listOf(reads === 1 ? ALIVE : ALIVE.slice(1))(call);
      },
    });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(INVALIDATE)).toHaveLength(1);
    expect(mock.callsTo(INVALIDATE)[0]?.body).toBeUndefined();
    expect(mock.callsTo(INVALIDATE)[0]?.path).toBe(`/athletes/${MEMBER_ID}/records/${recordId(1)}/invalidate`);
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("403 (coach que no lo registró o pasaron 24 horas) lo explica dentro del modal y lo deja abierto", async () => {
    const { user } = renderTab({ [INVALIDATE]: apiError(403, "forbidden") });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Solo un administrador puede invalidar este récord. Un coach solo invalida el que registró él en las últimas 24 horas.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("409 record_is_derived explica que se corrige desde el resultado y relee la lista", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: apiError(409, "record_is_derived") });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este récord es automático: se corrige corrigiendo o anulando el resultado que lo originó. Actualizamos la lista.");
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("409 record_already_invalidated dice que ya estaba invalidado y relee la lista", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: apiError(409, "record_already_invalidated") });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este récord ya estaba invalidado. Actualizamos la lista.");
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("404 dice que el récord ya no existe y relee la lista", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: apiError(404, "record_not_found") });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este récord ya no existe. Actualizamos la lista.");
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("429 dice cuánto esperar y no relee la lista", async () => {
    const { user, mock } = renderTab({ [INVALIDATE]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalidaste muchos récords seguidos. Espera 30 segundos e intenta de nuevo.");
    expect(mock.callsTo(LIST)).toHaveLength(1);
  });

  it("500 dice qué hacer sin el texto técnico", async () => {
    const { user } = renderTab({ [INVALIDATE]: apiError(500, "internal_error") });
    const dialog = await openModal(user);

    await user.click(within(dialog).getByRole("button", { name: "Invalidar récord" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos invalidar el récord. Intenta de nuevo en un momento.");
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
  });
});

describe("RecordsTab · paginación en el servidor", () => {
  it("con 60 récords pide la segunda página con offset 25 y lo deja en la URL", async () => {
    const { mock, user } = renderTab({ [LIST]: (call) => pageReply(call, ALIVE, 60) });
    await screen.findByText("Helen (benchmark)");
    expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("25");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("25");
    expect(screen.getByTestId("where")).toHaveTextContent("offset=25");
  });

  it("lee limit y offset de la URL al cargar y cambiar el tamaño vuelve a la primera página", async () => {
    const { mock, user } = renderTab({ [LIST]: (call) => pageReply(call, ALIVE, 120) }, false, `${BASE}&limit=50&offset=50`);
    await screen.findByText("Helen (benchmark)");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("50");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("50");
    expect(screen.getByText("Página 2 de 3")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Mostrar"), "100");

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("100");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
  });

  it("una página fuera de rango lo dice y ofrece volver a la primera", async () => {
    const { user, mock } = renderTab({ [LIST]: (call) => pageReply(call, [], 30) }, false, `${BASE}&offset=50`);

    expect(await screen.findByText("Esta página ya no tiene récords.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));
    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
    });
  });
});

describe("RecordsTab · estados", () => {
  it("sin récords guía a registrar el primero y no dice «No hay datos»", async () => {
    renderTab({ [LIST]: listOf([]) });

    expect(await screen.findByText("Todavía no hay récords registrados. Usa «Registrar récord» para guardar el primero.")).toBeInTheDocument();
    expect(screen.queryByText(/No hay datos/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("con un filtro activo y sin resultados no dice que no hay récords: pide quitar un filtro", async () => {
    renderTab({ [LIST]: listOf([MANUAL_CURRENT]) }, false, `${BASE}&kind=benchmark`);

    expect(await screen.findByText("No hay récords con estos filtros. Quita un filtro para ver más.")).toBeInTheDocument();
    expect(screen.queryByText(/Todavía no hay récords/)).not.toBeInTheDocument();
  });

  it("mientras carga ya pidió la lista y no muestra filas ni el vacío", async () => {
    const { mock } = renderTab({ [LIST]: () => new Promise(() => undefined) });

    await waitFor(() => {
      expect(mock.callsTo(LIST)).toHaveLength(1);
    });
    expect(screen.queryByText(/Todavía no hay récords/)).not.toBeInTheDocument();
    expect(screen.queryByText("Helen (benchmark)")).not.toBeInTheDocument();
  });

  it("un error 500 dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({
      [LIST]: (call) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : listOf()(call);
      },
    });

    expect(await screen.findByText("No pudimos cargar los récords. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Helen (benchmark)")).toBeInTheDocument();
  });

  it("un 403 explica que no tiene permiso para ver los récords", async () => {
    renderTab({ [LIST]: apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver los récords de este socio.")).toBeInTheDocument();
  });

  it("un 404 dice que el socio ya no existe", async () => {
    renderTab({ [LIST]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y elige otro.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTab();
    await screen.findByText("Helen (benchmark)");

    expect(await axe(container)).toHaveNoViolations();
  });
});

// Revisión S9-F2.
describe("RecordsTab · revisión", () => {
  it("un 429 de la lista dice cuánto esperar", async () => {
    renderTab({ [LIST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });

    expect(await screen.findByText("Hiciste muchas consultas seguidas. Espera 30 segundos e intenta de nuevo.")).toBeInTheDocument();
  });

  it("carrera: la respuesta tardía de la lista sin filtro no pisa la de «Benchmarks»", async () => {
    let release: (reply: MockReply) => void = () => undefined;
    const late = new Promise<MockReply>((resolve) => {
      release = resolve;
    });
    let first = true;
    let firstCall: RecordedCall | undefined;
    const { user } = renderTab({
      [LIST]: (call) => {
        if (first) {
          first = false;
          firstCall = call;
          return late;
        }
        return listOf()(call);
      },
    });
    await screen.findByRole("button", { name: "Benchmarks" });

    await user.click(screen.getByRole("button", { name: "Benchmarks" }));
    expect(await screen.findByText("Helen (benchmark)")).toBeInTheDocument();
    if (firstCall === undefined) throw new Error("la primera petición no salió");
    release(pageReply(firstCall, ALIVE));

    await waitFor(() => {
      expect(screen.queryByText("Back Squat 1RM")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Helen (benchmark)")).toBeInTheDocument();
  });

  it("tras invalidar con éxito el foco pasa al encabezado «Récords» (el botón ya no existe)", async () => {
    const INVALIDATE = `POST ${invalidatePath(recordId(1))}`;
    const { user } = renderTab({ [INVALIDATE]: { status: 200, body: record(1, { is_current: false, invalidated_at: "2026-10-21T15:00:00Z", invalidated_reason: "manual_error" }) } });
    await screen.findByText("Helen (benchmark)");
    await user.click(invalidateButton("Deadlift 1RM", "4 sept 2026"));

    await user.click(within(screen.getByRole("dialog", { name: "¿Invalidar este récord?" })).getByRole("button", { name: "Invalidar récord" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 2, name: "Récords" })).toHaveFocus();
    });
  });

  it("invalidar relee RMs, récords, benchmarks y resumen del socio, pero no sus medidas ni las de otro socio", async () => {
    const INVALIDATE = `POST ${invalidatePath(recordId(1))}`;
    const queryClient = testQueryClient();
    queryClient.setQueryData(["athlete-metrics", MEMBER_ID, { limit: 25, offset: 0 }], { items: [], total: 0, limit: 25, offset: 0 });
    queryClient.setQueryData(["athlete-rms", "otro-socio", { limit: 25, offset: 0 }], { items: [], total: 0, limit: 25, offset: 0 });
    queryClient.setQueryData(["athlete-summary", MEMBER_ID], { ok: true });
    const { user } = renderAthlete(<RecordsTab memberId={MEMBER_ID} memberDeleted={false} />, {
      handlers: { [LIST]: listOf(), [INVALIDATE]: { status: 200, body: record(1, { is_current: false, invalidated_at: "2026-10-21T15:00:00Z", invalidated_reason: "manual_error" }) } },
      route: BASE,
      queryClient,
    });
    await screen.findByText("Helen (benchmark)");
    await user.click(invalidateButton("Deadlift 1RM", "4 sept 2026"));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Invalidar récord" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    const stale = (key: readonly unknown[]): boolean | undefined => queryClient.getQueryCache().find({ queryKey: key, exact: false })?.state.isInvalidated;
    expect(stale(["athlete-summary", MEMBER_ID])).toBe(true);
    expect(stale(["athlete-metrics", MEMBER_ID])).toBe(false);
    expect(stale(["athlete-rms", "otro-socio"])).toBe(false);
  });
});
